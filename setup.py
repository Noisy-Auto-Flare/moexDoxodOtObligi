from setuptools import setup, find_packages

setup(
    name="bond_ytm",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "requests>=2.31.0",
        "pydantic>=2.5.0",
        "scipy>=1.11.0",
        "structlog>=23.2.0",
        "python-dateutil>=2.8.2",
        "diskcache>=5.6.0",
    ],
    extras_require={
        "test": ["pytest>=7.4.0"],
    },
    python_requires=">=3.11",
)
