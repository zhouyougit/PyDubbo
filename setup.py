import os
import sys

from setuptools import find_packages, setup
from dubbo import __version__

setup(
    name = 'PyDubbo',
    version = __version__,
    description = 'python dubbo rpc framework client',
    url = '',
    author = 'you.zhou',
    author_email = 'you.zhou@qunar.com',
    packages = find_packages(exclude = ['temp.*', '*.class', '*.jar']),
)
