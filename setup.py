from setuptools import setup, find_packages

setup(
    name="claude",
    version="1.0.0",
    packages=['claude'],
    package_dir={'claude': '.claude'},
    install_requires=[
        "python-dotenv",
        "requests",
    ],
    python_requires=">=3.8",
)