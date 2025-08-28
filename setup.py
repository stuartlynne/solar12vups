from setuptools import setup, find_packages

# Dynamically load version
version_ns = {}
with open("version.py") as f:
    exec(f.read(), version_ns)

setup(
    name="solar12vups",
    version=version_ns["__version__"],
    description="Solar-powered UPS monitor with BLE support and real-time GUI",
    author="Stuart Lynne",
    author_email="stuart.lynne@gmail.com",
    packages=find_packages(include=["app*", "ble*", "lib*", "gui*"]),
    py_modules=["solar_runner"],
    install_requires=[
        "tabulate"
    ],
    entry_points={
        "console_scripts": [
            "solar12vups=solar_runner:main",
        ],
    },
    include_package_data=True,
    zip_safe=False,
)
