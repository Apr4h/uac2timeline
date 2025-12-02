# setup.py
from setuptools import setup, find_packages

setup(
    name="uac2timeline",
    version="0.0.1",
    packages=find_packages(),
    entry_points={
        "console_scripts": [
            "uac2timeline = uac2timeline.cli:main",
        ],
    },
    install_requires=[
        "pytsk3",
        "sqlalchemy",
        "pygrok",
        "tqdm",
    ],
    python_requires=">=3.7",
)