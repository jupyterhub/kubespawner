"""pytest fixtures for kubespawner"""
import asyncio
import base64
import inspect
import io
import logging
import os
import sys
import tarfile
from functools import partial

import pytest
import pytest_asyncio
from jupyterhub.app import JupyterHub
from jupyterhub.objects import Hub
from kubernetes.client import CoreV1Api as sync_CoreV1Api
from kubernetes.config import load_kube_config as sync_load_kube_config
from kubernetes.stream import stream as sync_stream
from kubernetes_asyncio.client import (
    V1ConfigMap,
    V1Namespace,
    V1Pod,
    V1PodSpec,
    V1Secret,
    V1Service,
    V1ServicePort,
    V1ServiceSpec,
)
from kubernetes_asyncio.client.rest import ApiException
from kubernetes_asyncio.config import load_kube_config
from kubernetes_asyncio.watch import Watch
from traitlets.config import Config

from kubespawner import KubeSpawner
from kubespawner.clients import shared_client

here = os.path.abspath(os.path.dirname(__file__))
jupyterhub_config_py = os.path.join(here, "jupyterhub_config.py")

# We do these to set up the synchronous client, needed for executing
# python inside pods.
sync_load_kube_config()
sync_corev1api = sync_CoreV1Api()


async def cancel_tasks():
    """Cancel long-running tasks

    This is copied from JupyterHub's shutdown_cancel_tasks (as of 2.1.1)
    to emulate JupyterHub's cleanup of cancelled tasks at shutdown.

    shared_client's cleanup relies on this.
    """
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    log = logging.getLogger("traitlets")
    if tasks:
        log.debug(f"Cancelling {len(tasks)} pending tasks")
        [t.cancel() for t in tasks]

        try:
            await asyncio.wait(tasks)
        except asyncio.CancelledError as e:
            log.debug("Caught Task CancelledError. Ignoring")
        except Exception:
            log.exception("Caught Exception in cancelled task")

        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        for t in tasks:
            log.debug("Task status: %s", t)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    # cancel tasks, as is done in JupyterHub
    loop.run_until_complete(cancel_tasks())
    loop.close()


@pytest.fixture(autouse=True)
def traitlets_logging():
    """Ensure traitlets default logging is enabled

    so KubeSpawner logs are captured by pytest.
    By default, there is a "NullHandler" so no logs are produced.
    """
    logger = logging.getLogger('traitlets')
    logger.setLevel(logging.DEBUG)
    logger.handlers = []


@pytest.fixture(scope="session")
def kube_ns():
    """Fixture for the kubernetes namespace"""
    return os.environ.get("KUBESPAWNER_TEST_NAMESPACE") or "kubespawner-test"


@pytest.fixture(scope="session")
def kube_another_ns():
    """Fixture for the another kubernetes namespace"""
    return os.environ.get("KUBESPAWNER_ANOTHER_NAMESPACE") or "kubespawner-another"


@pytest.fixture
def config(kube_ns):
    """Return a traitlets Config object

    The base configuration for testing.
    Use when constructing Spawners for tests
    """
    cfg = Config()
    cfg.KubeSpawner.namespace = kube_ns
    cfg.KubeSpawner.cmd = ["jupyterhub-singleuser"]
    cfg.KubeSpawner.start_timeout = 180
    # prevent spawners from exiting early due to missing env
    cfg.KubeSpawner.environment = {
        "JUPYTERHUB_API_TOKEN": "test-secret-token",
        "JUPYTERHUB_CLIENT_ID": "ignored",
    }
    return cfg


@pytest.fixture(scope="session")
def ssl_app(tmpdir_factory, kube_ns):
    """Partially instantiate a JupyterHub instance to generate ssl certificates

    Generates ssl certificates on the host,
    which will then be staged

    This is not a fully instantiated Hub,
    but it will have internal_ssl-related attributes such as
    .internal_trust_bundles and .internal_certs_location initialized.
    """
    tmpdir = tmpdir_factory.mktemp("ssl")
    tmpdir.chdir()
    config = Config()
    config.JupyterHub.internal_ssl = True
    tmpdir.mkdir("internal-ssl")
    # use relative path for ssl certs
    config.JupyterHub.internal_certs_location = "internal-ssl"
    config.JupyterHub.trusted_alt_names = [
        "DNS:hub-ssl",
        f"DNS:hub-ssl.{kube_ns}",
        f"DNS:hub-ssl.{kube_ns}.svc",
        f"DNS:hub-ssl.{kube_ns}.svc.cluster.local",
    ]
    app = JupyterHub(config=config)
    app.init_internal_ssl()
    return app


