import os
import sys

from setuptools import find_packages, setup
from dubbo.dubbo import __version__

setup(
    name = 'PyDubbo',
    version = __version__,
    description = 'python dubbo rpc framework client',
    keywords = 'dubbo hessian2 java',
    url = 'https://github.com/zhouyougit/PyDubbo',
    author = 'zhouyou',
    author_email = 'zhouyoug@gmail.com',
    packages = find_packages(exclude = ['temp.*', '*.class', '*.jar'])
)
