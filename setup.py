from setuptools import setup

setup(
    name='kubespawner',
    version='0.1',
    install_requires=[
        'requests-futures>=0.9.7',
        'jupyterhub>=0.4.0',
    ],
    description='JupyterHub Spawner targetting Kubernetes',
    url='http://github.com/yuvipanda/jupyterhub-kubernetes-spawner',
    author='Yuvi Panda',
    author_email='yuvipanda@riseup.net',
    license='BSD',
    packages=['kubespawner'],
)
