from setuptools import setup, find_packages

setup(
    name='jupyterhub-kubespawner',
    version='0.5.1',
    install_requires=[
        'jupyterhub',
        'pyyaml',
    ],
    setup_requires=['pytest-runner'],
    tests_require=['pytest'],
    description='JupyterHub Spawner targetting Kubernetes',
    url='http://github.com/jupyterhub/kubespawner',
    author='Yuvi Panda',
    author_email='yuvipanda@gmail.com',
    license='BSD',
    packages=find_packages(),
)
