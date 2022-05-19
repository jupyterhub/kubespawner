import sys

from setuptools import find_packages, setup

v = sys.version_info
if v[:2] < (3, 7):
    error = "ERROR: kubespawner requires Python version 3.7 or above."
    print(error, file=sys.stderr)
    sys.exit(1)

setup(
    name='jupyterhub-kubespawner',
    version='4.1.0',
    install_requires=[
        'escapism',
        'python-slugify',
        'jupyterhub>=0.9',
        'jinja2',
        'kubernetes_asyncio>=19.15.1',
        'urllib3',
        'pyYAML',
    ],
    python_requires='>=3.7',
    extras_require={
        'test': [
            'bump2version',
            'kubernetes>=11',
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
