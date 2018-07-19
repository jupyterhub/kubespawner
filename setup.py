from __future__ import print_function
from setuptools import setup, find_packages
import sys

v = sys.version_info
if v[:2] < (3, 5):
    error = "ERROR: jupyterhub-kubespawner requires Python version 3.5 or above."
    print(error, file=sys.stderr)
    sys.exit(1)

setup(
    name='jupyterhub-kubespawner',
    version='0.8.1',
    install_requires=[
        'jupyterhub>=0.9',
        'pyYAML',
        'kubernetes==6.*',
        'escapism',
        'jinja2',
        'async_generator>=1.8',
    ],
    python_requires='>=3.5',
    setup_requires=['pytest-runner'],
    tests_require=['pytest'],
    description='JupyterHub Spawner targeting Kubernetes',
    url='http://github.com/jupyterhub/kubespawner',
    author='Yuvi Panda',
    author_email='yuvipanda@gmail.com',
    license='BSD',
    packages=find_packages(),
)
