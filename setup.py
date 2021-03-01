from __future__ import print_function

import sys

from setuptools import find_packages
from setuptools import setup

v = sys.version_info
if v[:2] < (3, 6):
    error = "ERROR: jupyterhub-kubespawner requires Python version 3.6 or above."
    print(error, file=sys.stderr)
    sys.exit(1)

setup(
    name='jupyterhub-kubespawner',
    version='0.16.1',
    install_requires=[
        'async_generator>=1.8',
        'escapism',
        'python-slugify',
        'jupyterhub>=0.8',
        'jinja2',
        'kubernetes>=10.1.0',
        'urllib3',
        'pyYAML',
    ],
    python_requires='>=3.6',
    extras_require={
        'test': [
            'bump2version',
            'flake8',
            'jupyterhub-dummyauthenticator',
            'pytest>=5.4',
            'pytest-cov',
            'pytest-asyncio>=0.11.0',
        ]
    },
    description='JupyterHub Spawner for Kubernetes',
    url='http://github.com/jupyterhub/kubespawner',
    author='Jupyter Contributors',
    author_email='jupyter@googlegroups.com',
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    license='BSD',
    packages=find_packages(),
    project_urls={
        'Documentation': 'https://jupyterhub-kubespawner.readthedocs.io',
        'Source': 'https://github.com/jupyterhub/kubespawner',
        'Tracker': 'https://github.com/jupyterhub/kubespawner/issues',
    },
)
