from setuptools import setup, find_packages

setup(
    name='jupyterhub-kubespawner',
    version='0.7.1',
    install_requires=[
        'jupyterhub>=0.8',
        'pyYAML',
        'kubernetes==3.*',
        'escapism',
    ],
    setup_requires=['pytest-runner'],
    tests_require=['pytest'],
    description='JupyterHub Spawner targeting Kubernetes',
    url='http://github.com/jupyterhub/kubespawner',
    author='Yuvi Panda',
    author_email='yuvipanda@gmail.com',
    license='BSD',
    packages=find_packages(),
)
