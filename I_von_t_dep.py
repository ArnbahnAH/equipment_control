import logging, random, datetime
from re import DOTALL
import time
from time import sleep
import numpy as np
from pymeasure.adapters import VISAAdapter
from pymeasure.experiment import Metadata, IntegerParameter, FloatParameter, Parameter, ListParameter, BooleanParameter
from pymeasure.instruments.keithley import Keithley2600
from pymeasure.instruments.agilent import Agilent34410A
from pymeasure.instruments.oxfordinstruments import ITC503
from pymeasure.instruments import Instrument

# from ..device import Device, make_resourcemanager
# from ..deviceprocedure import DeviceProcedure
# from ..export import export
# from ..windows import MultiDockArg, WindowMultiDock

from equipment_control import WindowSingleDock, DeviceProcedure, Device, make_resourcemanager, DESCRIPTOR, ADAPTER_TYPE


logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s | %(levelname)s | %(name)s | "
        "%(funcName)s:%(lineno)d | %(message)s"
    )
)

log = logging.getLogger(__name__)

_DATA_COLUMNS = [
    "t / s", #0
    "I_sourcemeter / A", #1
    "U_sourcemeter / V", #2
    "U_voltmeter / V", #3
    "R_2probe / V/A", #4
    "R_4probe / V/A", #5
    "1/R_4probe / K" , #6
]

# _multiDockargs = [
#    MultiDockArg(
#        name="I(t)-Kurve",
#        x_axis_label=_DATA_COLUMNS[0], # note this has to match with DATA_COLUMNS otherwise it breaks
#        y_axis_label=_DATA_COLUMNS[1],
#    ) ,
#    MultiDockArg(
#        name="U_nanovoltmeter(t)-Kurve",
#        x_axis_label=_DATA_COLUMNS[0],
#        y_axis_label=_DATA_COLUMNS[3],
#    ) ,
#    MultiDockArg(
#        name="R_4probe(t)-Kurve",
#        x_axis_label=_DATA_COLUMNS[0],
#        y_axis_label=_DATA_COLUMNS[5],
#    ) ,
#    MultiDockArg(
#        name="R_2probe(t)-Kurve",
#        x_axis_label=_DATA_COLUMNS[0],
#        y_axis_label=_DATA_COLUMNS[4],
#    ) ,
#    MultiDockArg(
#        name="1/R_4probe(t)-Kurve",
#        x_axis_label=_DATA_COLUMNS[0],
#        y_axis_label=_DATA_COLUMNS[6],
#    ) ,
# ]

