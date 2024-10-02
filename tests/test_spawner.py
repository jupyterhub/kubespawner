import asyncio
import base64
import json
import os
from functools import partial
from unittest.mock import Mock

import jupyterhub
import pytest
from jupyterhub.objects import Hub, Server
from jupyterhub.orm import Spawner
from jupyterhub.utils import exponential_backoff
from kubernetes_asyncio.client.models import (
    V1Capabilities,
    V1Container,
    V1EnvVar,
    V1PersistentVolumeClaim,
    V1Pod,
    V1SecurityContext,
)
from traitlets.config import Config

import kubespawner
from kubespawner import KubeSpawner
from kubespawner.objects import make_owner_reference, make_service
from kubespawner.slugs import safe_slug


class MockUser(Mock):
    name = '9user@email.com'
    server = Server()

    def __init__(self, **kwargs):
        super().__init__()
        for key, value in kwargs.items():
            setattr(self, key, value)

    @property
    def escaped_name(self):
        return self.name

    @property
    def url(self):
        return self.server.url


class MockOrmSpawner(Mock):
    name = 'server'
    server = None


async def test_deprecated_config():
    """Deprecated config is handled correctly"""
    with pytest.warns(DeprecationWarning):
        c = Config()
        # both set, non-deprecated wins
        c.KubeSpawner.singleuser_fs_gid = 5
        c.KubeSpawner.fs_gid = 10
        # only deprecated set, should still work
        c.KubeSpawner.hub_connect_ip = '10.0.1.1'
        c.KubeSpawner.singleuser_extra_pod_config = extra_pod_config = {"key": "value"}
        c.KubeSpawner.image_spec = 'abc:123'
        c.KubeSpawner.image_pull_secrets = 'k8s-secret-a'
        spawner = KubeSpawner(hub=Hub(), config=c, _mock=True)
        assert spawner.hub.connect_ip == '10.0.1.1'
        assert spawner.fs_gid == 10
        assert spawner.extra_pod_config == extra_pod_config
        # deprecated access gets the right values, too
        assert spawner.singleuser_fs_gid == spawner.fs_gid
        assert spawner.singleuser_extra_pod_config == spawner.extra_pod_config
        assert spawner.image == 'abc:123'
        assert spawner.image_pull_secrets[0]["name"] == 'k8s-secret-a'


async def test_deprecated_runtime_access():
    """Runtime access/modification of deprecated traits works"""
    spawner = KubeSpawner(_mock=True)
    spawner.singleuser_uid = 10
    assert spawner.uid == 10
    assert spawner.singleuser_uid == 10
    spawner.uid = 20
    assert spawner.uid == 20
    assert spawner.singleuser_uid == 20
    spawner.image_spec = 'abc:latest'
    assert spawner.image_spec == 'abc:latest'
    assert spawner.image == 'abc:latest'
    spawner.image = 'abc:123'
    assert spawner.image_spec == 'abc:123'
    assert spawner.image == 'abc:123'
    spawner.image_pull_secrets = 'k8s-secret-a'
    assert spawner.image_pull_secrets[0]["name"] == 'k8s-secret-a'


async def test_spawner_values():
    """Spawner values are set correctly"""
    spawner = KubeSpawner(_mock=True)

    def set_id(spawner):
        return 1

    assert spawner.uid == None
    spawner.uid = 10
    assert spawner.uid == 10
    spawner.uid = set_id
    assert spawner.uid == set_id
    spawner.uid = None
    assert spawner.uid == None

    assert spawner.gid == None
    spawner.gid = 20
    assert spawner.gid == 20
    spawner.gid = set_id
    assert spawner.gid == set_id
    spawner.gid = None
    assert spawner.gid == None

    assert spawner.fs_gid == None
    spawner.fs_gid = 30
    assert spawner.fs_gid == 30
    spawner.fs_gid = set_id
    assert spawner.fs_gid == set_id
    spawner.fs_gid = None
    assert spawner.fs_gid == None