async def watch_logs(kube_client, pod_info):
    """Stream a single pod's logs

    pod logs are streamed directly to sys.stdout,
    so that pytest capture can deal with it.

    Called for each new pod from watch_kubernetes
    """
    watch = Watch()
    while True:
        try:
            async for event in watch.stream(
                func=kube_client.read_namespaced_pod_log,
                namespace=pod_info.namespace,
                name=pod_info.name,
            ):
                print(f"[{pod_info.name}]: {event}")
        except ApiException as e:
            if e.status == 400:
                # 400 can occur if the container is not yet ready
                # wait and retry
                await asyncio.sleep(1)
                continue
            elif e.status == 404:
                # pod is gone, we are done
                return
            else:
                # unexpected error
                print(f"Error watching logs for {pod_info.name}: {e}", file=sys.stderr)
                raise
        else:
            break


async def watch_kubernetes(kube_client, kube_ns):
    """Stream kubernetes events to stdout

    so that pytest io capturing can include k8s events and logs

    All events are streamed to stdout

    When a new pod is started, spawn an additional task to watch its logs
    """

    watch = Watch()
    watch_task = {}

    try:
        async for event in watch.stream(
            func=kube_client.list_namespaced_event,
            namespace=kube_ns,
        ):
            resource = event['object']
            obj = resource.involved_object
            print(
                f"k8s event ({event['type']} {obj.kind}/{obj.name}): {resource.message}"
            )

            # new pod appeared, start streaming its logs
            if (
                obj.kind == "Pod"
                and event["type"] == "ADDED"
                and obj.name not in watch_task
            ):
                watch_task[obj.name] = asyncio.create_task(
                    watch_logs(
                        kube_client,
                        obj,
                    ),
                )

    except asyncio.CancelledError as exc:
        # kube_client cleanup cancelled us.  In turn, we should cancel
        # the individual watch tasks.
        for t in watch_task:
            if watch_task[t] and not watch_task[t].done():
                try:
                    watch_task[t].cancel()
                except asyncio.CancelledError:
                    # Swallow these; they are what we expect.
                    pass
        # And re-raise so kube_client can finish cleanup
        raise exc


@pytest_asyncio.fixture(scope="session")
async def kube_client(request, kube_ns, kube_another_ns):
    """fixture for the Kubernetes client object.
    skips test that require kubernetes if kubernetes cannot be contacted
    - Ensures kube_ns and kube_another_ns namespaces do exist
    - Hooks up kubernetes events and logs to pytest capture
    - Cleans up kubernetes namespace on exit
    """
    await load_kube_config()
    client = shared_client("CoreV1Api")

    expected_namespaces = [kube_ns, kube_another_ns]
    try:
        namespaces = await client.list_namespace(_request_timeout=3)
    except Exception as e:
        pytest.skip("Kubernetes not found: %s" % e)

    for namespace in expected_namespaces:
        if not any(ns.metadata.name == namespace for ns in namespaces.items):
            print("Creating namespace %s" % namespace)
            await client.create_namespace(V1Namespace(metadata=dict(name=namespace)))
        else:
            print("Using existing namespace %s" % namespace)

    # begin streaming all logs and events in our test namespace
    log_tasks = [
        asyncio.create_task(watch_kubernetes(client, namespace))
        for namespace in expected_namespaces
    ]

    yield client

    # Clean up at close by sending a cancel to watch_kubernetes and letting
    # it handle the signal, cancel the tasks *it* started, and then raising
    # it back to us.
    for task in log_tasks:
        try:
            task.cancel()
        except asyncio.CancelledError:
            pass

    # allow opting out of namespace cleanup, for post-mortem debugging
    if not os.environ.get("KUBESPAWNER_DEBUG_NAMESPACE"):
        for namespace in expected_namespaces:
            await client.delete_namespace(namespace, body={}, grace_period_seconds=0)
            for _ in range(20):  # Usually finishes a good deal faster
                try:
                    await client.read_namespace(namespace)
                except ApiException as e:
                    if e.status == 404:
                        return
                    else:
                        raise
                else:
                    print("waiting for %s to delete" % namespace)
                    await asyncio.sleep(1)


async def wait_for_pod(kube_client, kube_ns, pod_name, timeout=90):
    """Wait for a pod to be ready"""
    conditions = {}
    for i in range(int(timeout)):
        pod = await kube_client.read_namespaced_pod(namespace=kube_ns, name=pod_name)
        for condition in pod.status.conditions or []:
            conditions[condition.type] = condition.status

        if conditions.get("Ready") != "True":
            print(
                f"Waiting for pod {kube_ns}/{pod_name}; current status: {pod.status.phase}; {conditions}"
            )
            await asyncio.sleep(1)
        else:
            break

    if conditions.get("Ready") != "True":
        raise TimeoutError(f"pod {kube_ns}/{pod_name} failed to start: {pod.status}")
    return pod


