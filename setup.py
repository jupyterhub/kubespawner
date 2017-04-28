from setuptools import setup, find_packages

setup(
    name='sqrekubespawner',
    version='0.0.4',
    install_requires=[
        'jupyterhub',
        'pyyaml',
        'pycurl'
    ],
    setup_requires=['pytest-runner'],
    tests_require=['pytest'],
    description='LSST SQuaRE flavor of KubeSpawner',
    url='http://github.com/lsst-sqre/kubespawner',
    author='Adam Thornton',
    author_email='athornton@lsst.org',
    license='BSD',
    packages=find_packages(),
)
