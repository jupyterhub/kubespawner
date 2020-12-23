"""Minimal jupyterhub config for hub pod"""
import json
import os
import socket
import tarfile

c = get_config()  # noqa

c.JupyterHub.hub_ip = "0.0.0.0"
c.JupyterHub.hub_connect_ip = socket.gethostname()
c.JupyterHub.log_level = "DEBUG"

import pprint

pprint.pprint(dict(os.environ))

print("before")
for root, dirs, files in os.walk("/etc/jupyterhub"):
    for name in files:
        print(os.path.join(root, name))
    for name in dirs:
        print(os.path.join(root, name) + "/")

ssl_tar_file = "/etc/jupyterhub/secret/internal-ssl.tar"
if os.path.exists(ssl_tar_file):
    print("Enabling internal SSL")
    c.JupyterHub.internal_ssl = True
    ssl_dir = "/etc/jupyterhub/internal-ssl"
    c.JupyterHub.internal_certs_location = ssl_dir

    with tarfile.open(ssl_tar_file) as tf:
        tf.extractall(path="/etc/jupyterhub")

    for root, dirs, files in os.walk("/etc/jupyterhub"):
        for name in files:
            print(os.path.join(root, name))
        for name in dirs:
            print(os.path.join(root, name) + "/")

    # rewrite paths in certipy config not created here
    certipy_config = os.path.join(c.JupyterHub.internal_certs_location, "certipy.json")
    with open(certipy_config) as f:
        cfg = json.load(f)
    print("cfg before", cfg)
    path = cfg["hub-internal"]["files"]["key"]
    prefix_len = path.index("/hub-internal")
    prefix = path[:prefix_len]
    print("relocating certipy {} -> {}".format(prefix, ssl_dir))
    for name, service in cfg.items():
        for key in list(service["files"]):
            path = service["files"][key]
            if path.startswith(prefix):
                service["files"][key] = ssl_dir + path[prefix_len:]
            # path = service["files"][key]
            # print(name, key, path)
            # if path:
            #     new_abs_path = ssl_dir + path[path.index("/" + name):]
            #     print(path, new_abs_path)
            #     service["files"][key] = new_abs_path

    print(cfg)

    with open(certipy_config, "w") as f:
        json.dump(cfg, f)

    # c.JupyterHub.trusted_alt_names = socket.gethostname()

c.JupyterHub.services = [
    {"name": "test", "admin": True, "api_token": "test-secret-token"},
]

print("after")
for root, dirs, files in os.walk("/etc/jupyterhub"):
    for name in files:
        print(os.path.join(root, name))
    for name in dirs:
        print(os.path.join(root, name) + "/")
