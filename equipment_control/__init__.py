#   Main file for backend
"""This set of files contains all functionalities to create procedures and user interfaces for GPIB, AR488 and RS232 connected measurement equipment.\n

The `DeviceProcedure` allows any window (user interface) from the `windows` file to read requested devices from the procedure, which should be shown to the user, and provide device identifiers `DESCRIPTOR` and `ADAPTER_TYPE` to the procedure which can be used with the `Device` class to create a `pymeasure` adapter as `Device.adapter` for communication.\n

Handling the communication (SCPI, etc ...) has to be done in the procedures.
"""
from .device import Device, make_resourcemanager, DeviceProcedure, DESCRIPTOR, ADAPTER_TYPE, IDENTIFICATION, GPIB_ADDRESS
from .windows import *