async def ensure_not_exists(kube_client, kube_ns, name, resource_type, timeout=30):
    """Ensure an object doesn't exist

    Request deletion and wait for it to be gone
    """
    delete = getattr(kube_client, f"delete_namespaced_{resource_type}")
    read = getattr(kube_client, f"read_namespaced_{resource_type}")
    try:
        await delete(namespace=kube_ns, name=name)
    except ApiException as e:
        if e.status != 404:
            raise

    while True:
        # wait for delete
        try:
            await read(namespace=kube_ns, name=name)
        except ApiException as e:
            if e.status == 404:
                # deleted
                break
            else:
                raise
        else:
            print(f"waiting for {resource_type}/{name} to delete")
            await asyncio.sleep(1)


async def create_resource(
    kube_client, kube_ns, resource_type, manifest, delete_first=True
):
    """Create a kubernetes resource

    handling 409 errors and others that can occur due to rapid startup
    (typically: default service account doesn't exist yet
    """
    name = manifest.metadata["name"]
    if delete_first:
        await ensure_not_exists(kube_client, kube_ns, name, resource_type)
    print(f"Creating {resource_type} {name}")
    create = getattr(kube_client, f"create_namespaced_{resource_type}")
    error = None
    for i in range(10):
        try:
            await create(
                body=manifest,
                namespace=kube_ns,
            )
        except ApiException as e:
            if e.status == 409:
                break
            error = e
            # need to retry since this can fail if run too soon after namespace creation
            print(e, file=sys.stderr)
            await asyncio.sleep(int(e.headers.get("Retry-After", 1)))
        else:
            break
    else:
        raise error


async def create_hub_pod(kube_client, kube_ns, pod_name="hub", ssl=False):
    config_map_name = pod_name + "-config"
    secret_name = pod_name + "-secret"
    with open(jupyterhub_config_py) as f:
        config = f.read()

    config_map_manifest = V1ConfigMap(
        metadata={"name": config_map_name}, data={"jupyterhub_config.py": config}
    )

    config_map = await create_resource(
        kube_client,
        kube_ns,
        "config_map",
        config_map_manifest,
        delete_first=True,
    )

    volumes = [{"name": "config", "configMap": {"name": config_map_name}}]
    volume_mounts = [
        {
            "mountPath": "/etc/jupyterhub/jupyterhub_config.py",
            "subPath": "jupyterhub_config.py",
            "name": "config",
        }
    ]
    if ssl:
        volumes.append({"name": "secret", "secret": {"secretName": secret_name}})
        volume_mounts.append(
            {
                "mountPath": "/etc/jupyterhub/secret",
                "name": "secret",
            }
        )

    pod_manifest = V1Pod(
        metadata={
            "name": pod_name,
            "labels": {"component": "hub", "hub-name": pod_name},
        },
        spec=V1PodSpec(
            volumes=volumes,
            containers=[
                {
                    "image": "jupyterhub/jupyterhub:1.3",
                    "name": "hub",
                    "volumeMounts": volume_mounts,
                    "args": [
                        "jupyterhub",
                        "-f",
                        "/etc/jupyterhub/jupyterhub_config.py",
                    ],
                    "env": [{"name": "PYTHONUNBUFFERED", "value": "1"}],
                    "readinessProbe": {
                        "tcpSocket": {
                            "port": 8081,
                        },
                        "periodSeconds": 1,
                    },
                }
            ],
        ),
    )
    pod = await create_resource(kube_client, kube_ns, "pod", pod_manifest)
    return await wait_for_pod(kube_client, kube_ns, pod_name)


@pytest_asyncio.fixture(scope="session")
async def hub_pod(kube_client, kube_ns):
    """Create and return a pod running jupyterhub"""
    return await create_hub_pod(kube_client, kube_ns)


@pytest.fixture
def hub(hub_pod):
    """Return the jupyterhub Hub object for passing to Spawner constructors

    Ensures the hub_pod is running
    """
    return Hub(ip=hub_pod.status.pod_ip, port=8081)


@pytest_asyncio.fixture(scope="session")
async def hub_pod_ssl(kube_client, kube_ns, ssl_app):
    """Start a hub pod with internal_ssl enabled"""
    # load ssl dir to tarfile
    buf = io.BytesIO()
    tf = tarfile.TarFile(fileobj=buf, mode="w")
    tf.add(ssl_app.internal_certs_location, arcname="internal-ssl", recursive=True)

    # store tarfile in a secret
    b64_certs = base64.b64encode(buf.getvalue()).decode("ascii")
    secret_name = "hub-ssl-secret"
    secret_manifest = V1Secret(
        metadata={"name": secret_name}, data={"internal-ssl.tar": b64_certs}
    )
    await create_resource(kube_client, kube_ns, "secret", secret_manifest)

    name = "hub-ssl"

    service_manifest = V1Service(
        metadata=dict(name=name),
        spec=V1ServiceSpec(
            type="ClusterIP",
            ports=[V1ServicePort(port=8081, target_port=8081)],
            selector={"hub-name": name},
        ),
    )

    await create_resource(kube_client, kube_ns, "service", service_manifest)

    return await create_hub_pod(
        kube_client,
        kube_ns,
        pod_name=name,
        ssl=True,
    )


