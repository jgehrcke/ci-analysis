import re
from setuptools import setup


version = re.search(
    r'^__version__\s*=\s*"(.*)"', open("cia/cia.py").read(), re.M
).group(1)


with open("README.md", "rb") as f:
    long_descr = f.read().decode("utf-8")


setup(
    name="ci-analysis",
    packages=["cia"],
    entry_points={
        "console_scripts": [
            "ci-analysis = cia.cia:main",
        ]
    },
    version=version,
    description="Performs analysis on CI build information.",
    long_description=long_descr,
    long_description_content_type="text/markdown",
    author="Dr. Jan-Philip Gehrcke",
    author_email="jgehrcke@googlemail.com",
    url="https://github.com/jgehrcke/ci-analysis",
    classifiers=[
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: Implementation :: CPython",
        "Operating System :: POSIX",
    ],
    install_requires=("pandas", "matplotlib", "pytablewriter", "pybuildkite"),
)
