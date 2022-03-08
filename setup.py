from setuptools import setup, find_packages

requires = [
    'antelope_core>=0.1.1',
    'pandas',
    'matplotlib',
#    'colorsys',  # builtin
#    'textwrap'  # builtin
]

"""
Version History

0.1.1 - First split from lca-tools

"""

VERSION = '0.1.1'

setup(
    name="antelope_reports",
    version=VERSION,
    author="Brandon Kuczenski",
    author_email="brandon@scope3consulting.com",
    install_requires=requires,
    url="https://github.com/AntelopeLCA/reports",
    summary="Tools for summarizing and visualizing LCA models",
    long_description=open('README.md').read(),
    packages=find_packages()
)