def check_up(url, ssl_ca=None, ssl_client_cert=None, ssl_client_key=None):
    """Check that a url responds with a non-error code

    For use in exec_python_in_pod,
    which means imports need to be in the function

    Uses stdlib only because requests isn't always available in the target pod
    """
    import ssl
    from urllib import request

    if ssl_ca:
        context = ssl.create_default_context(
            purpose=ssl.Purpose.SERVER_AUTH, cafile=ssl_ca
        )
        if ssl_client_cert:
            context.load_cert_chain(certfile=ssl_client_cert, keyfile=ssl_client_key)
    else:
        context = None

    # disable redirects (this would be easier if we ran exec in an image with requests)
    class NoRedirect(request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    opener = request.build_opener(NoRedirect, request.HTTPSHandler(context=context))
    try:
        u = opener.open(url)
    except request.HTTPError as e:
        if e.status >= 400:
            raise
        u = e
    print(u.status)


async def test_spawn_start(
    kube_ns,
    kube_client,
    config,
    hub,
    exec_python,
):
    spawner = KubeSpawner(
        hub=hub,
        user=MockUser(name="start"),
        config=config,
        api_token="abc123",
        oauth_client_id="unused",
    )
    # empty spawner isn't running
    status = await spawner.poll()
    assert isinstance(status, int)

    pod_name = spawner.pod_name

    # start the spawner
    url = await spawner.start()

    # verify the pod exists
    pods = (await kube_client.list_namespaced_pod(kube_ns)).items
    pod_names = [p.metadata.name for p in pods]
    assert pod_name in pod_names

    # pod should be running when start returns
    pod = await kube_client.read_namespaced_pod(namespace=kube_ns, name=pod_name)
    assert pod.status.phase == "Running"

    # verify poll while running
    status = await spawner.poll()
    assert status is None

    # make sure spawn url is correct
    r = await exec_python(check_up, {"url": url}, _retries=3)
    assert r == "302"

    # stop the pod
    await spawner.stop()

    # verify pod is gone
    pods = (await kube_client.list_namespaced_pod(kube_ns)).items
    pod_names = [p.metadata.name for p in pods]
    assert pod_name not in pod_names

    # verify exit status
    status = await spawner.poll()
    assert isinstance(status, int)


async def test_spawn_start_in_different_namespace(
    kube_another_ns,
    kube_client,
    config,
    hub,
    exec_python,
):
    # hub is running in `kube_ns`. pods, PVC and other objects are created in `kube_another_ns`
    config.KubeSpawner.namespace = kube_another_ns

    spawner = KubeSpawner(
        hub=hub,
        user=MockUser(name="start"),
        config=config,
        api_token="abc123",
        oauth_client_id="unused",
    )
    # empty spawner isn't running
    status = await spawner.poll()
    assert isinstance(status, int)

    pod_name = spawner.pod_name

    # start the spawner
    url = await spawner.start()

    # verify the pod exists
    pods = (await kube_client.list_namespaced_pod(kube_another_ns)).items
    pod_names = [p.metadata.name for p in pods]
    assert pod_name in pod_names

    # pod should be running when start returns
    pod = await kube_client.read_namespaced_pod(
        namespace=kube_another_ns, name=pod_name
    )
    assert pod.status.phase == "Running"

    # verify poll while running
    status = await spawner.poll()
    assert status is None

    # make sure spawn url is correct
    r = await exec_python(check_up, {"url": url}, _retries=3)
    assert r == "302"

    # stop the pod
    await spawner.stop()

    # verify pod is gone
    pods = (await kube_client.list_namespaced_pod(kube_another_ns)).items
    pod_names = [p.metadata.name for p in pods]
    assert pod_name not in pod_names

    # verify exit status
    status = await spawner.poll()
    assert isinstance(status, int)


async def test_spawn_enable_user_namespaces():
    user = MockUser()
    spawner = KubeSpawner(user=user, _mock=True, enable_user_namespaces=True)
    assert spawner.namespace.endswith(f"-{safe_slug(user.name)}")


async def test_spawn_start_enable_user_namespaces(
    kube_another_ns,
    kube_client,
    config,
    hub,
    exec_python,
):
    # this should be a template, but using a static value
    # just to properly cleanup created namespace after test is finished
    config.KubeSpawner.user_namespace_template = kube_another_ns
    config.KubeSpawner.enable_user_namespaces = True

    spawner = KubeSpawner(
        hub=hub,
        user=MockUser(name="start@test"),
        config=config,
        api_token="abc123",
        oauth_client_id="unused",
    )
    # empty spawner isn't running
    status = await spawner.poll()
    assert isinstance(status, int)

    pod_name = spawner.pod_name

    # start the spawner
    url = await spawner.start()

    # verify the pod exists
    pods = (await kube_client.list_namespaced_pod(kube_another_ns)).items
    pod_names = [p.metadata.name for p in pods]
    assert pod_name in pod_names

    # pod should be running when start returns
    pod = await kube_client.read_namespaced_pod(
        namespace=kube_another_ns, name=pod_name
    )
    assert pod.status.phase == "Running"

    # verify poll while running
    status = await spawner.poll()
    assert status is None

    # make sure spawn url is correct
    r = await exec_python(check_up, {"url": url}, _retries=3)
    assert r == "302"

    # stop the pod
    await spawner.stop()

    # verify pod is gone
    pods = (await kube_client.list_namespaced_pod(kube_another_ns)).items
    pod_names = [p.metadata.name for p in pods]
    assert pod_name not in pod_names

    # verify exit status
    status = await spawner.poll()
    assert isinstance(status, int)


async def test_spawn_component_label_and_other_labels(
    kube_ns,
    kube_client,
    config,
    hub,
    reset_pod_reflectors,
):
    spawner = KubeSpawner(
        hub=hub,
        user=MockUser(name="start"),
        config=config,
        api_token="abc123",
        oauth_client_id="unused",
        component_label="something",
    )

    pod_name = spawner.pod_name

    # start the spawner
    await spawner.start()

    # verify the pod exists
    pods = (await kube_client.list_namespaced_pod(kube_ns)).items
    pods = [p for p in pods if p.metadata.name == pod_name]
    assert pods

    # component label is same as expected
    pod = pods[0]
    assert pod.metadata.labels["app.kubernetes.io/component"] == "something"
    assert pod.metadata.labels["component"] == "something"

    # other labels are the same as expected
    assert pod.metadata.labels["app.kubernetes.io/name"] == "jupyterhub"
    assert pod.metadata.labels["app.kubernetes.io/managed-by"] == "kubespawner"
    assert pod.metadata.labels["heritage"] == "jupyterhub"
    assert pod.metadata.labels["app"] == "jupyterhub"
    assert pod.metadata.labels["heritage"] == "jupyterhub"

    # stop the pod
    await spawner.stop()


async def test_spawn_internal_ssl(
    kube_ns,
    kube_client,
    ssl_app,
    hub_pod_ssl,
    hub_ssl,
    config,
    exec_python_pod,
):
    hub_pod_name = hub_pod_ssl.metadata.name

    spawner = KubeSpawner(
        config=config,
        hub=hub_ssl,
        user=MockUser(name="ssl"),
        api_token="abc123",
        oauth_client_id="unused",
        internal_ssl=True,
        internal_trust_bundles=ssl_app.internal_trust_bundles,
        internal_certs_location=ssl_app.internal_certs_location,
    )
    # initialize ssl config
    hub_paths = await spawner.create_certs()

    spawner.cert_paths = await spawner.move_certs(hub_paths)

    # Validate that certificates are correctly encoded
    # https://github.com/jupyterhub/kubespawner/pull/828
    manifest = spawner.get_secret_manifest(None)
    for _, secret in manifest.data.items():
        base64.b64decode(secret, validate=True)

    # start the spawner
    url = await spawner.start()
    pod_name = "jupyter-%s" % spawner.user.name
    # verify the pod exists
    pods = (await kube_client.list_namespaced_pod(kube_ns)).items
    pod_names = [p.metadata.name for p in pods]
    assert pod_name in pod_names
    # verify poll while running
    status = await spawner.poll()
    assert status is None

    # verify service and secret exist
    secret_name = spawner.secret_name
    secrets = (await kube_client.list_namespaced_secret(kube_ns)).items
    secret_names = [s.metadata.name for s in secrets]
    assert secret_name in secret_names

    service_name = pod_name
    services = (await kube_client.list_namespaced_service(kube_ns)).items
    service_names = [s.metadata.name for s in services]
    assert service_name in service_names

    # resolve internal-ssl paths in hub-ssl pod
    # these are in /etc/jupyterhub/internal-ssl
    hub_ssl_dir = "/etc/jupyterhub"
    hub_ssl_ca = os.path.join(hub_ssl_dir, ssl_app.internal_trust_bundles["hub-ca"])

    # use certipy to resolve these?
    hub_internal = os.path.join(hub_ssl_dir, "internal-ssl", "hub-internal")
    hub_internal_cert = os.path.join(hub_internal, "hub-internal.crt")
    hub_internal_key = os.path.join(hub_internal, "hub-internal.key")

    r = await exec_python_pod(
        hub_pod_name,
        check_up,
        {
            "url": url,
            "ssl_ca": hub_ssl_ca,
            "ssl_client_cert": hub_internal_cert,
            "ssl_client_key": hub_internal_key,
        },
        _retries=3,
    )
    assert r == "302"

    # stop the pod
    await spawner.stop()

    # verify pod is gone
    pods = (await kube_client.list_namespaced_pod(kube_ns)).items
    pod_names = [p.metadata.name for p in pods]
    assert "jupyter-%s" % spawner.user.name not in pod_names

    # verify service and secret are gone
    # it may take a little while for them to get cleaned up
    for i in range(5):
        secrets = (await kube_client.list_namespaced_secret(kube_ns)).items
        secret_names = {s.metadata.name for s in secrets}

        services = (await kube_client.list_namespaced_service(kube_ns)).items
        service_names = {s.metadata.name for s in services}
        if secret_name in secret_names or service_name in service_names:
            await asyncio.sleep(1)
        else:
            break
    assert secret_name not in secret_names
    assert service_name not in service_names


async def test_spawn_services_enabled(
    kube_ns,
    kube_client,
    hub,
    config,
    reset_pod_reflectors,
):
    spawner = KubeSpawner(
        config=config,
        hub=hub,
        user=MockUser(name="services"),
        api_token="abc123",
        oauth_client_id="unused",
        services_enabled=True,
        component_label="something",
        common_labels={
            "some/label": "value1",
        },
        extra_labels={
            "extra/label": "value2",
        },
    )

    # start the spawner
    await spawner.start()
    pod_name = "jupyter-%s" % spawner.user.name
    # verify the pod exists
    pods = (await kube_client.list_namespaced_pod(kube_ns)).items
    pod_names = [p.metadata.name for p in pods]
    assert pod_name in pod_names
    # verify poll while running
    status = await spawner.poll()
    assert status is None

    # verify service exist
    service_name = pod_name
    services = (await kube_client.list_namespaced_service(kube_ns)).items
    services = [s for s in services if s.metadata.name == service_name]
    assert services

    # verify selector contains component_label, common_labels and extra_labels
    # as well as user and server name
    selector = services[0].spec.selector
    assert selector["app.kubernetes.io/component"] == "something"
    assert selector["component"] == "something"
    assert selector["some/label"] == "value1"
    assert selector["extra/label"] == "value2"
    assert selector["hub.jupyter.org/servername"] == ""
    assert selector["hub.jupyter.org/username"] == "services"

    # stop the pod
    await spawner.stop()

    # verify pod is gone
    pods = (await kube_client.list_namespaced_pod(kube_ns)).items
    pod_names = [p.metadata.name for p in pods]
    assert "jupyter-%s" % spawner.user.name not in pod_names

    # verify service is gone
    # it may take a little while for them to get cleaned up
    for _ in range(5):
        services = (await kube_client.list_namespaced_service(kube_ns)).items
        service_names = {s.metadata.name for s in services}
        if service_name in service_names:
            await asyncio.sleep(1)
        else:
            break

    assert service_name not in service_names


async def test_spawn_after_pod_created_hook(
    kube_ns,
    kube_client,
    hub,
    config,
):
    async def after_pod_created_hook(spawner: KubeSpawner, pod: dict):
        owner_reference = make_owner_reference(spawner.pod_name, pod["metadata"]["uid"])

        labels = spawner._build_common_labels(spawner._expand_all(spawner.extra_labels))
        annotations = spawner._build_common_annotations(
            spawner._expand_all(spawner.extra_annotations)
        )
        selector = spawner._build_pod_labels(spawner._expand_all(spawner.extra_labels))

        service_manifest = make_service(
            name=spawner.pod_name + "-hook",
            port=spawner.port,
            selector=selector,
            owner_references=[owner_reference],
            labels=labels,
            annotations=annotations,
        )

        await exponential_backoff(
            partial(
                spawner._ensure_not_exists,
                "service",
                service_manifest.metadata.name,
            ),
            f"Failed to delete service {service_manifest.metadata.name}",
        )
        await exponential_backoff(
            partial(spawner._make_create_resource_request, "service", service_manifest),
            f"Failed to create service {service_manifest.metadata.name}",
        )

    spawner = KubeSpawner(
        config=config,
        hub=hub,
        user=MockUser(name="hook"),
        api_token="abc123",
        oauth_client_id="unused",
        after_pod_created_hook=after_pod_created_hook,
    )
    # start the spawner
    await spawner.start()
    pod_name = "jupyter-%s" % spawner.user.name
    # verify the pod exists
    pods = (await kube_client.list_namespaced_pod(kube_ns)).items
    pod_names = [p.metadata.name for p in pods]
    assert pod_name in pod_names
    # verify poll while running
    status = await spawner.poll()
    assert status is None

    # verify service exist
    service_name = pod_name + "-hook"
    services = (await kube_client.list_namespaced_service(kube_ns)).items
    service_names = [s.metadata.name for s in services]
    assert service_name in service_names

    # stop the pod
    await spawner.stop()

    # verify pod is gone
    pods = (await kube_client.list_namespaced_pod(kube_ns)).items
    pod_names = [p.metadata.name for p in pods]
    assert "jupyter-%s" % spawner.user.name not in pod_names

    # verify service is gone
    # it may take a little while for them to get cleaned up
    for _ in range(5):
        services = (await kube_client.list_namespaced_service(kube_ns)).items
        service_names = {s.metadata.name for s in services}
        if service_name in service_names:
            await asyncio.sleep(1)
        else:
            break

    assert service_name not in service_names


async def test_spawn_progress(kube_ns, kube_client, config, hub_pod, hub):
    spawner = KubeSpawner(
        hub=hub,
        user=MockUser(name="progress"),
        config=config,
    )

    # empty spawner isn't running
    status = await spawner.poll()
    assert isinstance(status, int)

    # start the spawner
    start_future = spawner.start()
    # check progress events
    messages = []
    async for progress in spawner.progress():
        assert 'progress' in progress
        assert isinstance(progress['progress'], int)
        assert 'message' in progress
        assert isinstance(progress['message'], str)
        messages.append(progress['message'])

        # ensure we can serialize whatever we return
        with open(os.devnull, "w") as devnull:
            json.dump(progress, devnull)
    assert 'Started container' in '\n'.join(messages)

    await start_future
    # stop the pod
    await spawner.stop()


async def test_spawn_start_restore_pod_name(
    kube_ns,
    kube_client,
    config,
    hub,
    exec_python,
):
    # Emulate stopping Jupyterhub and starting with different settings while some pods still exist

    # Save state with old config
    old_spawner = KubeSpawner(
        hub=hub,
        user=MockUser(name="start"),
        config=config,
        api_token="abc123",
        oauth_client_id="unused",
    )
    old_spawner_pod_name = old_spawner.pod_name

    # create reflector
    await old_spawner.start()
    old_state = old_spawner.get_state()
    await old_spawner.stop()

    # Change config
    config.KubeSpawner.pod_name_template = 'new-{username}--{servername}'

    # Load old state
    spawner = KubeSpawner(
        hub=hub,
        user=MockUser(name="start"),
        config=config,
        api_token="abc123",
        oauth_client_id="unused",
    )
    spawner.load_state(old_state)

    # previous pod name is restored by the load_state call
    assert spawner.pod_name == old_spawner_pod_name

    # empty spawner isn't running
    status = await spawner.poll()
    assert isinstance(status, int)

    pod_name = spawner.pod_name

    # start the spawner
    url = await spawner.start()

    # verify pod with old name now exists
    pods = (await kube_client.list_namespaced_pod(kube_ns)).items
    pod_names = [p.metadata.name for p in pods]
    assert pod_name in pod_names

    # pod should be running when start returns
    pod = await kube_client.read_namespaced_pod(namespace=kube_ns, name=pod_name)
    assert pod.status.phase == "Running"

    # verify poll while running
    status = await spawner.poll()
    assert status is None

    # make sure spawn url is correct
    r = await exec_python(check_up, {"url": url}, _retries=3)
    assert r == "302"

    # stop the pod
    await spawner.stop()

    # verify pod with old name is gone
    pods = (await kube_client.list_namespaced_pod(kube_ns)).items
    pod_names = [p.metadata.name for p in pods]
    assert pod_name not in pod_names

    # verify exit status
    status = await spawner.poll()
    assert isinstance(status, int)


@pytest.mark.parametrize("enable_user_namespaces", [True, False])
async def test_spawn_start_restore_namespace(
    kube_ns,
    kube_another_ns,
    kube_client,
    config,
    hub,
    exec_python,
    enable_user_namespaces,
):
    # Emulate stopping Jupyterhub and starting with different settings with existing pods

    config.KubeSpawner.enable_user_namespaces = enable_user_namespaces

    # Save state with old config
    config.KubeSpawner.namespace = kube_another_ns
    config.KubeSpawner.user_namespace_template = kube_another_ns

    old_spawner = KubeSpawner(
        hub=hub,
        user=MockUser(name="start"),
        config=config,
        api_token="abc123",
        oauth_client_id="unused",
    )
    old_spawner_namespace = old_spawner.namespace

    # create reflector with old namespace
    await old_spawner.start()
    old_state = old_spawner.get_state()
    await old_spawner.stop()

    # Save config
    config.KubeSpawner.namespace = kube_ns
    config.KubeSpawner.user_namespace_template = kube_ns

    # Load old state
    spawner = KubeSpawner(
        hub=hub,
        user=MockUser(name="start"),
        config=config,
        api_token="abc123",
        oauth_client_id="unused",
    )
    spawner.load_state(old_state)

    # previous namespace is restored
    # KubeSpawner should properly run on a different namespace
    assert spawner.namespace == old_spawner_namespace

    # empty spawner isn't running
    status = await spawner.poll()
    assert isinstance(status, int)

    pod_name = spawner.pod_name

    # start the spawner
    url = await spawner.start()

    # verify the pod exists
    pods = (await kube_client.list_namespaced_pod(kube_another_ns)).items
    pod_names = [p.metadata.name for p in pods]
    assert pod_name in pod_names

    # pod should be running when start returns
    pod = await kube_client.read_namespaced_pod(
        namespace=kube_another_ns, name=pod_name
    )
    assert pod.status.phase == "Running"

    # verify poll while running
    status = await spawner.poll()
    assert status is None

    # make sure spawn url is correct
    r = await exec_python(check_up, {"url": url}, _retries=3)
    assert r == "302"

    # stop the pod
    await spawner.stop()

    # verify pod is gone
    pods = (await kube_client.list_namespaced_pod(kube_another_ns)).items
    pod_names = [p.metadata.name for p in pods]
    assert pod_name not in pod_names

    # verify exit status
    status = await spawner.poll()
    assert isinstance(status, int)


@pytest.mark.parametrize("handle_legacy_names", [True, False])
async def test_spawn_start_upgrade_pvc_name(
    config,
    hub,
    handle_legacy_names,
):
    # Emulate stopping JupyterHub and starting with different settings while some pods still exist
    user = MockUser(name="needs-Escape")
    spawner_args = dict(
        hub=hub,
        user=user,
        orm_spawner=MockOrmSpawner(),
        config=config,
        api_token="abc123",
        oauth_client_id="unused",
    )
    config.KubeSpawner.storage_pvc_ensure = True
    config.KubeSpawner.storage_capacity = "100M"
    config.KubeSpawner.slug_scheme = "escape"
    config.KubeSpawner.handle_legacy_names = handle_legacy_names

    # Save state with old config
    old_spawner = KubeSpawner(
        **spawner_args, pvc_name_template="claim-{username}--{servername}"
    )
    old_spawner.load_state({})
    assert old_spawner._state_kubespawner_version is None

    old_spawner_pvc_name = old_spawner.pvc_name

    # launch old pod
    await old_spawner.start()
    assert old_spawner._pvc_exists
    old_state = old_spawner.get_state()
    # subset keys to what's actually stored in earlier versions of kubespawner
    old_state = {key: old_state[key] for key in ("namespace", "pod_name", "dns_name")}

    await old_spawner.stop()

    # Change config
    config.KubeSpawner.slug_scheme = "safe"

    # Load old state
    spawner = KubeSpawner(**spawner_args)
    spawner.load_state(old_state)
    assert spawner._state_kubespawner_version == "unknown"
    # value changed from config
    new_spawner_pvc_name = spawner.pvc_name
    assert spawner.pvc_name != old_spawner_pvc_name
    # start checks for old name and uses it if it exists
    await spawner.start()
    if handle_legacy_names:
        assert spawner.pvc_name == old_spawner_pvc_name
    else:
        assert spawner.pvc_name == new_spawner_pvc_name
    assert spawner._pvc_exists
    await spawner.stop()
    new_state = spawner.get_state()
    assert new_state["pvc_name"] == spawner.pvc_name

    # one more time, this time shouldn't need to call _check_pvc_exists
    config.KubeSpawner.pvc_name_template = "shouldnt-be-used"
    spawner = KubeSpawner(**spawner_args)

    def _shouldnt_check():
        pytest.fail("shouldn't have called _check_pvc_exists")

    spawner._check_pvc_exists = _shouldnt_check
    spawner.load_state(new_state)
    assert spawner._pvc_exists
    assert spawner._state_kubespawner_version == kubespawner.__version__

    await spawner.start()
    assert spawner.pvc_name == new_state["pvc_name"]
    assert spawner._pvc_exists
    await spawner.stop()


async def test_get_pod_manifest_tolerates_mixed_input():
    """
    Test that the get_pod_manifest function can handle a either a dictionary or
    an object both representing V1Container objects and that the function
    returns a V1Pod object containing V1Container objects.
    """
    c = Config()

    dict_model = {
        'name': 'mock_name_1',
        'image': 'mock_image_1',
        'command': ['mock_command_1'],
    }
    object_model = V1Container(
        name="mock_name_2",
        image="mock_image_2",
        command=['mock_command_2'],
        security_context=V1SecurityContext(
            privileged=True,
            run_as_user=0,
            capabilities=V1Capabilities(add=['NET_ADMIN']),
        ),
    )
    c.KubeSpawner.init_containers = [dict_model, object_model]

    spawner = KubeSpawner(config=c, _mock=True)

    # this test ensures the following line doesn't raise an error
    manifest = await spawner.get_pod_manifest()

    # and tests the return value's types
    assert isinstance(manifest, V1Pod)
    assert isinstance(manifest.spec.init_containers[0], V1Container)
    assert isinstance(manifest.spec.init_containers[1], V1Container)


async def test_expansion_hyphens():
    c = Config()

    c.KubeSpawner.init_containers = [
        {
            'name': 'mock_name_1',
            'image': 'mock_image_1',
            'command': [
                'mock_command_1',
                '--',
                '{unescaped_username}',
                '{unescaped_username}-',
                '-x',
            ],
        }
    ]

    spawner = KubeSpawner(config=c, _mock=True)

    # this test ensures the following line doesn't raise an error
    manifest = await spawner.get_pod_manifest()
    assert isinstance(manifest, V1Pod)
    container = manifest.spec.init_containers[0]
    assert isinstance(container, V1Container)

    assert container.command == [
        'mock_command_1',
        '--',
        spawner.user.name,
        spawner.user.name + "-",
        '-x',
    ]


async def test_init_containers_as_dict():
    """
    Test that the init_containers config option can be a dictionary of lists
    and the values are sorted by key before being added to the pod manifest.
    """
    c = Config()

    c.KubeSpawner.init_containers = {
        '02-beta': {
            'name': 'mock_name_2',
            'image': 'mock_image_2',
            'command': ['mock_command_2'],
        },
        '01-alpha': {
            'name': 'mock_name_1',
            'image': 'mock_image_1',
            'command': ['mock_command_1'],
        },
    }

    spawner = KubeSpawner(config=c, _mock=True)

    manifest = await spawner.get_pod_manifest()
    assert isinstance(manifest, V1Pod)
    init_containers = manifest.spec.init_containers
    assert len(init_containers) == 2
    for container in init_containers:
        assert isinstance(container, V1Container)

    assert init_containers[0].name == 'mock_name_1'
    assert init_containers[1].name == 'mock_name_2'
    assert init_containers[0].image == 'mock_image_1'
    assert init_containers[1].image == 'mock_image_2'


_test_profiles = [
    {
        'display_name': 'Training Env - Python',
        'slug': 'training-python',
        'default': True,
        'kubespawner_override': {
            'image': 'training/python:label',
            'cpu_limit': 1,
            'mem_limit': 512 * 1024 * 1024,
            'environment': {'override': 'override-value'},
        },
    },
    {
        'display_name': 'Training Env - Datascience',
        'slug': 'training-datascience',
        'kubespawner_override': {
            'image': 'training/datascience:label',
            'cpu_limit': 4,
            'mem_limit': 8 * 1024 * 1024 * 1024,
        },
    },
    {
        'display_name': 'Training Env - R',
        'slug': 'training-r',
        'kubespawner_override': {
            'image': 'training/r:label',
            'cpu_limit': 1,
            'mem_limit': 512 * 1024 * 1024,
            'environment': {'override': 'override-value', "to-remove": None},
        },
    },
    {
        'display_name': 'Test choices',
        'slug': 'test-choices',
        'profile_options': {
            'image': {
                'display_name': 'Image',
                'unlisted_choice': {
                    'enabled': True,
                    'display_name': 'Image Location',
                    'validation_regex': '^pangeo/.*$',
                    'validation_message': 'Must be a pangeo image, matching ^pangeo/.*$',
                    'kubespawner_override': {'image': '{value}'},
                },
                'choices': {
                    'pytorch': {
                        'display_name': 'Python 3 Training Notebook',
                        'kubespawner_override': {
                            'image': 'pangeo/pytorch-notebook:master'
                        },
                    },
                    'tf': {
                        'display_name': 'R 4.2 Training Notebook',
                        'default': True,
                        'kubespawner_override': {'image': 'training/r:label'},
                    },
                },
            },
        },
    },
    {
        'display_name': 'Test choices no regex',
        'slug': 'no-regex',
        'profile_options': {
            'image': {
                'display_name': 'Image',
                'unlisted_choice': {
                    'enabled': True,
                    'display_name': 'Image Location',
                    'kubespawner_override': {'image': '{value}'},
                },
                'choices': {
                    'pytorch': {
                        'display_name': 'Python 3 Training Notebook',
                        'kubespawner_override': {
                            'image': 'pangeo/pytorch-notebook:master'
                        },
                    },
                    'tf': {
                        'display_name': 'R 4.2 Training Notebook',
                        'default': True,
                        'kubespawner_override': {'image': 'training/r:label'},
                    },
                },
            },
        },
    },
]


async def test_user_options_set_from_form():
    spawner = KubeSpawner(_mock=True)
    spawner.profile_list = _test_profiles
    # render the form
    await spawner.get_options_form()
    spawner.user_options = spawner.options_from_form(
        {'profile': [_test_profiles[1]['slug']]}
    )
    assert spawner.user_options == {
        'profile': _test_profiles[1]['slug'],
    }
    # nothing should be loaded yet
    assert spawner.cpu_limit is None
    await spawner.load_user_options()
    for key, value in _test_profiles[1]['kubespawner_override'].items():
        assert getattr(spawner, key) == value


async def test_user_options_set_from_form_choices():
    """
    Test that the `choices` field in profile_options is processed correctly -
    i.e. when a user sends a profile option choice, it is correctly processed
    in user_options and the value on the spawner correctly over-ridden by the user choice.
    """
    spawner = KubeSpawner(_mock=True)
    spawner.profile_list = _test_profiles
    await spawner.get_options_form()
    spawner.user_options = spawner.options_from_form(
        {
            'profile': [_test_profiles[3]['slug']],
            'profile-option-test-choices--image': ['pytorch'],
        }
    )
    assert spawner.user_options == {
        'image': 'pytorch',
        'profile': _test_profiles[3]['slug'],
    }
    assert spawner.cpu_limit is None
    await spawner.load_user_options()
    assert getattr(spawner, 'image') == 'pangeo/pytorch-notebook:master'


async def test_user_options_set_from_form_unlisted_choice():
    """
    Test that when user sends an arbitrary text input in the `unlisted_choice` field,
    it is process correctly and the correct attribute over-ridden on the spawner.
    """
    spawner = KubeSpawner(_mock=True)
    spawner.profile_list = _test_profiles
    await spawner.get_options_form()
    spawner.user_options = spawner.options_from_form(
        {
            'profile': [_test_profiles[3]['slug']],
            'profile-option-test-choices--image--unlisted-choice': [
                'pangeo/test:latest'
            ],
        }
    )
    assert spawner.user_options == {
        'image--unlisted-choice': 'pangeo/test:latest',
        'profile': _test_profiles[3]['slug'],
    }
    assert spawner.cpu_limit is None
    await spawner.load_user_options()
    assert getattr(spawner, 'image') == 'pangeo/test:latest'

    # Test choosing an unlisted choice a second time
    spawner.user_options = spawner.options_from_form(
        {
            'profile': [_test_profiles[3]['slug']],
            'profile-option-test-choices--image--unlisted-choice': [
                'pangeo/test:1.2.3'
            ],
        }
    )
    assert spawner.user_options == {
        'image--unlisted-choice': 'pangeo/test:1.2.3',
        'profile': _test_profiles[3]['slug'],
    }
    assert spawner.cpu_limit is None
    await spawner.load_user_options()
    assert getattr(spawner, 'image') == 'pangeo/test:1.2.3'


async def test_user_options_set_from_form_invalid_regex():
    """
    Test that if the user input for the `unlisted-choice` field does not match the regex
    specified in the `validation_match_regex` option for the `unlisted_choice`, a ValueError is raised.
    """
    spawner = KubeSpawner(_mock=True)
    spawner.profile_list = _test_profiles
    await spawner.get_options_form()
    spawner.user_options = spawner.options_from_form(
        {
            'profile': [_test_profiles[3]['slug']],
            'profile-option-test-choices--image--unlisted-choice': [
                'invalid/foo:latest'
            ],
        }
    )
    assert spawner.user_options == {
        'image--unlisted-choice': 'invalid/foo:latest',
        'profile': _test_profiles[3]['slug'],
    }
    assert spawner.cpu_limit is None

    with pytest.raises(ValueError):
        await spawner.load_user_options()


async def test_user_options_set_from_form_no_regex():
    """
    Test that if the `unlisted_choice` object in the profile_options does not contain
    a `validation_regex` key, no validation is done and the input is correctly processed - i.e. validation_regex is optional.
    """
    spawner = KubeSpawner(_mock=True)
    spawner.profile_list = _test_profiles
    await spawner.get_options_form()
    # print(_test_profiles[4])
    spawner.user_options = spawner.options_from_form(
        {
            'profile': [_test_profiles[4]['slug']],
            'profile-option-no-regex--image--unlisted-choice': ['invalid/foo:latest'],
        }
    )
    assert spawner.user_options == {
        'image--unlisted-choice': 'invalid/foo:latest',
        'profile': _test_profiles[4]['slug'],
    }
    assert spawner.cpu_limit is None
    await spawner.load_user_options()
    assert getattr(spawner, 'image') == 'invalid/foo:latest'


async def test_kubespawner_override():
    spawner = KubeSpawner(_mock=True)
    spawner.profile_list = _test_profiles
    # Set a base environment
    # to-remove will be removed because we set its value to None
    # in the override
    spawner.environment = {"existing": "existing-value", "to-remove": "does-it-matter"}
    # render the form, select first option
    await spawner.get_options_form()
    spawner.user_options = spawner.options_from_form(
        {'profile': [_test_profiles[2]['slug']]}
    )
    assert spawner.user_options == {
        'profile': _test_profiles[2]['slug'],
    }
    await spawner.load_user_options()
    assert spawner.environment == {
        "existing": "existing-value",
        "override": "override-value",
    }


async def test_user_options_api():
    spawner = KubeSpawner(_mock=True)
    spawner.profile_list = _test_profiles
    # set user_options directly (e.g. via api)
    spawner.user_options = {'profile': _test_profiles[1]['slug']}

    # nothing should be loaded yet
    assert spawner.cpu_limit is None
    await spawner.load_user_options()
    for key, value in _test_profiles[1]['kubespawner_override'].items():
        assert getattr(spawner, key) == value


async def test_default_profile():
    spawner = KubeSpawner(_mock=True)
    spawner.profile_list = _test_profiles
    spawner.user_options = {}
    # nothing should be loaded yet
    assert spawner.cpu_limit is None
    await spawner.load_user_options()
    for key, value in _test_profiles[0]['kubespawner_override'].items():
        assert getattr(spawner, key) == value


async def test_spawn_start_profile_list_override_namespace(
    kube_another_ns,
    kube_client,
    config,
    hub,
    exec_python,
):
    # Emulate case when different profiles create objects in different namespaces

    profiles = [
        {
            'display_name': 'Default namespace - Python',
            'slug': 'default-namespace',
            'default': True,
            'kubespawner_override': {
                'cpu_limit': 1,
            },
        },
        {
            'display_name': 'Different namespace - Python',
            'slug': 'different-namespace',
            'default': False,
            'kubespawner_override': {
                'namespace': kube_another_ns,
                'cpu_limit': 1,
            },
        },
    ]

    config.KubeSpawner.profile_list = profiles

    spawner = KubeSpawner(
        hub=hub,
        user=MockUser(name="start"),
        config=config,
        api_token="abc123",
        oauth_client_id="unused",
    )
    # set user_options (via form or API)
    spawner.user_options = {'profile': profiles[1]['slug']}

    # empty spawner isn't running
    status = await spawner.poll()
    assert isinstance(status, int)

    pod_name = spawner.pod_name

    # start the spawner
    url = await spawner.start()

    # pod started in namespace which is different from constructor

    # verify the pod exists
    pods = (await kube_client.list_namespaced_pod(kube_another_ns)).items
    pod_names = [p.metadata.name for p in pods]
    assert pod_name in pod_names

    # pod should be running when start returns
    pod = await kube_client.read_namespaced_pod(
        namespace=kube_another_ns, name=pod_name
    )
    assert pod.status.phase == "Running"

    # verify poll while running
    status = await spawner.poll()
    assert status is None

    # make sure spawn url is correct
    r = await exec_python(check_up, {"url": url}, _retries=3)
    assert r == "302"

    # stop the pod
    await spawner.stop()

    # verify pod is gone
    pods = (await kube_client.list_namespaced_pod(kube_another_ns)).items
    pod_names = [p.metadata.name for p in pods]
    assert pod_name not in pod_names

    # verify exit status
    status = await spawner.poll()
    assert isinstance(status, int)


async def test_spawn_start_profile_callback_override_namespace(
    kube_ns,
    kube_another_ns,
    kube_client,
    config,
    hub,
    exec_python,
):
    def get_profile(spawner):
        return [
            {
                'display_name': 'Default namespace - Python',
                'slug': 'default-namespace',
                'default': True,
                'kubespawner_override': {
                    'cpu_limit': 1,
                },
            },
            {
                'display_name': 'Different namespace - Python',
                'slug': 'different-namespace',
                'default': False,
                'kubespawner_override': {
                    'namespace': kube_another_ns,
                    'cpu_limit': 1,
                },
            },
        ]

    config.KubeSpawner.profile_list = get_profile

    # It does not matter if namespace is set explicitly or generated from a template,
    # checking enable_user_namespaces=True only to cover case with one reflector per all namespaces
    config.KubeSpawner.enable_user_namespaces = True
    config.KubeSpawner.user_namespace_template = kube_ns

    spawner = KubeSpawner(
        hub=hub,
        user=MockUser(name="start"),
        config=config,
        api_token="abc123",
        oauth_client_id="unused",
    )
    # set user_options (via form or API)
    spawner.user_options = {'profile': 'different-namespace'}

    # empty spawner isn't running
    status = await spawner.poll()
    assert isinstance(status, int)

    pod_name = spawner.pod_name

    # start the spawner
    url = await spawner.start()

    # pod started in namespace which is different from constructor

    # verify the pod exists
    pods = (await kube_client.list_namespaced_pod(kube_another_ns)).items
    pod_names = [p.metadata.name for p in pods]
    assert pod_name in pod_names

    # pod should be running when start returns
    pod = await kube_client.read_namespaced_pod(
        namespace=kube_another_ns, name=pod_name
    )
    assert pod.status.phase == "Running"

    # verify poll while running
    status = await spawner.poll()
    assert status is None

    # make sure spawn url is correct
    r = await exec_python(check_up, {"url": url}, _retries=3)
    assert r == "302"

    # stop the pod
    await spawner.stop()

    # verify pod is gone
    pods = (await kube_client.list_namespaced_pod(kube_another_ns)).items
    pod_names = [p.metadata.name for p in pods]
    assert pod_name not in pod_names

    # verify exit status
    status = await spawner.poll()
    assert isinstance(status, int)


async def test_pod_name_no_named_servers():
    c = Config()
    c.JupyterHub.allow_named_servers = False

    user = Config()
    user.name = "user"

    orm_spawner = Spawner()

    spawner = KubeSpawner(config=c, user=user, orm_spawner=orm_spawner, _mock=True)

    assert spawner.pod_name == "jupyter-user"


async def test_spawner_env():
    c = Config()
    c.Spawner.environment = {
        "STATIC": "static",
        "EXPANDED": "{username} (expanded)",
        "ESCAPED": "{{username}}",
        "CALLABLE": lambda spawner: spawner.user.name + " (callable)",
    }
    spawner = KubeSpawner(config=c, _mock=True)
    slug = safe_slug(spawner.user.name)
    env = spawner.get_env()
    assert env["STATIC"] == "static"
    assert env["EXPANDED"] == f"{slug} (expanded)"
    assert env["ESCAPED"] == "{username}"
    assert env["CALLABLE"] == "mock@name (callable)"


async def test_jupyterhub_supplied_env():
    cookie_options = {"samesite": "None", "secure": True}
    c = Config()

    c.KubeSpawner.environment = {"HELLO": "It's {unescaped_username}"}
    spawner = KubeSpawner(config=c, _mock=True, cookie_options=cookie_options)

    pod_manifest = await spawner.get_pod_manifest()

    env = pod_manifest.spec.containers[0].env

    # Set via .environment, must be expanded
    assert V1EnvVar("HELLO", "It's mock@name") in env
    # Set by JupyterHub itself, must not be expanded
    assert V1EnvVar("JUPYTERHUB_COOKIE_OPTIONS", json.dumps(cookie_options)) in env


async def test_pod_name_named_servers():
    c = Config()
    c.JupyterHub.allow_named_servers = True

    user = Config()
    user.name = "user"

    orm_spawner = Spawner()
    orm_spawner.name = "server"

    spawner = KubeSpawner(config=c, user=user, orm_spawner=orm_spawner, _mock=True)

    assert spawner.pod_name == "jupyter-user--server"


async def test_pod_name_escaping():
    c = Config()
    c.JupyterHub.allow_named_servers = True

    user = Config()
    user.name = "some_user"

    orm_spawner = Spawner()
    orm_spawner.name = "test-server!"

    spawner = KubeSpawner(config=c, user=user, orm_spawner=orm_spawner, _mock=True)

    assert spawner.pod_name == "jupyter-some-user---7d3a4d4e--test-server---cb54a9af"


async def test_pod_name_custom_template():
    user = MockUser()
    user.name = "some_user"

    pod_name_template = "prefix-{user_server}-suffix"

    spawner = KubeSpawner(user=user, pod_name_template=pod_name_template, _mock=True)

    assert spawner.pod_name == "prefix-some-user---7d3a4d4e-suffix"


async def test_pod_name_collision():
    user1 = MockUser()
    user1.name = "user-has-dash"

    orm_spawner1 = Spawner()
    orm_spawner1.name = ""

    user2 = MockUser()
    user2.name = "user-has"
    orm_spawner2 = Spawner()
    orm_spawner2.name = "dash"

    spawner = KubeSpawner(user=user1, orm_spawner=orm_spawner1, _mock=True)
    assert spawner.pod_name == "jupyter-user-has-dash"
    assert spawner.pvc_name == "claim-user-has-dash"
    named_spawner = KubeSpawner(user=user2, orm_spawner=orm_spawner2, _mock=True)
    assert named_spawner.pod_name == "jupyter-user-has--dash"
    assert spawner.pod_name != named_spawner.pod_name
    assert named_spawner.pvc_name == "claim-user-has--dash"
    assert spawner.pvc_name != named_spawner.pvc_name


async def test_spawner_can_use_list_of_image_pull_secrets():
    secrets = ["ecr", "regcred", "artifactory"]

    c = Config()
    c.KubeSpawner.image_spec = "private.docker.registry/jupyter:1.2.3"
    c.KubeSpawner.image_pull_secrets = secrets
    spawner = KubeSpawner(hub=Hub(), config=c, _mock=True)
    assert spawner.image_pull_secrets == secrets

    secrets = [dict(name=secret) for secret in secrets]
    c = Config()
    c.KubeSpawner.image_spec = "private.docker.registry/jupyter:1.2.3"
    c.KubeSpawner.image_pull_secrets = secrets
    spawner = KubeSpawner(hub=Hub(), config=c, _mock=True)
    assert spawner.image_pull_secrets == secrets


async def test_pod_connect_ip(kube_ns, kube_client, config, hub_pod, hub):
    config.KubeSpawner.pod_connect_ip = (
        "jupyter-{username}--{servername}.foo.example.com"
    )

    user = MockUser(name="connectip")
    # w/o servername
    spawner = KubeSpawner(hub=hub, user=user, config=config)

    # start the spawner
    res = await spawner.start()
    # verify the pod IP and port

    assert res == "http://jupyter-connectip.foo.example.com:8888"

    await spawner.stop()

    # w/ servername

    spawner = KubeSpawner(
        hub=hub,
        user=user,
        config=config,
        orm_spawner=MockOrmSpawner(),
    )

    # start the spawner
    res = await spawner.start()
    # verify the pod IP and port

    assert res == "http://jupyter-connectip--server.foo.example.com:8888"
    await spawner.stop()


async def test_get_pvc_manifest():
    c = Config()

    username = "mock@name"
    slug = safe_slug(username)
    c.KubeSpawner.pvc_name_template = "user-{username}"
    c.KubeSpawner.storage_extra_labels = {"user": "{username}"}
    c.KubeSpawner.storage_extra_annotations = {"user": "{username}"}
    c.KubeSpawner.storage_selector = {"matchLabels": {"user": "{username}"}}

    spawner = KubeSpawner(config=c, _mock=True)

    manifest = spawner.get_pvc_manifest()

    assert isinstance(manifest, V1PersistentVolumeClaim)
    assert manifest.metadata.name == f"user-{slug}"
    assert manifest.metadata.labels == {
        "user": slug,
        "hub.jupyter.org/username": slug,
        "app.kubernetes.io/name": "jupyterhub",
        "app.kubernetes.io/managed-by": "kubespawner",
        "app.kubernetes.io/component": "singleuser-server",
        "app": "jupyterhub",
        "heritage": "jupyterhub",
        "component": "singleuser-storage",
    }
    assert manifest.metadata.annotations == {
        "user": slug,
        "hub.jupyter.org/username": username,
        "hub.jupyter.org/jupyterhub-version": jupyterhub.__version__,
        "hub.jupyter.org/kubespawner-version": kubespawner.__version__,
    }
    assert manifest.spec.selector == {"matchLabels": {"user": slug}}


async def test_variable_expansion(ssl_app):
    """
    Variable expansion not tested here:
    - pod_connect_ip: is tested in test_url_changed
    - user_namespace_template: isn't tested because it isn't set as part of the
      Pod manifest but.
    """
    config_to_test = {
        "pod_name_template": {
            "configured_value": "pod-name-template-{username}",
            "findable_in": ["pod"],
        },
        "pvc_name_template": {
            "configured_value": "pvc-name-template-{username}",
            "findable_in": ["pvc"],
        },
        "secret_name_template": {
            "configured_value": "secret-name-template-{username}",
            "findable_in": ["secret"],
        },
        "storage_selector": {
            "configured_value": {
                "matchLabels": {"dummy": "storage-selector-{username}"}
            },
            "findable_in": ["pvc"],
        },
        "storage_extra_labels": {
            "configured_value": {"dummy": "storage-extra-labels-{username}"},
            "findable_in": ["pvc"],
        },
        "storage_extra_annotations": {
            "configured_value": {"dummy": "storage-extra-annotations-{username}"},
            "findable_in": ["pvc"],
        },
        "extra_labels": {
            "configured_value": {"dummy": "common-extra-labels-{username}"},
            "findable_values": ["common-extra-labels-user1"],
            "findable_in": ["pod", "service", "secret"],
        },
        "extra_annotations": {
            "configured_value": {"dummy": "common-extra-annotations-{username}"},
            "findable_values": ["common-extra-annotations-user1"],
            "findable_in": ["pod", "service", "secret"],
        },
        "working_dir": {
            "configured_value": "working-dir-{username}",
            "findable_in": ["pod"],
        },
        "service_account": {
            "configured_value": "service-account-{username}",
            "findable_in": ["pod"],
        },
        "volumes": {
            "configured_value": [
                {
                    'name': 'volumes-{username}',
                    'secret': {'secretName': 'dummy'},
                }
            ],
            "findable_in": ["pod"],
        },
        "volume_mounts": {
            "configured_value": [
                {
                    'name': 'volume-mounts-{username}',
                    'mountPath': '/tmp/',
                }
            ],
            "findable_in": ["pod"],
        },
        "environment": {
            "configured_value": {
                'VAR1': 'VAR1-{username}',
                'VAR2': {
                    'value': 'VAR2-{username}',
                },
                'VAR3': {
                    'valueFrom': {
                        'secretKeyRef': {
                            'name': 'VAR3-SECRET-{username}',
                            'key': 'VAR3-KEY-{username}',
                        },
                    },
                },
                'VAR4': 'VAR4-{{username}}-{{SHELL}}',
            },
            "findable_values": [
                "VAR1-user1",
                "VAR2-user1",
                "VAR3-SECRET-user1",
                "VAR3-KEY-user1",
                "VAR4-{username}-{SHELL}",
            ],
            "findable_in": ["pod"],
        },
        "init_containers": {
            "configured_value": [
                {
                    'name': 'init-containers-{username}',
                    'image': 'busybox',
                }
            ],
            "findable_in": ["pod"],
        },
        "extra_containers": {
            "configured_value": [
                {
                    'name': 'extra-containers-{username}',
                    'image': 'busybox',
                }
            ],
            "findable_in": ["pod"],
        },
        "extra_pod_config": {
            "configured_value": {"schedulerName": "extra-pod-config-{username}"},
            "findable_in": ["pod"],
        },
    }

    c = Config()
    for key, value in config_to_test.items():
        c.KubeSpawner[key] = value["configured_value"]

        if "findable_values" not in value:
            value["findable_values"] = [key.replace("_", "-") + "-user1"]

    user = MockUser(name="user1")
    spawner = KubeSpawner(
        config=c,
        user=user,
        internal_trust_bundles=ssl_app.internal_trust_bundles,
        internal_certs_location=ssl_app.internal_certs_location,
        _mock=True,
    )
    hub_paths = await spawner.create_certs()
    spawner.cert_paths = await spawner.move_certs(hub_paths)

    manifests = {
        "pod": await spawner.get_pod_manifest(),
        "pvc": spawner.get_pvc_manifest(),
        "secret": spawner.get_secret_manifest("dummy-owner-ref"),
        "service": spawner.get_service_manifest("dummy-owner-ref"),
    }

    for resource_kind, manifest in manifests.items():
        manifest_string = str(manifest)
        for config in config_to_test.values():
            if resource_kind in config["findable_in"]:
                for value in config["findable_values"]:
                    assert value in manifest_string, (
                        manifest_string
                        + "\n\n"
                        + "findable_value: "
                        + value
                        + "\n"
                        + "resource_kind: "
                        + resource_kind
                    )


async def test_url_changed(kube_ns, kube_client, config, hub_pod, hub):
    user = MockUser(name="url")
    config.KubeSpawner.pod_connect_ip = (
        "jupyter-{username}--{servername}.foo.example.com"
    )
    spawner = KubeSpawner(hub=hub, user=user, config=config)
    spawner.db = Mock()

    # start the spawner
    res = await spawner.start()
    pod_host = "http://jupyter-url.foo.example.com:8888"
    assert res == pod_host

    # Mock an incorrect value in the db
    # Can occur e.g. by interrupting a launch with a hub restart
    # or possibly weird network things in kubernetes
    spawner.server = Server.from_url(res + "/users/url/")
    spawner.server.ip = "1.2.3.4"
    spawner.server.port = 0
    assert spawner.server.host == "http://1.2.3.4:0"
    assert spawner.server.base_url == "/users/url/"

    # poll checks the url, and should restore the correct value
    await spawner.poll()
    # verify change noticed and persisted to db
    assert spawner.server.host == pod_host
    assert spawner.db.commit.call_count == 1
    # base_url should be left alone
    assert spawner.server.base_url == "/users/url/"

    previous_commit_count = spawner.db.commit.call_count
    # run it again, to make sure we aren't incorrectly detecting and committing
    # changes on every poll
    await spawner.poll()
    assert spawner.db.commit.call_count == previous_commit_count

    await spawner.stop()


async def test_delete_pvc(kube_ns, kube_client, hub, config):
    config.KubeSpawner.storage_pvc_ensure = True
    config.KubeSpawner.storage_capacity = '1M'

    spawner = KubeSpawner(
        hub=hub,
        user=MockUser(name="mockuser"),
        config=config,
        _mock=True,
    )
    spawner.api = kube_client

    # start the spawner
    await spawner.start()

    # verify the pod exists
    pod_name = "jupyter-%s" % spawner.user.name
    pods = (await kube_client.list_namespaced_pod(kube_ns)).items
    pod_names = [p.metadata.name for p in pods]
    assert pod_name in pod_names

    # verify PVC is created
    pvc_name = spawner.pvc_name
    pvc_list = (
        await kube_client.list_namespaced_persistent_volume_claim(kube_ns)
    ).items
    pvc_names = [s.metadata.name for s in pvc_list]
    assert pvc_name in pvc_names

    # stop the pod
    await spawner.stop()

    # verify pod is gone
    pods = (await kube_client.list_namespaced_pod(kube_ns)).items
    pod_names = [p.metadata.name for p in pods]
    assert "jupyter-%s" % spawner.user.name not in pod_names

    # delete the PVC
    await spawner.delete_forever()

    # verify PVC is deleted, it may take a little while
    for i in range(5):
        pvc_list = (
            await kube_client.list_namespaced_persistent_volume_claim(kube_ns)
        ).items
        pvc_names = [s.metadata.name for s in pvc_list]
        if pvc_name in pvc_names:
            await asyncio.sleep(1)
        else:
            break
    assert pvc_name not in pvc_names


async def test_ipv6_addr():
    """make sure ipv6 addresses are templated into URL correctly"""
    # https://github.com/jupyterhub/jupyterhub/pull/3020
    # https://github.com/jupyterhub/kubespawner/pull/619

    spawner = KubeSpawner(
        _mock=True,
    )
    url = spawner._get_pod_url({"status": {"podIP": "cafe:f00d::"}})
    assert "[" in url and "]" in url


async def test_volume_mount_dictionary():
    """
    Test that volume_mounts can be a dictionary of dictionaries.
    The output list should be lexicographically sorted by key.
    """
    c = Config()

    c.KubeSpawner.volume_mounts = {
        "02-group-beta": {
            'name': 'volume-mounts-beta',
            'mountPath': '/beta/',
        },
        "01-group-alpha": {
            'name': 'volume-mounts-alpha',
            'mountPath': '/alpha/',
        },
    }

    spawner = KubeSpawner(config=c, _mock=True)

    manifest = await spawner.get_pod_manifest()

    assert isinstance(manifest.spec.containers[0].volume_mounts, list)
    assert manifest.spec.containers[0].volume_mounts[0].name == 'volume-mounts-alpha'
    assert manifest.spec.containers[0].volume_mounts[0].mount_path == '/alpha/'
    assert manifest.spec.containers[0].volume_mounts[1].name == 'volume-mounts-beta'
    assert manifest.spec.containers[0].volume_mounts[1].mount_path == '/beta/'


async def test_volume_mount_list():
    """
    Test that volume_mounts can be a list of dictionaries for backwards compatibility.
    """
    c = Config()

    c.KubeSpawner.volume_mounts = [
        {
            'name': 'volume-mounts-alpha',
            'mountPath': '/alpha/',
        },
        {
            'name': 'volume-mounts-beta',
            'mountPath': '/beta/',
        },
    ]
    spawner = KubeSpawner(config=c, _mock=True)

    manifest = await spawner.get_pod_manifest()

    assert isinstance(manifest.spec.containers[0].volume_mounts, list)
    assert manifest.spec.containers[0].volume_mounts[0].name == 'volume-mounts-alpha'
    assert manifest.spec.containers[0].volume_mounts[0].mount_path == '/alpha/'
    assert manifest.spec.containers[0].volume_mounts[1].name == 'volume-mounts-beta'
    assert manifest.spec.containers[0].volume_mounts[1].mount_path == '/beta/'


async def test_volume_dict():
    """
    Test that volumes can be a dictionary of dictionaries.
    The output list should be lexicographically sorted by key.
    """
    c = Config()

    c.KubeSpawner.volumes = {
        "02-group-beta": {
            'name': 'volumes-beta',
            'persistentVolumeClaim': {'claimName': 'beta-claim'},
        },
        "01-group-alpha": {
            'name': 'volumes-alpha',
            'persistentVolumeClaim': {'claimName': 'alpha-claim'},
        },
    }

    spawner = KubeSpawner(config=c, _mock=True)

    manifest = await spawner.get_pod_manifest()

    assert isinstance(manifest.spec.volumes, list)
    assert manifest.spec.volumes[0].name == 'volumes-alpha'
    assert (
        manifest.spec.volumes[0].persistent_volume_claim["claimName"] == 'alpha-claim'
    )
    assert manifest.spec.volumes[1].name == 'volumes-beta'
    assert manifest.spec.volumes[1].persistent_volume_claim["claimName"] == 'beta-claim'


async def test_volume_list():
    """
    Test that volumes can be a list of dictionaries for backwards compatibility.
    """
    c = Config()

    c.KubeSpawner.volumes = [
        {
            'name': 'volumes-alpha',
            'persistentVolumeClaim': {'claimName': 'alpha-claim'},
        },
        {
            'name': 'volumes-beta',
            'persistentVolumeClaim': {'claimName': 'beta-claim'},
        },
    ]
    spawner = KubeSpawner(config=c, _mock=True)

    manifest = await spawner.get_pod_manifest()

    assert isinstance(manifest.spec.volumes, list)
    assert manifest.spec.volumes[0].name == 'volumes-alpha'
    assert (
        manifest.spec.volumes[0].persistent_volume_claim["claimName"] == 'alpha-claim'
    )
    assert manifest.spec.volumes[1].name == 'volumes-beta'
    assert manifest.spec.volumes[1].persistent_volume_claim["claimName"] == 'beta-claim'


async def test_extra_containers_dictionary():
    """
    Test that extra_containers can be a dictionary of dictionaries.
    The output list should be lexicographically sorted by key.
    """
    c = Config()

    c.KubeSpawner.extra_containers = {
        "02-group-beta": {
            'name': 'extra-containers-beta',
            'image': 'busybox',
        },
        "01-group-alpha": {
            'name': 'extra-containers-alpha',
            'image': 'busybox',
        },
    }

    spawner = KubeSpawner(config=c, _mock=True)

    manifest = await spawner.get_pod_manifest()

    assert isinstance(manifest.spec.containers, list)
    assert (
        len(manifest.spec.containers) == 3
    )  # 1 for the notebook container, 2 for extra_containers
    assert manifest.spec.containers[1].name == 'extra-containers-alpha'
    assert manifest.spec.containers[2].name == 'extra-containers-beta'


async def test_extra_containers_list():
    """
    Test that extra_containers can be a list of dictionaries.
    """
    c = Config()

    c.KubeSpawner.extra_containers = [
        {
            'name': 'extra-containers-alpha',
            'image': 'busybox',
        },
        {
            'name': 'extra-containers-beta',
            'image': 'busybox',
        },
    ]
    spawner = KubeSpawner(config=c, _mock=True)

    manifest = await spawner.get_pod_manifest()

    assert isinstance(manifest.spec.containers, list)
    assert (
        len(manifest.spec.containers) == 3
    )  # 1 for the notebook container, 2 for extra_containers
    assert manifest.spec.containers[1].name == 'extra-containers-alpha'
    assert manifest.spec.containers[2].name == 'extra-containers-beta'


async def test_tolerations_list():
    """
    Test that tolerations can be a list.
    """
    c = Config()

    tolerations = [
        {
            'key': 'key1',
            'operator': 'Equal',
            'value': 'value1',
            'effect': 'NoSchedule',
        },
        {
            'key': 'key2',
            'operator': 'Exists',
            'effect': 'NoExecute',
        },
    ]
    c.KubeSpawner.tolerations = tolerations
    spawner = KubeSpawner(config=c, _mock=True)

    manifest = await spawner.get_pod_manifest()

    assert isinstance(manifest.spec.tolerations, list)
    assert len(manifest.spec.tolerations) == 2
    assert manifest.spec.tolerations[0].key == 'key1'
    assert manifest.spec.tolerations[0].operator == 'Equal'
    assert manifest.spec.tolerations[0].value == 'value1'
    assert manifest.spec.tolerations[0].effect == 'NoSchedule'
    assert manifest.spec.tolerations[1].key == 'key2'
    assert manifest.spec.tolerations[1].operator == 'Exists'
    assert manifest.spec.tolerations[1].effect == 'NoExecute'


async def test_tolerations_dict():
    """
    Test that tolerations can be a dictionary.
    The output list should be lexicographically sorted by key.
    """
    c = Config()

    tolerations = {
        '01-group-alpha': {
            'key': 'key1',
            'operator': 'Equal',
            'value': 'value1',
            'effect': 'NoSchedule',
        },
        '02-group-beta': {
            'key': 'key2',
            'operator': 'Exists',
            'effect': 'NoExecute',
        },
    }
    c.KubeSpawner.tolerations = tolerations
    spawner = KubeSpawner(config=c, _mock=True)

    manifest = await spawner.get_pod_manifest()

    assert isinstance(manifest.spec.tolerations, list)
    assert len(manifest.spec.tolerations) == 2
    assert manifest.spec.tolerations[0].key == 'key1'
    assert manifest.spec.tolerations[0].operator == 'Equal'
    assert manifest.spec.tolerations[0].value == 'value1'
    assert manifest.spec.tolerations[0].effect == 'NoSchedule'
    assert manifest.spec.tolerations[1].key == 'key2'
    assert manifest.spec.tolerations[1].operator == 'Exists'
    assert manifest.spec.tolerations[1].effect == 'NoExecute'


async def test_node_affinity_preferred():
    """
    Test that node_affinity_preferred can be a list or dictionary of dictionaries.
    The output list should be lexicographically sorted by key when a dictionary is used.
    """
    c = Config()
    node_affinity_preferred = [
        {
            'weight': 1,
            'preference': {
                'matchExpressions': [
                    {'key': 'key1', 'operator': 'In', 'values': ['value1', 'value2']}
                ]
            },
        },
        {
            'weight': 2,
            'preference': {'matchExpressions': [{'key': 'key2', 'operator': 'Exists'}]},
        },
    ]
    c.KubeSpawner.node_affinity_preferred = node_affinity_preferred
    spawner = KubeSpawner(config=c, _mock=True)
    manifest = await spawner.get_pod_manifest()
    spec = (
        manifest.spec.affinity.node_affinity.preferred_during_scheduling_ignored_during_execution
    )

    assert isinstance(spec, list)
    assert len(spec) == 2
    assert spec[0].weight == 1
    assert spec[0].preference == node_affinity_preferred[0]["preference"]
    assert spec[1].weight == 2
    assert spec[1].preference == node_affinity_preferred[1]["preference"]

    node_affinity_preferred_dict = {
        "02-group-beta": {
            "weight": 2,
            "preference": {
                "matchExpressions": [
                    {
                        "key": "security",
                        "operator": "In",
                        "values": ["S2"],
                    }
                ]
            },
        },
        "01-group-alpha": {
            "weight": 1,
            "preference": {
                "matchExpressions": [
                    {
                        "key": "security",
                        "operator": "In",
                        "values": ["S1"],
                    }
                ]
            },
        },
    }
    c.KubeSpawner.node_affinity_preferred = node_affinity_preferred_dict
    spawner = KubeSpawner(config=c, _mock=True)
    manifest = await spawner.get_pod_manifest()
    spec = (
        manifest.spec.affinity.node_affinity.preferred_during_scheduling_ignored_during_execution
    )

    assert len(spec) == 2
    assert spec[0].weight == 1
    assert (
        spec[0].preference
        == node_affinity_preferred_dict["01-group-alpha"]["preference"]
    )
    assert spec[1].weight == 2
    assert (
        spec[1].preference
        == node_affinity_preferred_dict["02-group-beta"]["preference"]
    )


async def test_node_affinity_required():
    """
    Test that node_affinity_required can be a list or dictionary of dictionaries.
    The output list should be lexicographically sorted by key when a dictionary is used.
    """
    c = Config()
    node_affinity_required = [
        {
            'matchExpressions': [
                {'key': 'key1', 'operator': 'In', 'values': ['value1', 'value2']}
            ]
        }
    ]
    c.KubeSpawner.node_affinity_required = node_affinity_required
    spawner = KubeSpawner(config=c, _mock=True)
    manifest = await spawner.get_pod_manifest()
    spec = (
        manifest.spec.affinity.node_affinity.required_during_scheduling_ignored_during_execution.node_selector_terms
    )

    assert isinstance(spec, list)
    assert len(spec) == 1
    assert spec[0].match_expressions == node_affinity_required[0]["matchExpressions"]

    node_affinity_required_dict = {
        "02-group-beta": {
            "matchExpressions": [
                {
                    "key": "security",
                    "operator": "In",
                    "values": ["S2"],
                }
            ]
        },
        "01-group-alpha": {
            "matchExpressions": [
                {
                    "key": "security",
                    "operator": "In",
                    "values": ["S1"],
                }
            ]
        },
    }
    c.KubeSpawner.node_affinity_required = node_affinity_required_dict
    spawner = KubeSpawner(config=c, _mock=True)
    manifest = await spawner.get_pod_manifest()
    spec = (
        manifest.spec.affinity.node_affinity.required_during_scheduling_ignored_during_execution.node_selector_terms
    )

    assert len(spec) == 2
    assert (
        spec[0].match_expressions
        == node_affinity_required_dict["01-group-alpha"]["matchExpressions"]
    )
    assert (
        spec[1].match_expressions
        == node_affinity_required_dict["02-group-beta"]["matchExpressions"]
    )


async def test_pod_affinity_preferred():
    """
    Test that pod_affinity_preferred can be a list or dictionary of dictionaries.
    The output list should be lexicographically sorted by key when a dictionary is used.
    """
    c = Config()
    pod_affinity_preferred = [
        {
            'weight': 1,
            'podAffinityTerm': {
                'labelSelector': {
                    'matchExpressions': [
                        {'key': 'key1', 'operator': 'In', 'values': ['value1']}
                    ]
                },
                'topologyKey': 'topology.kubernetes.io/zone',
            },
        }
    ]
    c.KubeSpawner.pod_affinity_preferred = pod_affinity_preferred
    spawner = KubeSpawner(config=c, _mock=True)
    manifest = await spawner.get_pod_manifest()
    spec = (
        manifest.spec.affinity.pod_affinity.preferred_during_scheduling_ignored_during_execution
    )

    assert isinstance(spec, list)
    assert len(spec) == 1
    assert spec[0].weight == 1
    assert spec[0].pod_affinity_term == pod_affinity_preferred[0]["podAffinityTerm"]

    pod_affinity_preferred_dict = {
        "02-group-beta": {
            "weight": 2,
            "podAffinityTerm": {
                "labelSelector": {
                    "matchExpressions": [
                        {
                            "key": "security",
                            "operator": "In",
                            "values": ["S2"],
                        }
                    ]
                },
                "topologyKey": "topology.kubernetes.io/zone",
            },
        },
        "01-group-alpha": {
            "weight": 1,
            "podAffinityTerm": {
                "labelSelector": {
                    "matchExpressions": [
                        {
                            "key": "security",
                            "operator": "In",
                            "values": ["S1"],
                        }
                    ]
                },
                "topologyKey": "topology.kubernetes.io/zone",
            },
        },
    }
    c.KubeSpawner.pod_affinity_preferred = pod_affinity_preferred_dict
    spawner = KubeSpawner(config=c, _mock=True)
    manifest = await spawner.get_pod_manifest()
    spec = (
        manifest.spec.affinity.pod_affinity.preferred_during_scheduling_ignored_during_execution
    )

    assert len(spec) == 2
    assert spec[0].weight == 1
    assert (
        spec[0].pod_affinity_term
        == pod_affinity_preferred_dict["01-group-alpha"]["podAffinityTerm"]
    )
    assert spec[1].weight == 2
    assert (
        spec[1].pod_affinity_term
        == pod_affinity_preferred_dict["02-group-beta"]["podAffinityTerm"]
    )


async def test_pod_affinity_required():
    """
    Test that pod_affinity_required can be a list or dictionary of dictionaries.
    The output list should be lexicographically sorted by key when a dictionary is used.
    """
    c = Config()
    pod_affinity_required = [
        {
            'labelSelector': {
                'matchExpressions': [
                    {'key': 'key1', 'operator': 'In', 'values': ['value1']}
                ]
            },
            'topologyKey': 'topology.kubernetes.io/zone',
        }
    ]
    c.KubeSpawner.pod_affinity_required = pod_affinity_required
    spawner = KubeSpawner(config=c, _mock=True)
    manifest = await spawner.get_pod_manifest()
    spec = (
        manifest.spec.affinity.pod_affinity.required_during_scheduling_ignored_during_execution
    )

    assert isinstance(spec, list)
    assert len(spec) == 1
    assert spec[0].label_selector == pod_affinity_required[0]["labelSelector"]
    assert spec[0].topology_key == pod_affinity_required[0]["topologyKey"]

    pod_affinity_required_dict = {
        "02-group-beta": {
            "labelSelector": {
                "matchExpressions": [
                    {
                        "key": "security",
                        "operator": "In",
                        "values": ["S2"],
                    }
                ]
            },
            "topologyKey": "topology.kubernetes.io/zone",
        },
        "01-group-alpha": {
            "labelSelector": {
                "matchExpressions": [
                    {
                        "key": "security",
                        "operator": "In",
                        "values": ["S1"],
                    }
                ]
            },
            "topologyKey": "topology.kubernetes.io/zone",
        },
    }
    c.KubeSpawner.pod_affinity_required = pod_affinity_required_dict
    spawner = KubeSpawner(config=c, _mock=True)
    manifest = await spawner.get_pod_manifest()
    spec = (
        manifest.spec.affinity.pod_affinity.required_during_scheduling_ignored_during_execution
    )

    assert len(spec) == 2
    assert (
        spec[0].label_selector
        == pod_affinity_required_dict["01-group-alpha"]["labelSelector"]
    )
    assert (
        spec[0].topology_key
        == pod_affinity_required_dict["01-group-alpha"]["topologyKey"]
    )
    assert (
        spec[1].label_selector
        == pod_affinity_required_dict["02-group-beta"]["labelSelector"]
    )
    assert (
        spec[1].topology_key
        == pod_affinity_required_dict["02-group-beta"]["topologyKey"]
    )


async def test_pod_anti_affinity_preferred():
    """
    Test that pod_anti_affinity_preferred can be a list or dictionary of dictionaries.
    The output list should be lexicographically sorted by key when a dictionary is used.
    """
    c = Config()
    pod_anti_affinity_preferred = [
        {
            'weight': 1,
            'podAffinityTerm': {
                'labelSelector': {
                    'matchExpressions': [
                        {'key': 'key1', 'operator': 'In', 'values': ['value1']}
                    ]
                },
                'topologyKey': 'topology.kubernetes.io/zone',
            },
        }
    ]
    c.KubeSpawner.pod_anti_affinity_preferred = pod_anti_affinity_preferred
    spawner = KubeSpawner(config=c, _mock=True)
    manifest = await spawner.get_pod_manifest()

    spec = (
        manifest.spec.affinity.pod_anti_affinity.preferred_during_scheduling_ignored_during_execution
    )

    assert isinstance(spec, list)
    assert len(spec) == 1
    assert spec[0].weight == 1
    assert (
        spec[0].pod_affinity_term == pod_anti_affinity_preferred[0]["podAffinityTerm"]
    )

    pod_anti_affinity_preferred_dict = {
        "02-group-beta": {
            "weight": 2,
            "podAffinityTerm": {
                "labelSelector": {
                    "matchExpressions": [
                        {
                            "key": "security",
                            "operator": "In",
                            "values": ["S2"],
                        }
                    ]
                },
                "topologyKey": "topology.kubernetes.io/zone",
            },
        },
        "01-group-alpha": {
            "weight": 1,
            "podAffinityTerm": {
                "labelSelector": {
                    "matchExpressions": [
                        {
                            "key": "security",
                            "operator": "In",
                            "values": ["S1"],
                        }
                    ]
                },
                "topologyKey": "topology.kubernetes.io/region",
            },
        },
    }
    c.KubeSpawner.pod_anti_affinity_preferred = pod_anti_affinity_preferred_dict
    spawner = KubeSpawner(config=c, _mock=True)
    manifest = await spawner.get_pod_manifest()
    spec = (
        manifest.spec.affinity.pod_anti_affinity.preferred_during_scheduling_ignored_during_execution
    )

    assert len(spec) == 2
    assert spec[0].weight == 1
    assert (
        spec[0].pod_affinity_term
        == pod_anti_affinity_preferred_dict["01-group-alpha"]["podAffinityTerm"]
    )
    assert spec[1].weight == 2
    assert (
        spec[1].pod_affinity_term
        == pod_anti_affinity_preferred_dict["02-group-beta"]["podAffinityTerm"]
    )


async def test_pod_anti_affinity_required():
    """
    Test that pod_anti_affinity_required can be a list or dictionary of dictionaries.
    The output list should be lexicographically sorted by key when a dictionary is used.
    """
    c = Config()
    pod_anti_affinity_required = [
        {
            "labelSelector": {
                "matchExpressions": [
                    {
                        "key": "security",
                        "operator": "In",
                        "values": ["S1"],
                    }
                ]
            },
            "topologyKey": "failure-domain.beta.kubernetes.io/zone",
        }
    ]
    c.KubeSpawner.pod_anti_affinity_required = pod_anti_affinity_required
    spawner = KubeSpawner(config=c, _mock=True)
    manifest = await spawner.get_pod_manifest()

    spec = (
        manifest.spec.affinity.pod_anti_affinity.required_during_scheduling_ignored_during_execution
    )

    assert spec[0].label_selector == pod_anti_affinity_required[0]["labelSelector"]
    assert spec[0].topology_key == pod_anti_affinity_required[0]["topologyKey"]

    pod_anti_affinity_required_dict = {
        "02-group-beta": {
            "labelSelector": {
                "matchExpressions": [
                    {
                        "key": "security",
                        "operator": "In",
                        "values": ["S2"],
                    }
                ]
            },
            "topologyKey": "failure-domain.beta.kubernetes.io/region",
        },
        "01-group-alpha": {
            "labelSelector": {
                "matchExpressions": [
                    {
                        "key": "security",
                        "operator": "In",
                        "values": ["S1"],
                    }
                ]
            },
            "topologyKey": "failure-domain.beta.kubernetes.io/zone",
        },
    }
    c.KubeSpawner.pod_anti_affinity_required = pod_anti_affinity_required_dict
    spawner = KubeSpawner(config=c, _mock=True)
    manifest = await spawner.get_pod_manifest()
    spec = (
        manifest.spec.affinity.pod_anti_affinity.required_during_scheduling_ignored_during_execution
    )

    assert len(spec) == 2
    assert (
        spec[0].label_selector
        == pod_anti_affinity_required_dict["01-group-alpha"]["labelSelector"]
    )
    assert (
        spec[0].topology_key
        == pod_anti_affinity_required_dict["01-group-alpha"]["topologyKey"]
    )
    assert (
        spec[1].label_selector
        == pod_anti_affinity_required_dict["02-group-beta"]["labelSelector"]
    )
    assert (
        spec[1].topology_key
        == pod_anti_affinity_required_dict["02-group-beta"]["topologyKey"]
    )