@pytest.fixture
def hub_ssl(kube_ns, hub_pod_ssl):
    """Return the Hub object for connecting to a running hub pod with internal_ssl enabled"""
    return Hub(
        proto="https",
        ip=f"{hub_pod_ssl.metadata.name}.{kube_ns}",
        port=8081,
        base_url="/hub/",
    )


class ExecError(Exception):
    """Error raised when a kubectl exec fails"""

    def __init__(self, exit_code, message="", command="exec"):
        self.exit_code = exit_code
        self.message = message
        self.command = command

    def __str__(self):
        return "{command} exited with status {exit_code}: {message}".format(
            command=self.command,
            exit_code=self.exit_code,
            message=self.message,
        )


async def _exec_python_in_pod(
    kube_client, kube_ns, pod_name, code, kwargs=None, _retries=0
):
    """Run simple Python code in a pod

    code can be a str of code, or a 'simple' Python function,
    where source can be extracted (i.e. self-contained imports, etc.)

    kwargs are passed to the function, if it is given.
    """
    pod = await wait_for_pod(kube_client, kube_ns, pod_name)
    original_code = code
    if not isinstance(code, str):
        # allow simple self-contained (no globals or args) functions
        func = code
        code = "\n".join(
            [
                inspect.getsource(func),
                "_kw = %r" % (kwargs or {}),
                f"{func.__name__}(**_kw)",
                "",
            ]
        )
    elif kwargs:
        raise ValueError("kwargs can only be passed to functions, not code strings.")

    exec_command = [
        "python3",
        "-c",
        code,
    ]
    print(f"Running {code} in {pod_name}")
    # need to create ws client to get returncode,
    # see https://github.com/kubernetes-client/python/issues/812
    #
    # That's why we are using the synchronous Kubernetes client here
    # and why we imported them in the first place: kubernetes_asyncio
    # does not yet support multichannel ws clients, which are needed
    # to get the return code.
    # cf https://github.com/tomplus/kubernetes_asyncio/issues/12
    client = sync_stream(
        sync_corev1api.connect_get_namespaced_pod_exec,
        pod_name,
        namespace=kube_ns,
        command=exec_command,
        stderr=True,
        stdin=False,
        stdout=True,
        tty=False,
        _preload_content=False,
    )
    client.run_forever(timeout=60)

    # let pytest capture stderr
    stderr = client.read_stderr()
    print(stderr, file=sys.stderr)

    returncode = client.returncode
    if returncode:
        print(client.read_stdout())
        if _retries == 0:
            raise ExecError(exit_code=returncode, message=stderr, command=code)
        else:
            # retry
            await asyncio.sleep(1)
            return await _exec_python_in_pod(
                kube_client,
                kube_ns,
                pod_name,
                code,
                _retries=_retries - 1,
            )
    else:
        return client.read_stdout().rstrip()


@pytest.fixture
def exec_python_pod(kube_client, kube_ns):
    """Fixture to return callable to execute python in a pod by name

    Used as a fixture to contain references to client, namespace
    """
    return partial(_exec_python_in_pod, kube_client, kube_ns)


@pytest_asyncio.fixture(scope="session")
async def exec_python(kube_client, kube_ns):
    """Return a callable to execute Python code in a pod in the test namespace

    This fixture creates a dedicated pod for executing commands
    """

    # note: this was created when there were only single-user pods running,
    # but now there's always a hub pod where we could be running,
    # and the ssl case *must* run from the hub pod for access to certs
    # Note: we could do without this feature if we always ran

    pod_name = "kubespawner-test-exec"
    pod_manifest = V1Pod(
        metadata={"name": pod_name},
        spec=V1PodSpec(
            containers=[
                {
                    "image": "python:3.8",
                    "name": "python",
                    "args": ["/bin/sh", "-c", "while true; do sleep 5; done"],
                }
            ],
            termination_grace_period_seconds=0,
        ),
    )
    pod = await create_resource(kube_client, kube_ns, "pod", pod_manifest)

    yield partial(_exec_python_in_pod, kube_client, kube_ns, pod_name)


@pytest.fixture(scope="function")
async def reset_pod_reflectors():
    """
    Resets the class state KubeSpawner.reflectors before and after the
    test function executes. This enables us to start fresh if a test needs to
    test configuration influencing the pod reflector options.
    """

    await KubeSpawner._stop_all_reflectors()
    yield
    await KubeSpawner._stop_all_reflectors()
