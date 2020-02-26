'''Analogous to objects.py, but objects we need for multi-namespace support.
'''
from kubernetes.client.models import (
    V1ObjectMeta,
    V1Namespace,
    V1ServiceAccount,
    V1PolicyRule,
    V1Role,
    V1RoleBinding,
    V1RoleRef,
    V1Subject,
    V1DeleteOptions,
    V1ResourceQuotaSpec,
    V1ResourceQuota
)


def make_namespace(name):
    '''Create a new namespace object.
    '''
    ns = V1Namespace(
        metadata=V1ObjectMeta(name=name))
    return ns


def make_namespaced_account_objects(namespace, username):
    '''Create the trio of account, role, binding for a given namespace/
    usename combination.'''
    # FIXME: probably something a little more sophisticated is called for.
    account = "{}-{}".format(username, "svcacct")
    md = V1ObjectMeta(name=account)
    svcacct = V1ServiceAccount(metadata=md)
    # These rules are suitable for spawning Dask pods.  You will need to
    #  modify them for spawning other things, such as Argo Workflows.
    rules = [
        V1PolicyRule(
            api_groups=[""],
            resources=["pods", "services"],
            verbs=["get", "list", "watch", "create", "delete"]
        ),
        V1PolicyRule(
            api_groups=[""],
            resources=["pods/log", "serviceaccounts"],
            verbs=["get", "list"]
        ),
    ]
    role = V1Role(
        rules=rules,
        metadata=md)
    rolebinding = V1RoleBinding(
        metadata=md,
        role_ref=V1RoleRef(api_group="rbac.authorization.k8s.io",
                           kind="Role",
                           name=account),
        subjects=[V1Subject(
            kind="ServiceAccount",
            name=account,
            namespace=namespace)]
    )

    return svcacct, role, rolebinding


def make_delete_options():
    '''Create empty delete options.
    '''
    delete_options = V1DeleteOptions()
    return delete_options


def make_quota_spec(cpu='100', memory='200Gi'):
    '''This is something you will probably want to override in a subclass.
    You could do different quotas by user group membership, or size
    based on things you determine from the environment.  This
    implementation is just a stub that returns defaults appropriate for
    smallish environments, assuming 2G per core.
    '''
    qs = V1ResourceQuotaSpec(
        hard={"limits.cpu": cpu,
              "limits.memory": memory})
    return qs


def make_quota(quotaspec):
    '''Return a quota based on a quotaspec.
    '''
    quota = V1ResourceQuota(
        metadata=V1ObjectMeta(
            name="quota",
        ),
        spec=quotaspec
    )
    return quota
