from setuptools import setup, find_packages

from transpilex.config.package import PACKAGE_NAME, PACKAGE_VERSION, PACKAGE_DESCRIPTION, PACKAGE_AUTHOR, \
    PACKAGE_AUTHOR_EMAIL, PACKAGE_LICENSE

setup(
    name=PACKAGE_NAME,
    version=PACKAGE_VERSION,
    description=PACKAGE_DESCRIPTION,
    author=PACKAGE_AUTHOR,
    author_email=PACKAGE_AUTHOR_EMAIL,
    packages=find_packages(),
    include_package_data=True,
    entry_points={
        'console_scripts': [
            'transpile=transpilex.main:main',
        ],
    },
    license=PACKAGE_LICENSE,
)
