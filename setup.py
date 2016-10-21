from setuptools import setup

setup(
    name='jupyterhub-kubespawner',
    version='0.1',
    install_requires=[
        'jupyterhub',
        'pyyaml',
    ],
    description='JupyterHub Spawner targetting Kubernetes',
    url='http://github.com/yuvipanda/jupyterhub-kubernetes-spawner',
    author='Yuvi Panda',
    author_email='yuvipanda@riseup.net',
    license='BSD',
    packages=['kubespawner'],
)
