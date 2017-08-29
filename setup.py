from setuptools import setup, find_packages

setup(
    name='jupyterhub-kubespawner',
    version='0.6.0',
    install_requires=[
        'jupyterhub',
        'pyYAML',
        'kubernetes==3.*',
        'escapism',
        'jupyter',
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
