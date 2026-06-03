
# Pulsed mode for Keithley2400

- Runs in constant current mode written for the SEM heat stage (?) that requires 100mA @ 20V 
  volt_prot=30V volt_range=20V if measuring don't expect good results from test() since `nplc` is 0.01.

- The `Dummy` class in `impl/dummy.py` shows which methods are expected 

``` py

@export
class Dummy(Base):

    @staticmethod
    def find_device(log=False):
        raise NotImplementedError

    @staticmethod
    def _test_port(port: str, log=False) -> bool:
        raise NotImplementedError

    def test(self, current, time_high, time_low, nplc=0.01, pulse_count=10):
        raise NotImplementedError
    def start(self, current, time_high, time_low, measure=True, nplc=0.01):
        raise NotImplementedError
    def stop(self):
        raise NotImplementedError
```

- Inherit from this and implement the necessary functions for your smu and then
  you can support others.

- You have to use `@export` on the class as well to register it in the gui.
  Afterward its selectable from the combobox if there are no compile errors.

- `QPainter` is used to draw the Square wave graph its just there as a
  visualization serves no purpose otherwise.

- This code should support both the ar488 adapter and the normal gpib adapter I haven't tested it yet.

- Keep the limits in mind 4ms pulse high 300µs pulse low are the minimum
  anything else is going to give a bad square wave. 

- Timings for the Keithley2400 will vary +-400µs due to firmware you are better
  off using a true pulse mode smu or a square wave generator if you need better resolution. 

- Use the `test` button to see the timings for the measurement mode.
