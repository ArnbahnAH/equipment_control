import logging, random, datetime
import time
from time import sleep
import numpy as np
from pymeasure.adapters import VISAAdapter
from pymeasure.experiment import Metadata, IntegerParameter, FloatParameter, Parameter, ListParameter, BooleanParameter
from pymeasure.instruments.keithley import Keithley2600
from pymeasure.instruments.agilent import Agilent34410A
from pymeasure.instruments import Instrument

#from ..export import export
#from ..windows import MultiDockArg, WindowMultiDock
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
    "T3 / K", #0
    "U_sourcemeter / V", #1
    "I_sourcemeter / A", #2
    "U_nanovoltmeter_1 / V", #3
    "U_nanovoltmeter_2 / V", #4
    "T1 / K", #5
    "T2 / K" , #6
    "time / s" #7
]


#_multiDockargs = [
#   MultiDockArg(
#       name="U(B)-Kurve, Sourcemeter",
#       x_axis_label=_DATA_COLUMNS[0], # note this has to match with DATA_COLUMNS otherwise it breaks
#       y_axis_label=_DATA_COLUMNS[1],
#   ) ,
#   MultiDockArg(
#       name="T3(B)-Kurve, Temperaturstabilität",
#       x_axis_label=_DATA_COLUMNS[0],
#       y_axis_label=_DATA_COLUMNS[7],
#   ) ,
#   MultiDockArg(
#       name="U(B)-Kurve, Nanovoltmeter, Channel 1",
#       x_axis_label=_DATA_COLUMNS[0],
#       y_axis_label=_DATA_COLUMNS[3],
#   ) ,
#   MultiDockArg(
#       name="U(B)-Kurve, Nanovoltmeter, Channel 2",
#       x_axis_label=_DATA_COLUMNS[0],
#       y_axis_label=_DATA_COLUMNS[4],
#   ) ,
#]
#
## TODO which keithley
## temperature is contrlled externally this just reads it
#@export(inner=WindowMultiDock, multiarg=_multiDockargs)
class WhiteCryoUvT(DeviceProcedure):
    """
    white cryo current driven temperature measurment. Temperature control has to be done by the controller this only reads it.
    There are options for sourcemeter only, sourcemeter+NanovoltmeterCh1 and sourcemeter+NanovoltmeterCh1+NanovoltmeterCh2
    the missing Nanovoltmeter channels will be filled by None which will show up as NaN in the file.
    Adapted from Ronalds program
    assuming that we use a keithley2600, agilent34420a, lakeshore 340
    """
    name = "White Cryo UvT"
    comment = "Copy of Ronald's White Cryo UvT using either Keithley2600 or Keithley2600 SMU+ Agilent NVM."
    inputs = [
              "measurement_mode",
              "sourcemeter_rs",
              "remove_emf",
              "voltage_limit_mV",
              "probe_current",
              "nplc",
    ]
    displays = inputs
    requested_devices = ["Temp controller LS340", "Source Meter: Keithley 2600", "Nanovoltmeter Agilent34410A"]
    default_devices = [
        {"Descriptor":"GPIB0::12::INSTR", "Adapter Type":"GPIB", "GPIB Address" : "12"}, #LS340
        {"Descriptor":"GPIB0::10::INSTR", "Adapter Type":"GPIB", "GPIB Address" : "10"}, #Keithley2600
        {"Descriptor":"GPIB0::11::INSTR", "Adapter Type":"GPIB", "GPIB Address" : "11"}, #Agilent
    ]
    provided_devices = []
    visa_path = ""

    measurement_mode = ListParameter(name="Two Probe, Four probe, Fourprobe with Channel 2", choices=["Two", "Four", "Four+Ch2"], default="Two")
    sourcemeter_rs = BooleanParameter(name="Use sourcemeter remote sense", default=False)
    remove_emf = BooleanParameter(name="Remove emf", default=False)

    nplc = FloatParameter(name="Number of Power Line Cycles (NPLC)", minimum=0.01, maximum=10, default = 1)
    voltage_limit_mV = FloatParameter(name="Voltage limit", units="mV", minimum=-210E3, maximum=210E3, default = 100 ) #TODO why 210 ?
    probe_current = FloatParameter(name="Probe Current", units="muA", minimum=-1.05E6, maximum=1.05E6, default = 10  )

    # T3 [K] 	 U_sourcemeter [V] 	 I_sourcemeter [A] 	 U_nanovoltmeter_1 [V] 	 U_nanovoltmeter_2 [V] 	 T1 [K] 	 T2 [K] 	 time [s] 	 @ Probenstrom 1e-05A, Spannungsbegrenzung 0.1V
    DATA_COLUMNS = _DATA_COLUMNS

    #TODO which keithley is there? I think keithley2600
    ls340 : Instrument
    keithley2600 : Instrument # pymeasure support? maybe just use pure commands
    agilent34420a : Instrument # pymeasure support?

    keithley2600_connected = False
    ls340_connected = False
    agilent34420a_connected = False

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

            self.ls340_connected, self.ls340 = make_instrument(0, Instrument)
            self.keithley2600_connected, self.keithley2600 = make_instrument(1, Instrument)
            self.agilent34420a_connected = False
            if self.measurement_mode in ["Four", "Four+Ch2"]:
                self.agilent34420a_connected, self.agilent34420a = make_instrument(2, Instrument)

        else:
            log.error(f"No devices provided, shutting down!")
            return

        if self.ls340_connected and self.keithley2600_connected :

            #self.ls340.instrument.read_termination = '\r' # TODO test if this is nesscary
            #self.ls340.instrument.write_termination = '\r' # TODO test if this is nesscary
            #self.keithley2600.instrument.write_termination = '\n' # TODO test if this is nesscary
            #self.agilent34420a.instrument.write

            probe_current = self.probe_current*1E-6 # A
            voltage_limit = self.voltage_limit_mV*1E-3  # V

            self.keithley2600.write("smua.reset()")
            self.keithley2600.write("smua.source.func = smua.OUTPUT_DCAMPS") # current mode
            self.keithley2600.write("smua.source.leveli = 0.0")
            self.keithley2600.write("smua.source.autorangei = smua.AUTORANGE_ON")
            self.keithley2600.write(f"smua.source.limitv = {voltage_limit}")
            self.keithley2600.write(f"smua.source.leveli = {probe_current}")
            self.keithley2600.write("smua.measure.autorangev = smua.AUTORANGE_ON")
            self.keithley2600.write(f"smua.measure.nplc = {self.nplc}")
            self.keithley2600.write("display.smua.measure.func = display.MEASURE_DCVOLTS")
            self.keithley2600.write("smua.source.output = smua.OUTPUT_OFF")

            if self.sourcemeter_rs:
                self.keithley2600.write("smua.sense = smua.SENSE_REMOTE")
            else:
                self.keithley2600.write("smua.sense = smua.SENSE_LOCAL")

            if self.measurement_mode in ["Four", "Four+Ch2"]:
                if self.agilent34420a_connected:
                    self.agilent34420a.write('*RST')
                    self.agilent34420a.write(":sense:function \"voltage\"")
                    self.agilent34420a.write(":sense:voltage:RANGe:AUTO ON")
                    self.agilent34420a.write(f":sense:voltage:NPLCycles {self.nplc}")
        else:
            if not self.keithley2600_connected:
                log.error(f"Could not connect Keithley2600, shutting down ...")
            if not self.ls340_connected:
                log.error(f"Could not connect ls340, shutting down ...")
            if self.measurement_mode in ["Four", "Four+Ch2"] and not self.agilent34420a_connected:
                log.error(f"Could not connect Agilent34420a, shutting down ...")
        return

    def execute(self):
        probe_current = self.probe_current*1E-6 # A
        voltage_limit = self.voltage_limit_mV*1E-3  # V
        if self.keithley2600_connected and self.ls340_connected:
            log.info("Measurement started ...")

            # NOTE on roland's program we are skipping the append mode which pymeasure can handle for us

            # TODO roland mixes try: expect: and read/ask why?
            #idn = self.keithley2600.ask("*IDN?")
            #assert(idn != "")
            self.ls340.clear()
            def read_temp():
                self.ls340.write("KRDG?A")
                temp_1 = self.ls340.read().split("\r")[0]#TODO check this
                self.ls340.write("KRDG?B")
                temp_2 = self.ls340.read().split("\r")[0]#TODO check this
                self.ls340.write("KRDG?C")
                temp_3 = self.ls340.read().split("\r")[0]#TODO check this
                return temp_1, temp_2, temp_3
            temp_1, temp_2, temp_3 = read_temp()
            time_start = time.time()
            time_new = time.time()
            time.sleep(0.2)
            self.keithley2600.write("smua.source.output = smua.OUTPUT_ON")
            while not self.should_stop():
                if self.should_stop():
                    break
                temperature_old = temp_2
                time_old = time_new
                time_new = time.time()

                if self.measurement_mode in ["Four", "Four+Ch2"]:
                    self.agilent34420a.write(":route:terminals front1")
                self.keithley2600.write("ireading, vreading = smua.measure.iv()")
                if self.measurement_mode in ["Four", "Four+Ch2"]:
                    self.agilent34420a.write(":initiate")

                #self.ls340.clear()
                temp_1, temp_2, temp_3 = read_temp()
                values_nvMeter_1 = None
                values_nvMeter_2 = None
                if self.measurement_mode in ["Four", "Four+Ch2"]:
                    self.agilent34420a.write(":fetch?")
                    values_nvMeter_1 = self.agilent34420a.read().rstrip()
                    if self.measurement_mode in ["Four+Ch2"]:
                        self.agilent34420a.write(":route:terminals front2")
                        time.sleep(self.time_nvSwitch)
                        self.agilent34420a.write(":read?")
                        values_nvMeter_2 = self.agilent34420a.read().rstrip()
                        self.agilent34420a.write(":route:terminals front1")
                self.keithley2600.write("printnumber(vreading,ireading)")
                values = self.keithley2600.read().rstrip().split(",")
                if self.remove_emf:
                    #self.keithley2600.write("printnumber(vreading,ireading)")
                    self.keithley2600.write(f"smua.source.leveli = {-1*probe_current}")
                    self.keithley2600.write("ireading, vreading = smua.measure.iv()")
                    if self.measurement_mode in ["Four", "Four+Ch2"]:
                        self.agilent34420a.write(":initiate")
                    if self.measurement_mode in ["Four", "Four+Ch2"]:
                        self.agilent34420a.write(":fetch?")
                        values_nvMeter_emf_1 = self.agilent34420a.read().rstrip()
                        if self.measurement_mode in ["Four+Ch2"]:
                            self.agilent34420a.write(":route:terminals front2")
                            time.sleep(self.time_nvSwitch)
                            self.agilent34420a.write(":read?")
                            values_nvMeter_emf_2 = self.agilent34420a.read().rstrip()
                            self.agilent34420a.write(":route:terminals front1")
                            values_nvMeter_2 = str((float(values_nvMeter_2)+(-1)*float(values_nvMeter_emf_2))/2.0)
                        values_nvMeter_1 = str((float(values_nvMeter_1)+(-1)*float(values_nvMeter_emf_1))/2.0)

                    self.keithley2600.write("printnumber(vreading,ireading)")
                    values_emf = self.keithley2600.read().rstrip().split(",")
                    self.keithley2600.write(f"smua.source.leveli = {probe_current}")
                    values[0] = str((float(values[0])+(-1)*float(values_emf[0]))/2.0)
                    values[1] = str((float(values[1])+(-1)*float(values_emf[1]))/2.0)
                dTdt = (float(temp_2) - float(temperature_old))/((time_new-time_old)/60.0)
                data = f"\nT={str(temp_3)[0:6]}K | dT/dt= {str(dTdt)[0:5]}K/min | U={float(values[0]):2e}V"
                return_data = {
                    _DATA_COLUMNS[0]: temp_3,
                    _DATA_COLUMNS[1]: values[0],
                    _DATA_COLUMNS[2]: values[1],
                    _DATA_COLUMNS[3]: values_nvMeter_1,
                    _DATA_COLUMNS[4]: values_nvMeter_2,
                    _DATA_COLUMNS[5]: temp_1,
                    _DATA_COLUMNS[6]: temp_2,
                    _DATA_COLUMNS[7]: time.time()
                }
                self.emit('results', return_data)
                log.debug("Emitting results: %s" % return_data)
                #self.emit('progress', progress)

                time.sleep(0.5)
            self.keithley2600.write("smua.source.leveli = 0.0")
            self.keithley2600.write("smua.source.output = smua.OUTPUT_OFF")
            self.keithley2600.write("smua.source.offmode = smua.OUTPUT_HIGH_Z")

        return

    def shutdown(self):
        try:
            if self.keithley2600_connected:
                self.keithley2600.close()
            else:
                log.error("keithley2600_Measurement:Unable to shutdown Source Meter.")

            if self.ls340_connected:
                self.ls340.close()
            else:
                log.error("ls340_Measurement:Unable to shutdown ls340.")

            if self.agilent34420a_connected:
                self.agilent34420a.close()
            else:
                log.error("agilent34420a_Measurement:Unable to shutdown Agilent34420a.")

        except Exception as e:
            log.error("keithley2600_Measurement:Unable to shutdown Source Meter. ", e)
        super().shutdown()

    #def get_estimates(self):
    #    return self.number_of_datapoints*self.number_of_steps*self.pause_per_step_ms*1E-3
