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
    version='0.10.0',
    install_requires=[
        'jupyterhub>=0.8',
        'pyYAML',
        'kubernetes>=7',
        'escapism',
        'jinja2',
        'async_generator>=1.8',
    ],
    python_requires='>=3.5',
    extras_require={
        'test': [
            'pytest>=3.3',
            'pytest-cov',
            'pytest-asyncio',
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
