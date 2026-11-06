__VERSION__ = "0.6.0.2"
# ruff: noqa: RUF100, UP025, UP004, I001, F401, BLE001, S110

import sys

MIN_VERSION = (1, 23, 0)

def check_firmware_version(major, minor, build):
    required_version = (int(major), int(minor), int(build))
    current_version = tuple(sys.implementation.version[:3])

    if current_version < required_version:
        raise RuntimeError(
            "This application requires MicroPython {} or later. \nDetected MicroPython: {}.".format(
                '.'.join(map(str, required_version)),
                '.'.join(map(str, current_version))
            )
        )
