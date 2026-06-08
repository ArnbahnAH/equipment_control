import sys
import pyvisa
import numpy as np
import time
import matplotlib.pyplot as plt
import numpy as np

from ..base import Base , AdapterPortIdentifier
from ..config import get_storage
from ..export import export



@export
class Dummy(Base):
    smu: pyvisa.Resource

    def __init__(self, port):
        pass


    def __deinit__(self):
        pass

    def test(self, current, time_high, time_low, nplc=0.01, pulse_count=10):
        """
        current in A
        time_high in ms 
        time_low in ms 
        runs  pulse_count pulses and measures so you can confirm the timings.
        keep in mind that measure mode has a lower bound of 2-4ms depending on the sourcemeter.

        """
        print("Dummy::Test")

        pass

    def start(self, current, time_high, time_low, measure=True, nplc=0.01):
        """
        current in A
        time_high in ms 
        time_low in ms 
        """
        print("Dummy::Start")
        pass

    def stop(self):
        print("Dummy::Stop")
        pass

    @staticmethod
    def uid():
        return "Dummy"

    @staticmethod
    def find_device(log=False):
        pass

    @staticmethod
    def _test_port(port: str, log=False) -> bool:
        return False

