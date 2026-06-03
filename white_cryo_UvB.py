import logging, random, datetime
import math
import time
from time import sleep
import numpy as np
from pymeasure.adapters import VISAAdapter
from pymeasure.experiment import Metadata, IntegerParameter, FloatParameter, Parameter, ListParameter, BooleanParameter, Results
from pymeasure.instruments import Instrument
from pymeasure.instruments.keithley import Keithley2600
from pymeasure.instruments.agilent import Agilent34410A

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

_DATA_COLUMNS = [
    "B / T", #0
    "U_sourcemeter / V", #1
    "I_sourcemeter / A", #2
    "U_nanovoltmeter_1 / V", #3
    "U_nanovoltmeter_2 / V", #4
    "T1 / K", #5
    "T2 / K" , #5
    "T3 / K", #7
    "time / s" #8
]

log = logging.getLogger(__name__)


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
#
#]
#@export(inner=WindowMultiDock, multiarg=_multiDockargs)
class WhiteCryoUvB(DeviceProcedure):
    """
    white cryo current driven magnetic field measurment.
    There are options for sourcemeter only, sourcemeter+NanovoltmeterCh1 and sourcemeter+NanovoltmeterCh1+NanovoltmeterCh2
    the missing Nanovoltmeter channels will be filled by None which will show up as NaN in the file.
    Adapted from Ronalds program
    assuming that we use a keithley2600, agilent34420a, lakeshore 340
    """
    name = "White Cryo UvB"
    comment = "Copy of Ronald's White Cryo UvB using either Keithley2600 or Keithley2600 SMU+ Agilent NVM."
    inputs = [
              "measurement_mode",
              "sourcemeter_rs",
              "remove_emf",
              "voltage_limit_mV",
              "probe_current",
              "B_start",
              "B_end",
              "B_steps",
              "repetitions",
              "nplc",
    ]
    displays = inputs
    requested_devices = ["Temp controller LS340", "Source Meter: Keithley 2600", "Nanovoltmeter Agilent34410A", "Magnet"]
    default_devices = [
        {"Descriptor":"GPIB0::12::INSTR", "Adapter Type":"GPIB", "GPIB Address" : "12"}, #LS340
        {"Descriptor":"GPIB0::10::INSTR", "Adapter Type":"GPIB", "GPIB Address" : "10"}, #Keithley2600
        {"Descriptor":"GPIB0::11::INSTR", "Adapter Type":"GPIB", "GPIB Address" : "11"}, #Agilent
        {"Descriptor":"GPIB0::4::INSTR", "Adapter Type":"GPIB", "GPIB Address" : "4"}, #Magnet
    ]
    provided_devices = []
    visa_path = ""

    measurement_mode = ListParameter(name="Two Probe, Four probe, Fourprobe with Channel 2", choices=["Two", "Four", "Four+Ch2"], default="Two")
    sourcemeter_rs = BooleanParameter(name="Use sourcemeter remote sense", default=False)
    remove_emf = BooleanParameter(name="Remove emf", default=False)
    B_start = FloatParameter(name="Field to start at", units="T" , minimum=-8.0, maximum=8.0, default = 0.0) #TODO
    B_end = FloatParameter(name="Field to end at", units="T", minimum=-8.0, maximum=8.0, default = 1.0) #TODO
    B_steps = IntegerParameter(name="How many steps to transverse from B_end to B_start", minimum=0, maximum=100_000, default = 100) #TODO
    repetitions = IntegerParameter(name="How often to reapt the sweep", minimum=1.0, maximum=10.0, default = 1.0) #TODO

    nplc = FloatParameter(name="Number of Power Line Cycles (NPLC)", minimum=0.01, maximum=10, default = 1)
    voltage_limit_mV = FloatParameter(name="Voltage limit", units="mV", minimum=-210E3, maximum=210E3, default = 100 ) #TODO why 210 ?
    probe_current = FloatParameter(name="Probe Current", units="muA", minimum=-1.05E6, maximum=1.05E6, default = 10  )

    # B [T] U_sourcemeter [V] I_sourcemeter [A] U_nanovoltmeter_1 [V] U_nanovoltmeter_2 [V] T1 [K] T2 [K] T3 [K] time [s] # @ Probenstrom str(self.I_probe)A, Spannungsbegrenzung str(self.VLimit)V
    # TODO the order of the emitted columns is important we plot [0] vs [1] by default
    DATA_COLUMNS = _DATA_COLUMNS

    #TODO which keithley is there? I think keithley2600?
    ls340 : Instrument
    keithley2600 : Instrument # pymeasure support? maybe just use pure commands
    agilent34420a : Instrument # pymeasure support?
    magnet: Instrument

    keithley2600_connected = False
    ls340_connected = False
    agilent34420a_connected = False
    magnet_connected = False

    file_avg = None
    _data_to_measure = []

    time_nvSwitch = 0.02
    time_magnet = 0.5
    time_points = 0.5
    imax = 78.2
    bmax = 8.0
    AmpsPerTesla = 9
    AmpsPerTesla = 9.755555  # A/T
    SleepTimeMagnet = 0.1


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
            self.magnet_connected, self.magnet = make_instrument(3, Instrument)

        else:
            log.error(f"No devices provided, shutting down!")
            return

        if self.ls340_connected and self.keithley2600_connected and self.magnet_connected:

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
                    self.agilent34420a.write(':sense:function "voltage"')
                    self.agilent34420a.write(":sense:voltage:RANGe:AUTO ON")
                    self.agilent34420a.write(f":sense:voltage:NPLCycles {self.nplc}")
                    self.agilent34420a.write(":trigger:source bus")


            # magnet stuff
            self.magnet.read_termination = "\r\n" # TODO figure this out probably run some tests first before you run this class
            self.magnet.write_termination = "\r\n" # TODO figure this out probably run some tests first before you run this class
            self.magnet.write("T0")
            self.magnet.write("P1")

            """ New value by Alfons and Michael """
            BRate = 0.02  # T/s, max: 0.05
            BRate_max = 0.05
            """ old value by Roland """
            #BRate = 0.005		#maximum 0.006 T/s
            IRate = min(BRate, BRate_max) * self.AmpsPerTesla
            IRateStr = str(IRate)
            if IRate < 10:
                IRateStr = "0" + IRateStr
            IRateStr = IRateStr[0:8]
            while len(IRateStr) < 8:
                IRateStr = IRateStr + "0"
            log.info(f"IRate: {IRateStr}")
            self.magnet.instrument.write(f"A{IRateStr}")    #rampRate

            if self.repetitions > 0:
                # TODO average saving...
                pass



        else:
            if not self.keithley2600_connected:
                log.error(f"Could not connect Keithley2600, shutting down ...")
            if not self.ls340_connected:
                log.error(f"Could not connect ls340, shutting down ...")
            if self.measurement_mode in ["Four", "Four+Ch2"] and not self.agilent34420a_connected:
                log.error(f"Could not connect Agilent34420a, shutting down ...")
            if not self.magnet_connected:
                log.error(f"Could not connect Keithley2600, shutting down ...")
        return

    def execute(self):
        if self.keithley2600_connected and self.ls340_connected and self.magnet_connected:
            log.info("Measurement started ...")

            # TODO rolands program uses repetitions to save each run seperate I think
            # this does not fit cleanly into how pymeasure works. Probably
            # have to rely on sequencer for this.
            # Ask Sebastian does anyone use this?

            # TODO roland mixes try: expect: and read/ask why?
            #idn = self.keithley2600.ask("*IDN?")
            #assert(idn != "")
            self.ls340.clear()
            temp_1, temp_2, temp_3 = self.read_temp()
            time_start = time.time()
            self.keithley2600.write("smua.source.output = smua.OUTPUT_ON")


            for i in range(0, self.B_steps+1):
                if not self.measure_cylce(i):
                    break

            self.B_start, self.B_end = self.B_end, self.B_start
            for i in range(1, 2 * self.B_steps+1):
                if not self.measure_cylce(i):
                    break

            self.B_start = -self.B_start
            for i in range(1, self.B_steps+1):
                if not self.measure_cylce(i):
                        break
            pass
            self.keithley2600.write("smua.source.leveli = 0.0")
            self.keithley2600.write("smua.source.output = smua.OUTPUT_OFF")
            self.keithley2600.write("smua.source.offmode = smua.OUTPUT_HIGH_Z")
        return

    def read_temp(self):
        self.ls340.write("KRDG?A")
        temp_1 = self.ls340.read().split("\r")[0]#TODO check this
        self.ls340.write("KRDG?B")
        temp_2 = self.ls340.read().split("\r")[0]#TODO check this
        self.ls340.write("KRDG?C")
        temp_3 = self.ls340.read().split("\r")[0]#TODO check this
        return temp_1, temp_2, temp_3

    def measure_cylce(self, i:int ) -> bool:
        """
        runs the magnet sweep in one direction
        i: B_step index
        returns False if early break true otherwise
        """
        probe_current = self.probe_current*1E-6 # A
        voltage_limit = self.voltage_limit_mV*1E-3  # V
        if self.should_stop():
            return False
        if self.repetitions > 0:
            T_avg = 0.0
            i_avg = 0.0
            u_avg = 0.0
            u_nv1_avg = float('nan')
            u_nv2_avg = float('nan')
            if self.measurement_mode in ["Four", "Four+Ch2"]:
                u_nv1_avg = 0.0
                if self.measurement_mode in [ "Four+Ch2"]:
                    u_nv2_avg = 0.0
        B_value = self.B_start + float(i)*(self.B_end-self.B_start)/float(self.B_steps)
        if abs(B_value) <= self.bmax:
            self.set_B(B_value)
        else:
            sign = B_value/abs(B_value)
            self.set_B(float(sign)*self.bmax)
            B_value = float(sign)*self.bmax

        for j in range(self.repetitions+1):
            if self.should_stop():
                return False

            if self.measurement_mode in ["Four", "Four+Ch2"]:
                self.agilent34420a.write(":route:terminals front1")
            self.keithley2600.write("ireading, vreading = smua.measure.iv()")
            if self.measurement_mode in ["Four", "Four+Ch2"]:
                self.agilent34420a.write(":initiate")
                self.agilent34420a.write("*TRG")
            #self.ls340.clear()
            temp_1, temp_2, temp_3 = self.read_temp()
            values_nvMeter_1 = float('nan')
            values_nvMeter_2 = float('nan')
            values = self.keithley2600.ask("printnumber(vreading,ireading)").split(",")
            if self.measurement_mode in ["Four", "Four+Ch2"]:
                values_nvMeter_1 =  self.agilent34420a.ask(":fetch?")
                if self.measurement_mode in ["Four+Ch2"]:
                    self.agilent34420a.write(":route:terminals front2")
                    time.sleep(self.time_nvSwitch)
                    self.agilent34420a.write(":initiate")
                    self.agilent34420a.write("*TRG")
                    time.sleep(float(self.nplc)*0.02)
                    values_nvMeter_2 = self.agilent34420a.ask(":fetch?")
                    self.agilent34420a.write(":route:terminals front1")
            if self.remove_emf:
                #self.keithley2600.write("printnumber(vreading,ireading)")
                self.keithley2600.write(f"smua.source.leveli = {-1*probe_current}")
                self.keithley2600.write("ireading, vreading = smua.measure.iv()")
                if self.measurement_mode in ["Four", "Four+Ch2"]:
                    self.agilent34420a.write(":initiate")
                    self.agilent34420a.write("*TRG")
                values_emf = self.keithley2600.ask("printnumber(vreading,ireading)").split(",")
                if self.measurement_mode in ["Four", "Four+Ch2"]:
                    values_nvMeter_emf_1 = self.agilent34420a.write(":fetch?")
                    if self.measurement_mode in ["Four+Ch2"]:
                        self.agilent34420a.write(":route:terminals front2")
                        time.sleep(self.time_nvSwitch)
                        self.agilent34420a.write(":initiate")
                        self.agilent34420a.write("*TRG")
                        values_nvMeter_emf_2 = self.agilent34420a.ask(":fetch?")
                        self.agilent34420a.write(":route:terminals front1")
                        values_nvMeter_2 = str((float(values_nvMeter_2)+(-1)*float(values_nvMeter_emf_2))/2.0)
                    values_nvMeter_1 = str((float(values_nvMeter_1)+(-1)*float(values_nvMeter_emf_1))/2.0)
                self.keithley2600.write(f"smua.source.leveli = {probe_current}")
                values[0] = str((float(values[0])+(-1)*float(values_emf[0]))/2.0)
                values[1] = str((float(values[1])+(-1)*float(values_emf[1]))/2.0)
            data = f"B={float(B_value):.3e}T | T={temp_3:.2f}K | U={float(values[0]):.2e}V"
            log.info(data)
            return_data = { #TODO this sucks
                    _DATA_COLUMNS[0] : B_value,
                    _DATA_COLUMNS[1] : values[0],
                    _DATA_COLUMNS[2] : values[1],
                    _DATA_COLUMNS[3] : values_nvMeter_1,
                    _DATA_COLUMNS[4] : values_nvMeter_2,
                    _DATA_COLUMNS[5] : temp_1,
                    _DATA_COLUMNS[6] : temp_2,
                    _DATA_COLUMNS[7] : temp_3,
                    _DATA_COLUMNS[8] : time.time()
            }
            self.emit('results', return_data)
            log.debug("Emitting results: %s" % return_data)
            if self.repetitions > 0:
                T_avg = T_avg + float(temp_3)
                i_avg = i_avg + float(values[0])
                u_avg = u_avg + float(values[1])
                if self.measurement_mode in ["Four", "Four+Ch2"]:
                    u_nv1_avg = u_nv1_avg + float(values_nvMeter_1)
                    if self.measurement_mode in ["Four+Ch2"]:
                        u_nv2_avg = u_nv2_avg + float(values_nvMeter_2)
            time.sleep(self.time_points)
        if self.repetitions > 0:
            T_avg = T_avg / float(self.repetitions+1)
            i_avg = i_avg / float(self.repetitions+1)
            u_avg = u_avg / float(self.repetitions+1)
            if self.measurement_mode in ["Four", "Four+Ch2"]:
                u_nv1_avg = u_nv1_avg / float(self.repetitions+1)
                if self.measurement_mode in ["Four+Ch2"]:
                    u_nv2_avg = u_nv2_avg / float(self.repetitions+1)
            result = {
                B_value,
                u_avg,
                i_avg,
                u_nv1_avg,
                u_nv2_avg,
                T_avg
            }
            # TODO write to file_avg
        return True

    def set_B(self, BSet):

        log.info(f"set B field: {BSet}")
        self.magnet.write("G")
        IMagnet = float(self.magnet.read()[1:9])
        log.info(f"IMagnet: {IMagnet}")
        if float(IMagnet) * float (BSet) < 0:    #if actual current has different sign than BSet: ramp field first to zero
            self.magnet.write("P1")    #pause
            time.sleep(self.SleepTimeMagnet)
            #gpib.write(self.magnet, "U000.000") # 0.0 Tesla
            self.magnet.write("U000.000") # 0.0 Tesla #TODO Roland did not add \r\n here?
            time.sleep(self.SleepTimeMagnet)
            self.magnet.write("R2") # Go to Upper Set Point
            time.sleep(self.SleepTimeMagnet)
            self.magnet.write("P0")    #no pause
            time.sleep(self.SleepTimeMagnet)
            self.stabelizeB()
            while True:
                time.sleep(self.SleepTimeMagnet)
                self.magnet.write("G")    #ask for output parameters
                IMagnet = float(self.magnet.read()[1:9])
                if IMagnet == 0 or self.should_stop() == False:
                    break
        self.magnet.write("P1")    #pause
        time.sleep(self.SleepTimeMagnet)
        if BSet >= 0:
            self.magnet.write("D0")    #change sign to plus
        else:
            self.magnet.write("D1")    #change sign to minus

        time.sleep(self.SleepTimeMagnet)
        ISet = BSet * self.AmpsPerTesla
        if ISet < 0:
            ISet = ISet * -1.0
        ISetCommand = str(ISet)
        if ISet < 10:
            ISetCommand = "0" + ISetCommand
        if ISet < 100:
            ISetCommand = "0" + ISetCommand
        while len(ISetCommand) < 7:
            ISetCommand = ISetCommand + "0"
        self.magnet.write("U" + ISetCommand) # set new current # TODO again no \r\n
        time.sleep(self.SleepTimeMagnet)
        self.magnet.write("R2") # Go to Upper Set Point
        time.sleep(self.SleepTimeMagnet)
        self.magnet.write("P0")    #no pause
        time.sleep(self.SleepTimeMagnet)
        while True:
            self.magnet.write("G")    #ask for output parameters
            try:
                real_current = float(self.magnet.read()[1:9])
                log.info(f"real current {real_current}")
                log.info(f"I_set {ISet}")
                if abs(abs(real_current) - abs(round(ISet,3))) < 0.015 or (abs(abs(real_current) - abs(round(ISet,3))))/abs(ISet) < 0.001:
                    break
                time.sleep(self.SleepTimeMagnet)
            except:
                pass



    def stabilizeB(self):
        while True:
            if self.should_stop():
                break
            self.magnet.write("K") # ask for status
            rampingFinished = self.magnet.read()[3:4]
            log.info(f"rampingFinished {rampingFinished}")
            if rampingFinished == "1":
                time.sleep(0.5)
                break
            time.sleep(self.SleepTimeMagnet)
            self.magnet.write("G") # ask for output parameters
            IMagnet = self.magnet.read()[1:9]
            log.info(f"IMagnet: {IMagnet}")
            time.sleep(1)
        self.magnet.write("P1") # pause

    def shutdown(self):
        try:
            if self.keithley2600_connected:
                self.keithley2600.close()
            else:
                log.error("Unable to shutdown Source Meter.")

            if self.ls340_connected:
                self.ls340.close()
            else:
                log.error("Unable to shutdown ls340.")

            if self.agilent34420a_connected:
                self.agilent34420a.close()
            else:
                log.error("Unable to shutdown Agilent34420a.")

            if self.magnet_connected:
                self.magnet.close()
            else:
                log.error("Unable to shutdown magnet.")

        except Exception as e:
            log.error("Unable to shutdown Source Meter. ", e)
        super().shutdown()

    #def get_estimates(self):
    #    return self.number_of_datapoints*self.number_of_steps*self.pause_per_step_ms*1E-3
