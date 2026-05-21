from setuptools import setup, find_packages
import sys

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
    packages=find_packages(include=["app*", "ble*", "lib*", "gui*", "remote*"]),
    py_modules=["solar_runner"],
    install_requires=[
        "tabulate"
    ],
    data_files=[
        ("share/solar12vups", [
            "favicon.png",
            "favicon-strict.png",
            "favicon.ico",
        ]),
    ],
    entry_points={
        "console_scripts": [
            "solar12vups=solar_runner:main",
            "solar12vups-install-desktop=app.install_desktop:main",
            "solar12vups-bridge-server=remote.bridge_server:main",
            "pingpico=tools.pingpico:main",
            "pico-uart-loopback=tools.pico_uart_loopback:main",
        ],
    },
    include_package_data=True,
    zip_safe=False,
)
