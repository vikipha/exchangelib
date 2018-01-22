#!/usr/bin/env python
"""
Release notes:
* Bumpt version in setup.py
* Bump version and date in README.rst
* Bump version in CHANGELOG.rst
* Commit changes
* Tag version
* Push to PyPI: python setup.py sdist bdist_wheel upload
"""
import io
import os

from setuptools import setup


def read(fname):
    with io.open(os.path.join(os.path.dirname(__file__), fname), encoding='utf-8') as f:
        return f.read()

setup(
    name='exchangelib',
    version='1.10.7',
    author='Erik Cederstrand',
    author_email='erik@cederstrand.dk',
    description='Client for Microsoft Exchange Web Services (EWS)',
    long_description=read('README.rst'),
    license='BSD',
    keywords='Exchange EWS autodiscover',
    install_requires=['requests>=2.7', 'requests_ntlm>=0.2.0', 'dnspython>=1.14.0', 'pytz', 'lxml',
                      'cached_property', 'future', 'six', 'tzlocal', 'python-dateutil', 'pygments'],
    packages=['exchangelib'],
    tests_require=['PyYAML', 'requests_mock', 'psutil'],
    test_suite='tests',
    zip_safe=False,
    url='https://github.com/ecederstrand/exchangelib',
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Topic :: Communications',
        'License :: OSI Approved :: BSD License',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 3',
    ],
)
