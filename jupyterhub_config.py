import os
import socket

c.JupyterHub.spawner_class = 'kubespawner.KubeSpawner'

c.JupyterHub.ip = '127.0.0.1'
c.JupyterHub.hub_ip = '127.0.0.1'

# Don't try to cleanup servers on exit - since in general for k8s, we want
# the hub to be able to restart without losing user containers
c.JupyterHub.cleanup_servers = False

# A small user image with jupyterlab that is easy to test against, assumed to be
# downloadable in less than 60 seconds.
c.KubeSpawner.image = 'jupyter/base-notebook:latest'
c.KubeSpawner.start_timeout = 60

if os.environ.get("CI"):
    # In the CI system we use k3s which will be accessible on localhost.
    c.JupyterHub.hub_connect_ip = "127.0.0.1"
else:
    # Find the IP of the machine that minikube is most likely able to talk to
    # Graciously used from https://stackoverflow.com/a/166589
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    host_ip = s.getsockname()[0]
    s.close()

    c.JupyterHub.hub_connect_ip = host_ip

# Simplify testing by using a dummy authenticator class where any username
# password combination will work and where we don't provide persistent storage.
c.JupyterHub.authenticator_class = 'dummy'
c.KubeSpawner.storage_pvc_ensure = False

c.JupyterHub.allow_named_servers = True

c.KubeSpawner.profile_list = [
    {
        'display_name': 'Demo - profile_list entry 1',
        'description': 'Demo description for profile_list entry 1, and it should look good even though it is a bit lengthy.',
        'slug': 'demo-1',
        'default': True,
        'profile_options': {
            'image': {
                'display_name': 'Image',
                'choices': {
                    'base': {
                        'display_name': 'jupyter/base-notebook:latest',
                        'kubespawner_override': {
                            'image': 'jupyter/base-notebook:latest'
                        },
                    },
                    'minimal': {
                        'display_name': 'jupyter/minimal-notebook:latest',
                        'default': True,
                        'kubespawner_override': {
                            'image': 'jupyter/minimal-notebook:latest'
                        },
                    },
                },
                'unlisted_choice': {
                    'enabled': True,
                    'display_name': 'Other image',
                    'validation_regex': '^jupyter/.+:.+$',
                    'validation_message': 'Must be an image matching ^jupyter/<name>:<tag>$',
                    'kubespawner_override': {'image': '{value}'},
                },
            },
        },
        'kubespawner_override': {
            'default_url': '/lab',
        },
    },
    {
        'display_name': 'Demo - profile_list entry 2',
        'slug': 'demo-2',
        'kubespawner_override': {
            'extra_resource_guarantees': {"nvidia.com/gpu": "1"},
        },
    },
    {
        # Demonstrates nested profile_options: choices can declare their own
        # profile_options, shown only while that choice is selected. Overrides
        # here only set environment variables so the pod stays schedulable on
        # a local cluster and the result is observable with `env | grep DEMO_`
        # in the spawned server's terminal.
        'display_name': 'Demo - nested profile options',
        'slug': 'demo-nested',
        'profile_options': {
            'gpu': {
                'display_name': 'GPU setup',
                'choices': {
                    'none': {
                        'display_name': 'No GPU',
                        'default': True,
                        'kubespawner_override': {
                            'environment': {'DEMO_GPU_SETUP': 'none'},
                        },
                    },
                    'nvidia': {
                        'display_name': 'NVIDIA',
                        'kubespawner_override': {
                            'environment': {'DEMO_GPU_SETUP': 'nvidia'},
                        },
                        'profile_options': {
                            'type': {
                                'display_name': 'GPU type',
                                'choices': {
                                    't4': {
                                        'display_name': 'T4',
                                        'default': True,
                                        'kubespawner_override': {
                                            'environment': {'DEMO_GPU_TYPE': 't4'},
                                        },
                                    },
                                    'a100': {
                                        'display_name': 'A100',
                                        'kubespawner_override': {
                                            'environment': {'DEMO_GPU_TYPE': 'a100'},
                                        },
                                    },
                                },
                                'unlisted_choice': {
                                    'enabled': True,
                                    'display_name': 'Custom GPU type',
                                    'validation_regex': '^[a-z0-9-]+$',
                                    'validation_message': 'Lowercase letters, digits and dashes only',
                                    'kubespawner_override': {
                                        'environment': {'DEMO_GPU_TYPE': '{value}'},
                                    },
                                },
                            },
                            'count': {
                                'display_name': 'GPU count',
                                'choices': {
                                    'one': {
                                        'display_name': '1',
                                        'default': True,
                                        'kubespawner_override': {
                                            'environment': {'DEMO_GPU_COUNT': '1'},
                                        },
                                        # A second level of nesting to exercise recursion
                                        'profile_options': {
                                            'sharing': {
                                                'display_name': 'GPU sharing',
                                                'choices': {
                                                    'exclusive': {
                                                        'display_name': 'Exclusive',
                                                        'default': True,
                                                        'kubespawner_override': {
                                                            'environment': {'DEMO_GPU_SHARING': 'exclusive'},
                                                        },
                                                    },
                                                    'mig': {
                                                        'display_name': 'MIG slice',
                                                        'kubespawner_override': {
                                                            'environment': {'DEMO_GPU_SHARING': 'mig'},
                                                        },
                                                    },
                                                },
                                            },
                                        },
                                    },
                                    'two': {
                                        'display_name': '2',
                                        'kubespawner_override': {
                                            'environment': {'DEMO_GPU_COUNT': '2'},
                                        },
                                    },
                                },
                            },
                        },
                    },
                },
            },
        },
    },
]
