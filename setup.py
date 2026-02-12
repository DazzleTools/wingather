import os
from setuptools import setup, find_packages

# Read version from _version.py (exec, not import — package isn't installed yet)
version_file = os.path.join(os.path.dirname(__file__), "wingather", "_version.py")
with open(version_file) as f:
    exec(f.read())

setup(
    name="wingather",
    version=get_pip_version() if "get_pip_version" in locals() else "0.0.0",
    description="Windows admin and security tool for discovering, recovering, and managing hidden or inaccessible windows",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    author="Dustin",
    author_email="6962246+djdarcy@users.noreply.github.com",
    url="https://github.com/DazzleTools/wingather",
    packages=find_packages(),
    entry_points={
        "console_scripts": [
            "wingather=wingather.cli:main",
        ],
    },
    install_requires=[
        "psutil>=5.9.0",
        'pywin32>=305; platform_system=="Windows"',
    ],
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Environment :: Console",
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Operating System :: Microsoft :: Windows",
        "Operating System :: MacOS",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Desktop Environment",
        "Topic :: System :: Systems Administration",
        "Topic :: Utilities",
    ],
    python_requires=">=3.8",
)