#@export(inner=WindowMultiDock, multiarg=_multiDockargs)
class I_von_t(DeviceProcedure):
    """
    Adapted from Ronalds program
    """
    name = "I_von_t_dep"
    comment = "Copy of Ronald's program Keithley2400 and Agilent NVM."
    inputs = [
              "V_bias",
              "iLimit",
              "nplc",
              "t_max",
              "t_step",
    ]
    displays = inputs
    requested_devices = ["Source Meter: Keithley 2400", "Nanovoltmeter Agilent34410A"]
    default_devices = [
        {"Descriptor":"GPIB0::10::INSTR", "Adapter Type":"GPIB", "GPIB Address" : "10"}, #Keithley2600
        {"Descriptor":"GPIB0::11::INSTR", "Adapter Type":"GPIB", "GPIB Address" : "11"}, #Agilent
    ]
    provided_devices = []
    visa_path = ""


    nplc = FloatParameter(name="Number of Power Line Cycles (NPLC)", minimum=0.01, maximum=10, default = 1)
    V_bias = FloatParameter(name="Bias Voltage", units="mV", minimum=-210E3, maximum=210E3, default = 100 ) #TODO why 210 ?
    iLimit = FloatParameter(name="ILimit", units="muA", minimum=-1.05E6, maximum=1.05E6, default = 100  )
    t_max = FloatParameter(name="t_max", units="s", minimum=1, maximum=3600*24, default = 3600  )
    t_step = FloatParameter(name="t_step", minimum=0.01, maximum=4.0, default = 0.5) #TODO


    DATA_COLUMNS = _DATA_COLUMNS

    keithley2600 : Instrument # pymeasure support? maybe just use pure commands
    agilent34420a : Instrument # pymeasure support?

    keithley2600_connected = False
    _data_to_measure = []
    _delay = 0.01

    time_nvSwitch = 0.02

    def startup(self):
        log.info("started ...")
        manager = make_resourcemanager(custom_visalib_path=self.visa_path)
        if len(self.provided_devices) != len(self.requested_devices) and len(self.provided_devices):
            log.error(fR"equested {len(self.requested_devices)} devices: {self.requested_devices} but got {len(self.provided_devices)} devices: {self.provided_devices}, does not match, aborting!")
            self.shutdown()
            return
        elif len(self.provided_devices) > 0:

            def make_instrument(index, cls):
                """helper to connect instrument
                index: the respective index of the self.provided_devices.
                cls:the measurement class
                """
                info = self.provided_devices[index]
                descriptor = info["Descriptor"]
                adapter_type = info["Adapter Type"]
                connected = False
                try:
                    generic_instrument = Device(descriptor=descriptor,
                                            manager=manager,
                                            adapter_type=adapter_type)
                    connected = generic_instrument.successfully_connected
                    log.info(f"{cls} connected: {connected}")
                    device = cls(adapter=generic_instrument.adapter)
                except Exception as e:
                    print("Error:", e)
                    device = None
                return connected, device
            self.keithley2600_connected, self.keithley2600 = make_instrument(0, Instrument)
            self.agilent34420a_connected, self.agilent34420a = make_instrument(1, Instrument)

        else:
            log.error(f"No devices provided, shutting down!")
            return

        if self.agilent34420a_connected and self.keithley2600_connected :

            iLimit = self.iLimit*1E-6 # A
            V_bias = self.V_bias*1E-3  # V
            nplc = self.nplc
            #self.keithley2600.instrument.write_termination = '\n' # TODO test if this is nesscary
            self.keithley2600.write(":abort")
            self.keithley2600.write("*RST")
            self.keithley2600.write(':sense:function "current"')
            self.keithley2600.write(":source:function voltage")
            self.keithley2600.write(":source:voltage:range:auto on")
            self.keithley2600.write(f":sense:voltage:protection {iLimit}")
            self.keithley2600.write(":format:elements voltage, current")
            self.keithley2600.write(":TRIG:COUN 1")#number of measurements until they will be read by the computer
            self.keithley2600.write(":route:terminals front")
            self.keithley2600.write(f":sense:current:nplcycles {nplc}")
            self.keithley2600.write(":sense:average off")
            self.keithley2600.write(":output:state off")

            self.agilent34420a.write('*RST')
            self.agilent34420a.write(":sense:function \"voltage\"")
            self.agilent34420a.write(":sense:voltage:RANGe:AUTO ON")
            self.agilent34420a.write(f":sense:voltage:NPLCycles {nplc}")
        else:
            if not self.keithley2600_connected:
                log.error(f"Could not connect Keithley2600, shutting down ...")
            if not self.agilent34420a_connected:
                log.error(f"Could not connect Agilent34420a, shutting down ...")
        return

    def execute(self):
        iLimit = self.iLimit*1E-6 # A
        V_bias = self.V_bias*1E-3  # V
        nplc = self.nplc
        self.t = time.time()
        if self.keithley2600_connected and self.agilent34420a_connected:
            log.info("Measurement started ...")

            # NOTE on roland's program we are skipping the append mode which pymeasure can handle for us
            self.keithley2600.write(f":source:voltage:level {V_bias}")   #set source meter voltage to self.V_bias
            self.keithley2600.write(":output:state on")   #set source meter output to state on

            while ( time.time() - self.t) < self.t_max:

                if self.should_stop():
                    break
                values = self.keithley2600.ask(":read?").split(",")
                values_vMeter = self.agilent34420a.ask(":read?")
                r2probe = float(values[0])/float(values[1])
                r4probe = float(values_vMeter)/float(values[1])
                s4probe = float(values[1])/float(values_vMeter)
                t = time.time() - self.t
                return_data = {
                    _DATA_COLUMNS[0]: t,
                    _DATA_COLUMNS[1]: values[1],
                    _DATA_COLUMNS[2]: values[0],
                    _DATA_COLUMNS[3]: values_vMeter,
                    _DATA_COLUMNS[4]: r2probe,
                    _DATA_COLUMNS[5]: r4probe,
                    _DATA_COLUMNS[6]: s4probe
                }
                self.emit('results', return_data)
                log.debug("Emitting results: {return_data}")

                #TODO sleep t_step?
                remaining = self.t_step
                while remaining > 0:
                    if self.should_stop():
                        break
                    sleeptime = min(1, remaining)
                    time.sleep(sleeptime)
                    remaining -= sleeptime



            self.keithley2600.write(":source:voltage:level 0.0")
            self.keithley2600.write(":output:state:off")
        return

    def shutdown(self):
        try:
            if self.keithley2600_connected:
                self.keithley2600.close()
            else:
                log.error("keithley2600_Measurement:Unable to shutdown Source Meter.")

            if self.agilent34420a_connected:
                self.agilent34420a.close()
            else:
                log.error("agilent34420a_Measurement:Unable to shutdown Agilent34420a.")

        except Exception as e:
            log.error("keithley2600_Measurement:Unable to shutdown Source Meter.", e)
        super().shutdown()
