
from enum import StrEnum
class AdapterPortIdentifier(StrEnum):
    Serial = "ASRL"
    Gpib = "GPIB"

class Base:

    @staticmethod
    def find_device(log=False) -> str:
        """returns port as string if the port is a valid device"""
        raise NotImplementedError

    @staticmethod
    def _test_port(port: str, log=False) -> bool:
        """returns true if the port is a valid device"""
        raise NotImplementedError

    def test(self, current, time_high, time_low, nplc=0.01, pulse_count=10):
        """just a test function that plots a couple cycles when mesauring so we can investigate timing without osc"""
        raise NotImplementedError
    def start(self, current, time_high, time_low, measure=True, nplc=0.01):
        raise NotImplementedError
    def stop(self):
        raise NotImplementedError
