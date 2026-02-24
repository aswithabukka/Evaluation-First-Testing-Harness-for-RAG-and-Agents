from setuptools import setup, find_packages

setup(
    name="rageval-sdk",
    version="0.1.0",
    description="SDK for logging production AI traffic to RAG Eval Harness",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "httpx>=0.24.0",
    ],
    extras_require={
        "fastapi": ["fastapi>=0.100.0"],
    },
)
