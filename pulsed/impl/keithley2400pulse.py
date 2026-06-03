import sys
import pyvisa
import numpy as np
import time
import matplotlib.pyplot as plt
import numpy as np

from ..base import Base , AdapterPortIdentifier
from ..config import get_storage
from ..export import export


#rem "ASRL/dev/ttyACM2::INSTR"

"""
nplc 0.01 bis 10
200µs .. 20ms

source_delay 0.00000 999.9999 s
10µs  => 50-100µs minimmum


for nplc 0.01 source_delay 0 we get highg for 4ms which is sitll too much.

=> use
:SENS:FUNC:OFF:ALL
:SENS:FUNC:EXT "SOUR"

with these and pause_time at 1ms we get a very bad pulse at about 500µs
getting a error code -113 => malfromed scip command

"""


@export
class Keithley2400Pulse(Base):
    #pulse width required is no less than 2ms for source & measure one function
    #or 640µs for source only
    #timing varriation of 100µs - 400µs

    # SOUR:DEL auslösung von ms
    # TRIG:DEL auslösung von µs
    smu: pyvisa.Resource

    def __init__(self, port):

        rm = pyvisa.ResourceManager("@py")
        self.smu = rm.open_resource(port)

        self.smu.write_termination = "\n"
        self.smu.read_termination = "\n"
        self.porttype = AdapterPortIdentifier.Serial in port #true if Serial False for Gpib
        if self.porttype:
            self.smu.write("++auto 0") # we have to force this into auto 0 otherwise we get a stupid beep
            self.smu.write("++clr")
            self.smu.write("++auto 1")

        ans = self.smu.query("*IDN?")
        if not "KEITHLEY" in ans:
            print("Error wrong device")
            self.smu.close()

    def __deinit__(self):
        self.smu.close()

    def test(self, current, time_high, time_low, nplc=0.01, pulse_count=10):
        """
        current in A
        time_high in ms 
        time_low in ms 
        runs  pulse_count pulses and measures so you can confirm the timings.
        keep in mind that measure mode has a lower bound of 2-4ms depending on the sourcemeter.

        """

        line_freq = 50 #Hz
        source_config = 50e-6
        ad_conversion_base = 185e-6
        source_overhead = 0.0
        trigger_latency = 225e-6 # TODO not for TRIG:SOUR IMM #TODO since TRIG:DEL can be set to 1µs you could in theory pause_times of 1µs as well

        measurment_time = nplc * 1/line_freq + ad_conversion_base #also called a/d conversion
        base_time_high= source_config + measurment_time + source_overhead # TODO can I figure this one from device?
        base_time_low = trigger_latency

        source_delay = time_high * 1e-3 - base_time_high
        pause_time = time_low * 1e-3 - base_time_low
        volt_range = 20
        volt_prot = 30

        period = time_high + time_low
        period *= 1e-3

        print(f"base_time_delay_high: {base_time_high*1e3:.2}ms desired_time_high: {time_high:.2}ms source_delay: {source_delay*1e3:.2}ms")
        print(f"base_time_delay_low: {base_time_low*1e3:.2}ms desired_time_low: {time_low:.2}ms pause_time: {pause_time*1e3:.2}ms")

        if self.porttype:
            self.smu.write("++auto 0")
        self.smu.write("*RST")
        self.smu.write(":TRAC:CLE") # clear buffer
        self.smu.write(f":TRAC:POIN {pulse_count}")
        #self.smu.write(f":STAT:MEAS:ENAB 512 ") #turn on buffer full bit 9
        #self.smu.write("*SRE 1") #sourcemeter makes a interrupt when it finished pulse_count points
        self.smu.write(f":TRIG:COUN {pulse_count}")
        self.smu.write(":SYST:AZER:STAT OFF") # auto zero off
        self.smu.write(f":SOUR:FUNC CURR")
        self.smu.write(f":SOUR:FUNC:CONC OFF") #disable concurrent readings
        self.smu.write(f':SENS:FUNC "VOLT"')
        self.smu.write(f":VOLT:NPLC {nplc}")
        self.smu.write(f":VOLT:RANG {volt_range}")
        self.smu.write(f":VOLT:PROT:LEV {volt_prot}")
        self.smu.write(f":FORM:ELEM VOLT, TIME") #we need volt and time
        self.smu.write(f":SOUR:CURR {current}")
        self.smu.write(f":TRIG:DEL {pause_time}")
        self.smu.write(f":SOUR:DEL {source_delay}")
        self.smu.write(f":TRAC:FEED:CONT NEXT")
        self.smu.write(f":SOUR:CLE:AUTO ON")
        self.smu.write(f":DISP:ENAB OFF")
        self.smu.write(f":INIT")

        # hack no srq for @py just wait a bit for data to come in
        if pulse_count * period <= .5:
            time.sleep(1)
        else:
            time.sleep(pulse_count * (period) * 2.0)
        if self.porttype:
            self.smu.write("++auto 1")
        data = self.smu.query(":TRAC:DATA?")
        if self.porttype:
            self.smu.write("++auto 0")
        self.smu.write("*RST")
        self.smu.write("*CLS")
        self.smu.write(f":DISP:ENAB ON")
        values = np.fromstring(data, sep=",")
        volt = values[0::2]
        timestamp = values[1::2]
        plt.clf()
        plt.plot(timestamp, volt)
        plt.title(f"{pulse_count} pulses at const current mode")
        plt.xlabel("time s")
        plt.ylabel("volt V")
        plt.show(block=False)

    def start(self, current, time_high, time_low, measure=True, nplc=0.01):
        """
        current in A
        time_high in ms 
        time_low in ms 
        """
        # https://www.tek.com/en/documents/application-note/can-i-generate-current-or-voltage-pulses-model-2400-or-other-non-pulse-mod
        # TODO add them to a config.json
        # highly depends on sourcemeter
        line_freq = 50 #Hz
        source_config = 50e-6
        ad_conversion_base = 185e-6
        source_overhead = 0.0
        trigger_latency = 225e-6 # TODO not for TRIG:SOUR IMM #TODO since TRIG:DEL can be set to 1µs you could in theory pause_times of 1µs as well

        measurment_time = nplc * 1/line_freq + ad_conversion_base #also called a/d conversion
        base_time_high= source_config + measurment_time + source_overhead # TODO can I figure this one from device?
        base_time_low = trigger_latency

        source_delay = time_high * 1e-3 - base_time_high
        pause_time = time_low * 1e-3 - base_time_low

        if source_delay < 0 or pause_time < 0 :
            print("Error: Pulsewidth too small")
            return 

        print(f"base_time_delay_high: {base_time_high*1e3:.2}ms desired_time_high: {time_high:.2}ms source_delay: {source_delay*1e3:.2}ms")
        print(f"base_time_delay_low: {base_time_low*1e3:.2}ms desired_time_low: {time_low:.2}ms pause_time: {pause_time*1e3:.2}ms")

        period = time_high + time_low
        period = period * 1e-3

        volt_range = 20
        volt_prot = 30

        # Keithley2400 has states IDLE, ARM, TRIG
        # :INIT moves from IDLE to ARM => ARM checks how often to repeat measurment
        # :TRI:COUN how often to measure goes back to :ARM
        # :ARM:COUN  1 extaclty do arm once 

        if self.porttype:
            self.smu.write("++auto 0")
        self.smu.write("*RST")

        self.smu.write(f":DISP:ENAB OFF")
        self.smu.write(":SYST:AZER:STAT OFF") # auto zero off

        self.smu.write(f":SOUR:FUNC CURR")
        self.smu.write(f":SOUR:CURR {current}")

        self.smu.write(f":SOUR:FUNC:CONC OFF") #disable concurrent readings
        if not measure:
            self.smu.write(":SENS:FUNC:OFF:ALL")

        self.smu.write(f":SOUR:CLE:AUTO ON")
        self.smu.write(f":SOUR:DEL {source_delay}")

        if not measure:
            # see p.329 keithley2400 manual 
            # not possible because TRIG:COUNT 1 to 2500
            #self.smu.write(":ARM:COUN 1")
            #self.smu.write(":TRIG:COUN INF")
            self.smu.write(":ARM:COUN INF")
            self.smu.write(":TRIG:COUN 1")

            self.smu.write(":TRIG:SOUR IMM")            # Sofort wiederholen
            self.smu.write(":TRAC:FEED:CONT NEVER")     # Internen Puffer deaktivieren
            self.smu.write(f":TRIG:DEL {pause_time}")
        else:
            self.smu.write(f':SENS:FUNC "VOLT"')
            self.smu.write(f":VOLT:NPLC {nplc}")
            self.smu.write(f":VOLT:RANG {volt_range}")
            self.smu.write(f":VOLT:PROT:LEV {volt_prot}")

            #self.smu.write(":ARM:COUN 1")             # Unendliche Schleife
            #self.smu.write(":TRIG:COUN INF")

            self.smu.write(":ARM:COUN INF")
            self.smu.write(":TRIG:COUN 1")


            self.smu.write(":TRIG:SOUR IMM")            # Sofort wiederholen
            self.smu.write(":TRAC:FEED:CONT NEVER")     # Internen Puffer deaktivieren

            self.smu.write(f":TRIG:DEL {pause_time}")
        #self.smu.write(":OUTP ON")
        self.smu.write(f":INIT")




    def stop(self):

        if self.porttype:
            self.smu.write("++auto 0")
        self.smu.write(":ABOR")
        self.smu.write(":SOUR:CLE:AUTO OFF")
        self.smu.write(":OUTP OFF")
        self.smu.write(":DISP:ENAB ON")
        self.smu.write("*RST")
        self.smu.write("*CLS")
        if self.porttype:
            self.smu.write("++clr")
        #self.smu.close()

        pass

    @staticmethod
    def uid():
        return "Keithley2400"

    @staticmethod
    def find_device(log=False):

        STORAGE = get_storage()
        try:
            port = STORAGE["ports"][Keithley2400Pulse.uid()] 
            if port != None:
                if Keithley2400Pulse._test_port(port, log):
                    return port 
        except:
            pass
        rm = pyvisa.ResourceManager("@py")
        ports = [ x for x in rm.list_resources() if AdapterPortIdentifier.Serial in x or AdapterPortIdentifier.Gpib in x]
        for port in ports:
            if Keithley2400Pulse._test_port(port, log):
                STORAGE["ports"][Keithley2400Pulse.uid()] = port
                return port

    @staticmethod
    def _test_port(port: str, log=False) -> bool:
        rm = pyvisa.ResourceManager("@py")
        device = None

        try:
            device = rm.open_resource(port)
            device.write_termination="\n"
            device.read_termination="\n"
            if AdapterPortIdentifier.Serial in  port:
                device.write("++eos 2") # ar488 appends LF for sending commands
                device.write("++eor 2") # ar488 looks for LF for receiving commands
                device.write("++auto 1") # use auto read when sending a query command ?

            ans = device.query("*IDN?")
            if log:
                print("resp:", ans)
            if "KEITHLEY" in ans:
                print(f"found {Keithley2400Pulse.uid()} at:", port)
                device.close()
                return True
            device.write("*RST;*CLS")
        except Exception as e:
            print(e)
        finally:
            if device is not None:
                try:
                    device.close()
                except:
                    pass
        return False

