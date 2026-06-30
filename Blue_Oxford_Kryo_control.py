#   Blue (new) Oxford Cryo control
#   2026

import sys, datetime, logging, time
import numpy as np

log = logging.getLogger()

from pymeasure.display.Qt import QtWidgets
from pymeasure.experiment import IntegerParameter, FloatParameter, Parameter, ListParameter, BooleanParameter, Metadata
from pymeasure.instruments import Instrument
from pymeasure.instruments.keithley.keithley2600 import Keithley2600
from pymeasure.instruments.keithley.keithley2600 import Channel as Keithley2600_Channel
from pymeasure.instruments.oxfordinstruments import ITC503, IPS120_10

### Own files
from equipment_control import WindowSingleDock, DeviceProcedure, Device, make_resourcemanager, DESCRIPTOR, ADAPTER_TYPE

class BlueOxfordCryo_MagnetControl(DeviceProcedure):
    """This procedure controls the Keithley 2636A Sourcemeter. 2- and 4-probe measurement are possible, with the 4-probe needing an optional voltmeter (procedure is tested with the Agilent 34420A but any SCPI '*read' capable voltmeter should work) and 'Use Voltmeter' set as True.\n

    The procedure is intended to be used for measuring magnetic field dependent current-voltage characteristics, for this the Sourcemeter is connected on one channel with the sample and on the other channel with a magnet. A current is applied to realise the desired magnetic field. The magnitude of the applied current is determined by the magnet dependent 'Field to Current ratio' in Tesla per Ampere. This ratio is used to calculate all magnetic field values presented from the measured applied current by the Sourcemeter.\n
    
    Data Columns
    
    Current / muA
        The current applied / measured on the channel connected to the sample. All values are directly supplied by the Sourcemeter.
    Voltage Sourcemeter / mV
        The voltage applied / measured on the channel connected to the sample. All values are directly supplied by the Sourcemeter.
    Voltage Voltmeter / mV
        (optional, None if no voltmeter used). The voltage measured by the voltmeter.
    Magnetic field / mT
        Values calculated from 'Field to Current ratio' using the current applied on the channel for the magnet.
    Resistance Sourcemeter / Ohm
        Values calculated from 'Current / muA' and 'Voltage Sourcemeter / mV'.
    Resistance Voltmeter / Ohm
        Values calculated from 'Current / muA' and 'Voltage Voltmeter / mV'.
    Time / s
        Time the measurement of a datapoint is started relative to the start of the whole procedure.
    Duration / s
        The duration of measuring one datapoint, i.e. the time it took for all the instruments to respond + averaging if enabled.
    Temperature / K
        The temperature 3 of the OXFORD ITC 503S (sample temperature). The procedure will attempt to read the temperature for a few times. Sometimes a decimal place can be missing when an invalid return is read, this causes an apparent jump in the temperature which is not real.
    """
    name = "Blue Oxford Cryostat magnetic field dependent 2 and 4 probe control"
    inputs = ["use_magnet_power_supply","measure_voltmeter","measure_sourcemeter", "measure_temperatures","advanced_options","filtering","filter_count","filtering_delay_ms","filter_voltmeter","filter_sourcemeter","built_in_voltmeter_average","built_in_voltmeter_average_count","built_in_voltmeter_filter","built_in_voltmeter_filter_type","built_in_voltmeter_filter_speed","channel_mesurement","sweep_direction_mesurement","number_of_steps_measurement","pause_per_step_measurement_ms","channel_magnet","sweep_direction_magnet","number_of_steps_magnet","pause_per_step_magnet_ms","field_to_current_ratio_T_per_A","apply_current","apply_voltage","measure_current","measure_voltage","nplc_sourcemeter","nplc_voltmeter","number_of_datapoints_measurement","current_limit_muA","maximum_voltage_mV","minimum_voltage_mV","voltage_limit_mV","maximum_current_muA","minimum_current_muA","number_of_datapoints_magnet","voltage_limit_magnetic_field_V","minimum_magnetic_field_mT","maximum_magnetic_field_mT","parameter_comment"]
    tool_tip_information = {"use_magnet_power_supply":"Use the dedicated magnet power supply instead of the Sourcemeter, the field to current ration is now unimportant but should not be 0.","parameter_comment":"Information about the measurement to be shown in the data file as a parameter. Has no influence on the measurement.","measure_voltmeter" : "Option to use a voltmeter to measure the voltage. Source meter will then only supply current","measure_sourcemeter" : "Option to disable measuring Source meter values, can improve measurement time if the Source meter values are unimportant.", "measure_temperatures" : "Option to use the OXFORD INSTRUMENTS ITC 503S temperature controller to log Temperature 3 (sample), might increase measurement time.","advanced_options" : "Shows further options, has not impact on measurement","filtering" : "Separate averaging of data returned from sourcemeter and voltmeter.","filter_count" : "Number of sampled datapoints per source value","filtering_delay_ms" : "Delay between samples","built_in_voltmeter_average" : "The built-in repeating average of the Voltmeter, might be faster than the self built one. Recommended instead of the Voltmeter digital filter.","built_in_voltmeter_filter" : "Build in filter of the Agilent 34420A","built_in_voltmeter_filter_type" : "Analog: Filter to remove the 50/60Hz noise, Digital: Averaging filter that can cause artifacts if speed does not match number of repeated measurement calls, WARNING: Not recommended to be used by manufacturer, use averaging function!","built_in_voltmeter_filter_speed" : "Slow: 10 last values are averaged, Medium: 50 last values, Slow: 100 last values.","sweep_direction_mesurement": "'up': Minimum -> Maximum, 'down': Maximum -> Minimum, 'both': Minimum -> Maximum -> Minimum","number_of_steps_measurement" : "Sends multiple steps between measurement source values","channel_mesurement" : "Channel that the sample is connected to","sweep_direction_magnet": "'up': Minimum -> Maximum, 'down': Maximum -> Minimum, 'both': Minimum -> Maximum -> Minimum, 'hysteresis': 0 -> Maximum -> Minimum -> 0","number_of_steps_magnet" : "Sends multiple steps between measurement source values","channel_magnet" : "Channel that the magnet is connected to","field_to_current_ratio_T_per_A" : "Magnet dependent factor converting a current supplied by the source meter into the calculated magnetic field","apply_voltage" : "Only possible for two probe measurement","measure_current": "Only possible for two probe measurement","nplc_sourcemeter" : "Number of Power Line Cycles for the Sourcemeter","nplc_voltmeter" : "Number of Power Line Cycles for the Voltmeter"}
    displays = inputs
    requested_devices = ["Sourcemeter: Keithley 2636A",
                         "(optional) Voltmeter: Agilent 34420A",
                         "(optional) Temperature Controller: OXFORD ITC 503S",
                         "(optional) Magnet Power Supply: OXFORD IPS 120-10"]
    default_devices = [{DESCRIPTOR:"GPIB0::10::INSTR", ADAPTER_TYPE:"GPIB"},
                       {DESCRIPTOR:"GPIB0::11::INSTR", ADAPTER_TYPE:"GPIB"},
                       {DESCRIPTOR:"GPIB0::24::INSTR", ADAPTER_TYPE:"GPIB"},
                       {DESCRIPTOR:"GPIB0::25::INSTR", ADAPTER_TYPE:"GPIB"}]
    provided_devices = []
    visa_path = ""
    
    ### Safety variables
    _safe_current_muA = 1.515E6
    _safe_voltage_mV = 202E3
    _safe_ramp_times_s_per_A = 10.0

    ### Metadata
    metadata_start_time = Metadata(name="Date and Time",default="Unknown Error")    # metadata defined in startup()
    parameter_comment = Parameter(name="Comment", default="")
    metadata_devices_used = Metadata(name="Devices used in the measurement", default="Unknown Error")

    ### 4probe control
    measure_voltmeter = BooleanParameter(name="Use Voltmeter", default=False)
    measure_sourcemeter = BooleanParameter(name="Measure with Sourcemeter", default=True)
    nplc_voltmeter = ListParameter(name="NPLC Voltmeter", choices=[0.02,0.2,1,2,10,20,100,200], default = 10, group_by={"measure_voltmeter":True})
    ### log temperatures
    measure_temperatures = BooleanParameter(name="Measure temperatures", default=False)
    ### use dedicated power-supply for the magnet
    use_magnet_power_supply = BooleanParameter(name="Use the power supply for the magnet", default=False)
    

    ### Built in filter for the Voltmeter (not recommended by manufacturer)
    built_in_voltmeter_filter = BooleanParameter(name="Voltmeter Filter", default=False, group_by={"measure_voltmeter":True,"advanced_options":True})
    built_in_voltmeter_filter_type = ListParameter(name="Voltmeter Filter Type", choices=["Analog","Digital","Both"], default="Digital", group_by={"measure_voltmeter":True,"advanced_options":True,"built_in_voltmeter_filter":True})
    built_in_voltmeter_filter_speed = ListParameter(name="Voltmeter Digital Filter Speed", choices=["Slow","Medium","Fast"], group_by={"measure_voltmeter":True,"advanced_options":True,"built_in_voltmeter_filter":True})

    ### Built in average function for the Voltmeter (recommended by manufacturer)
    built_in_voltmeter_average = BooleanParameter(name="Voltmeter Averaging", default=False,group_by={"measure_voltmeter":True,"advanced_options":True})
    built_in_voltmeter_average_count = IntegerParameter(name="Number of Voltmeter voltages to average", minimum=1, maximum=1024, default=10,group_by={"measure_voltmeter":True,"advanced_options":True,"built_in_voltmeter_average":True})


    ### Advanced options for 2-probe measurement
    advanced_options = BooleanParameter(name="Advanced Options", default=False)
    channel_mesurement = ListParameter(name="Sample channel", choices=["A", "B"], default="A", group_by={"advanced_options":True})
    sweep_direction_mesurement = ListParameter(name="Sweep direction for measurement",choices=["up","down","both"], default="up", group_by={"advanced_options":True})
    number_of_steps_measurement = IntegerParameter(name="Number of steps to next source value for measurement", minimum=1, default=1, group_by={"advanced_options":True})
    pause_per_step_measurement_ms = FloatParameter(name="Pause per step to next source value for measurement", units="ms", minimum=0, default=1, group_by={"advanced_options":True})
    
    ### Advanced options for filtering
    filtering = BooleanParameter(name="Apply Repeating Average Filter", default=False, group_by={"advanced_options":True})
    filter_count = IntegerParameter(name="Number of datapoints to average", minimum=1, default=10, group_by={"advanced_options":True, "filtering":True})
    filtering_delay_ms = FloatParameter(name="Delay between filtering repeats", units="ms", minimum=0, default=10, group_by={"advanced_options":True, "filtering":True})
    filter_voltmeter = BooleanParameter(name="Use Average for Voltmeter", default=True, group_by={"filtering":True,"measure_voltmeter":True})
    filter_sourcemeter = BooleanParameter(name="Use Average for Sourcemeter", default=True, group_by={"filtering":True,"measure_sourcemeter":True})

    ### Advanced options for magnet control
    channel_magnet = ListParameter(name="Magnet channel", choices=["A", "B"], default="B", group_by={"advanced_options":True, "use_magnet_power_supply":False})
    sweep_direction_magnet= ListParameter(name="Sweep direction for the magnetic field",choices=["up","down","both","hysteresis"], default="up", group_by={"advanced_options":True})
    number_of_steps_magnet = IntegerParameter(name="Number of steps to next magnetic field", minimum=1, default=20, group_by={"advanced_options":True,"use_magnet_power_supply":False})
    pause_per_step_magnet_ms = FloatParameter(name="Pause per step to next magnetic field", units="ms", minimum=1, default=50, group_by={"advanced_options":True,"use_magnet_power_supply":False})
    field_to_current_ratio_T_per_A = FloatParameter(name="Field to Current ratio", units="T/A", minimum=1E-13, default=0.1206, group_by={"advanced_options":True,"use_magnet_power_supply":False})
    
    ### Measurement inputs with limits for the Keithley 2600
    apply_current = BooleanParameter(name="Apply Current", default=True, group_by={"apply_voltage":False})
    apply_voltage = BooleanParameter(name="Apply Voltage", default=False, group_by={"apply_current":False, "measure_voltmeter":False})
    
    measure_current = BooleanParameter(name="Measure Current", default=False, group_by={"apply_current":False, "measure_voltage":False, "measure_voltmeter":False})
    measure_voltage = BooleanParameter(name="Measure Voltage", default=True, group_by={"apply_voltage":False, "measure_current":False})
    
    nplc_sourcemeter = FloatParameter(name="NPLC Sourcemeter", minimum=0.001, maximum=25, default = 10,group_by={"measure_sourcemeter":True})
    number_of_datapoints_measurement = IntegerParameter(name="Number of IV-Measurement Datapoints", minimum=1, default=100)
    ## Current measurement
    current_limit_muA = FloatParameter(name="Compliance Current", units="muA", minimum=0, maximum=_safe_current_muA, default = 1, group_by={"apply_voltage" : True, "measure_voltmeter":False})
    maximum_voltage_mV = FloatParameter(name="Maximal Voltage", units="mV", minimum=-_safe_voltage_mV, maximum=_safe_voltage_mV, default = 100, group_by={"apply_voltage" : True, "measure_voltmeter":False})
    minimum_voltage_mV = FloatParameter(name="Minimum Voltage", units="mV", minimum=-_safe_voltage_mV, maximum=_safe_voltage_mV, default = 0, group_by={"apply_voltage" : True, "measure_voltmeter":False})
    ## Voltage measurement
    voltage_limit_mV = FloatParameter(name="Compliance Voltage", units="mV", minimum=0, maximum=_safe_voltage_mV, default = 100, group_by={"apply_current" : True})
    maximum_current_muA = FloatParameter(name="Maximal Current", units="muA", minimum=-_safe_current_muA, maximum=_safe_current_muA, default = 1, group_by={"apply_current" : True})
    minimum_current_muA = FloatParameter(name="Minimum Current", units="muA", minimum=-_safe_current_muA, maximum=_safe_current_muA, default = 0, group_by={"apply_current" : True})
    
    ### Measurement inputs with limits for the Oxford Instruments IPS120-10
    voltage_limit_magnetic_field_V = FloatParameter(name="Compliance Voltage for the Magnet", units="V", minimum=0, maximum=_safe_voltage_mV*1E-3, default=10, group_by={"use_magnet_power_supply" : False})
    minimum_magnetic_field_mT = FloatParameter(name="Minimum magnetic field", units="mT", minimum=-14E3, maximum=14E3, default=0)
    maximum_magnetic_field_mT = FloatParameter(name="Maximum magnetic field", units="mT", minimum=-14E3, maximum=14E3, default=0)
    number_of_datapoints_magnet = IntegerParameter(name="Number of Magnetic Field Datapoints", minimum=1, default=1)
    
    ### Measurement data
    DATA_COLUMNS = ['Current / muA', 'Voltage Sourcemeter / mV', 'Voltage Voltmeter / mV', "Magnetic field / mT", "Temperature / K", "Resistance Sourcemeter / Ohm", "Resistance Voltmeter / Ohm", "Time / s", "Duration / s"]
        
    ### Internal
    #   Instruments
    keithley2600 : Keithley2600
    keithley2600_channel_measurement : Keithley2600_Channel
    keithley2600_channel_magnet : Keithley2600_Channel
    keithley2600_connected = False
    #
    agilent34420A : Instrument
    agilent34420A_connected = False
    agilent34420A_read_attempts = 5
    agilent34420A_failure_delay_s = 0.1
    #
    itc503 : ITC503
    itc503_connected = False
    itc503_delay_s = 0.05  
    _num_temperature_attempts = 6
    #
    ips12010 : IPS120_10
    ips12010_connected = False
    ips12010_delay_s = 0.05  
    _num_magnet_attempts = 5
    #
    _apply_voltage = False
    _apply_current = False
    _data_to_measure = []
    _magnetic_field_data_T = []
    _applied_current_on_magnet_A = None
    keithley2600_channel_measurement_filter_type = None
    keithley2600_channel_measurement_filter_count = None
    keithley2600_channel_measurement_filter_state = None
    _last_datapoint = 0
    _start_time = 0
    _first_measurement = False

    def _startup_sourcemeter(self, manager) -> None:
        info = self.provided_devices[0]
        descriptor = info[DESCRIPTOR]
        adapter_type = info[ADAPTER_TYPE]
        
        min_timeout_ms = self.nplc_sourcemeter/50*1E3
        timeout_ms = min_timeout_ms + 3000
        
        device = Device(descriptor=descriptor, manager=manager,adapter_type=adapter_type, VISAAdapter_args={"timeout":timeout_ms})
        device.clear()
        
        self.keithley2600_connected = device.successfully_connected
        self.keithley2600 = Keithley2600(adapter=device.adapter)
        self.metadata_devices_used = self.keithley2600.ask("*IDN?").strip()

        if self.keithley2600_connected:
            ### Initiate source meter
            self.keithley2600.reset()
            if self.channel_mesurement == "A" and self.channel_magnet == "B":
                self.keithley2600_channel_measurement = self.keithley2600.ChA
                self.keithley2600_channel_magnet = self.keithley2600.ChB
            elif self.channel_mesurement == "B" and self.channel_magnet == "A":
                self.keithley2600_channel_measurement = self.keithley2600.ChB
                self.keithley2600_channel_magnet = self.keithley2600.ChA
            else:
                log.error(f"BlueOxfordCryo_MagnetControl:Invalid channels '{self.channel_mesurement}' & '{self.channel_magnet}' provided: Must be different and 'A' or 'B', shutting down!")
                self.shutdown()
                return
            #   Catch potential connection difficulties by probing for errors (coming from experience)
            try:
                self.keithley2600.check_errors()
            except Exception as error:
                log.error(f"BlueOxfordCryo_MagnetControl:Sourcemeter could not check for errors, measurement might fail in the near future! Try resetting the instrument and restarting.")
                
            ### Define 2-probe measurement parameters
            current_limit = self.current_limit_muA*1E-6 # A
            max_voltage = self.maximum_voltage_mV*1E-3  # V
            min_voltage = self.minimum_voltage_mV*1E-3  # V
            
            voltage_limit = self.voltage_limit_mV*1E-3  # V
            max_current = self.maximum_current_muA*1E-6 # A
            min_current = self.minimum_current_muA*1E-6 # A
            
            #   Make data to measure
            minimum = 0
            maximum = 0
            if self.measure_current and not self.measure_voltmeter:
                if self.apply_voltage:
                    minimum = min_voltage
                    maximum = max_voltage
                    try:
                        self.keithley2600_channel_measurement.apply_voltage(compliance_current=current_limit)
                        if self.measure_sourcemeter:
                            self.keithley2600_channel_measurement.measure_current(nplc=self.nplc_sourcemeter, auto_range=True)
                    except Exception as error:
                        log.error(f"BlueOxfordCryo_MagnetControl:Error when setting Sourcemeter up for measuring current: '{error}'")
                    self._apply_voltage = True
                else:
                    log.error(f"BlueOxfordCryo_MagnetControl:Can not measure current and not apply voltage!")
                    self.shutdown()
                    return
            elif self.measure_voltage:
                if self.apply_current:
                    minimum = min_current
                    maximum = max_current
                    try:
                        self.keithley2600_channel_measurement.apply_current(compliance_voltage=voltage_limit)
                        if self.measure_sourcemeter:
                            self.keithley2600_channel_measurement.measure_voltage(nplc=self.nplc_sourcemeter, auto_range=True)
                    except Exception as error:
                        log.error(f"BlueOxfordCryo_MagnetControl:Error when setting Sourcemeter up for measuring voltage: '{error}'")
                    self._apply_current = True
                else:
                    log.error(f"BlueOxfordCryo_MagnetControl:Can not measure voltage and not apply current!")
                    self.shutdown()
                    return
            elif (self.measure_voltmeter and self.measure_current) or (self.measure_voltmeter and self.apply_voltage):
                log.error(f"BlueOxfordCryo_MagnetControl:Can not do a 4 probe measurement and measure current / apply voltage!")
                self.shutdown()
                return
            else:
                log.error(f"BlueOxfordCryo_MagnetControl:Incorrect Source / Sense functions, shutting down ...")
                self.shutdown()
                return
                
            if self.sweep_direction_mesurement == "up":
                self._data_to_measure = np.linspace(minimum, maximum, self.number_of_datapoints_measurement, dtype=float)
                log.info("BlueOxfordCryo_MagnetControl:Sweeping measurement up")
            elif self.sweep_direction_mesurement == "down":
                self._data_to_measure = np.linspace(maximum, minimum, self.number_of_datapoints_measurement, dtype=float)
                log.info("BlueOxfordCryo_MagnetControl:Sweeping measurement down")
            elif self.sweep_direction_mesurement == "both":
                up = np.linspace(minimum, maximum, int(self.number_of_datapoints_measurement/2), dtype=float)
                down = np.linspace(maximum, minimum, int(self.number_of_datapoints_measurement/2), dtype=float)
                self._data_to_measure = np.concatenate((up, down), axis=None)
                log.info("BlueOxfordCryo_MagnetControl:Sweeping measurement up and down")

            ### Define magnetic field control parameters
            try:
                self.keithley2600_channel_magnet.apply_current(compliance_voltage=self.voltage_limit_magnetic_field_V)
            except Exception as error:
                log.error(f"BlueOxfordCryo_MagnetControl:Error when setting Sourcemeter up for applying current: '{error}'")
            
            self.keithley2600_channel_measurement.source_output = 'OFF'
            self.keithley2600_channel_magnet.source_output = 'OFF'

    def _startup_voltmeter(self, manager) -> None:
        info = self.provided_devices[1]
        descriptor = info[DESCRIPTOR]
        adapter_type = info[ADAPTER_TYPE]

        if self.built_in_voltmeter_average:
            min_timeout_ms = (self.nplc_voltmeter*self.built_in_voltmeter_average_count)/50*1E3
        else:
            min_timeout_ms = self.nplc_voltmeter/50*1E3
        timeout_ms = min_timeout_ms + 3000
        
        device = Device(descriptor=descriptor, manager=manager, adapter_type=adapter_type, VISAAdapter_args={"timeout":timeout_ms})
        self.agilent34420A_clear = lambda : device.clear()
        
        self.agilent34420A_connected = device.successfully_connected
        self.agilent34420A = Instrument(device.adapter, name="Agilent 34420A Voltmeter")
        self.metadata_devices_used += " + " + self.agilent34420A.ask("*IDN?").strip()

        if self.agilent34420A_connected:
            ### Initiate voltmeter
            self.agilent34420A.clear()
            self.agilent34420A.reset()
            
            try:
                self.agilent34420A.check_errors()
            except Exception as error:
                if self.measure_voltmeter:
                    log.error(f"BlueOxfordCryo_MagnetControl:Volt Meter could not check for errors, measurement might fail in the near future! Try resetting the instruments and restarting.")
            
            self.agilent34420A.write(":sense:function \"voltage\"")
            self.agilent34420A.write(":sense:voltage:RANGe:AUTO ON")
            self.agilent34420A.write(":sense:voltage:NPLCycles "+str(self.nplc_voltmeter))
            
            #   Do build in filtering
            if self.built_in_voltmeter_filter:
                self.agilent34420A.write(":input:filter:state ON")
                
                if self.built_in_voltmeter_filter_type=="Analog":
                    self.agilent34420A.write(":input:filter:type analog")
                elif self.built_in_voltmeter_filter_type=="Digital":
                    self.agilent34420A.write(":input:filter:type digital")
                elif self.built_in_voltmeter_filter_type=="Both":
                    self.agilent34420A.write(":input:filter:type both")
                
                if self.built_in_voltmeter_filter_type != "Analog":
                    if self.built_in_voltmeter_filter_speed=="Slow":
                        self.agilent34420A.write(":input:filter:digital:response slow")
                    elif self.built_in_voltmeter_filter_speed=="Medium":
                        self.agilent34420A.write(":input:filter:digital:response medium")
                    elif self.built_in_voltmeter_filter_speed=="Fast":
                        self.agilent34420A.write(":input:filter:digital:response fast")
            else:
                self.agilent34420A.write(":input:filter:state OFF")
            
            #   Setup built-in averaging
            if self.built_in_voltmeter_average:
                self.agilent34420A.write(":calc:func average")
                self.agilent34420A.write(":calc:state ON")
                self.agilent34420A.write(f":sample:count {self.built_in_voltmeter_average_count}")
                self.agilent34420A.write(":TRIGGER:SOURCE IMM")
                self.agilent34420A.write("*ESE 1")
                self.agilent34420A.write("*OPC")

            self.agilent34420A.write(":output:state 0")
        else:
            log.error(f"BlueOxfordCryo_MagnetControl:4 probe was selected but voltmeter was not connected successfully, shutting down!")
            self.shutdown()
    
    def _startup_temperature_controller(self, manager) -> None:
            info = self.provided_devices[2]
            descriptor = info[DESCRIPTOR]
            adapter_type = info[ADAPTER_TYPE]
            device = Device(descriptor=descriptor, manager=manager, adapter_type=adapter_type, VISAAdapter_args={"send_end" : False, "query_delay" : 0.1, "read_termination" : '\r', "write_termination" : '\r', "chunk_size" : 512, "timeout":3000})
            self.Itc503_clear = lambda : device.clear() # this is a non SCPI capable device, hence clearing the buffer requires a GPIB clear signal and not *CLS which depends on the adapter used, hence the implementation in the Device class
            self.Itc503_clear()
            
            self.itc503_connected = device.successfully_connected
            self.itc503 = ITC503(device.adapter,clear_buffer=False)
            self.itc503.adapter.write("@0V")
            time.sleep(0.1)
            self.metadata_devices_used += " + " + self.itc503.adapter.read().strip()
            self.Itc503_clear()
            self.itc503.control_mode = "RU"
            self.Itc503_clear()
    
    def _startup_magnet_power_supply(self, manager) -> None:
            info = self.provided_devices[3]
            descriptor = info[DESCRIPTOR]
            adapter_type = info[ADAPTER_TYPE]
            device = Device(descriptor=descriptor, manager=manager, adapter_type=adapter_type, VISAAdapter_args={"send_end" : True, "read_termination" : '\r', "write_termination" : '\r', "chunk_size" : 512,"timeout":5000})
            self.ips12010_clear = lambda : device.clear() # this is a non SCPI capable device, hence clearing the buffer requires a GPIB clear signal and not *CLS which depends on the adapter used, hence the implementation in the Device class
            self.ips12010_clear()
            
            self.ips12010_connected = device.successfully_connected
            self.ips12010 = IPS120_10(device.adapter,clear_buffer=False, field_range=(-14,14))
            self.ips12010_clear()
            self.ips12010.adapter.write("@0V")
            time.sleep(0.1)
            self.metadata_devices_used += " + " + self.ips12010.adapter.read().strip()
            self.ips12010_clear()
            self.ips12010.control_mode = "RU"   #   remote operation
            #   self.ips12010.write("Q4")           #   extended range (no implemetation?)
            self.ips12010_clear()
            self.ips12010.activity = "hold"     #   set sweep mode to hold
            self.ips12010_clear()
            self.ips12010.switch_heater_enabled = True
            self.ips12010_clear()
            self.ips12010.sweep_rate = 0.9648   #   set sweep rate to 8 A/min, i.e. 0.9648  T/min
            self.ips12010_clear()
            self.ips12010.enable_control()
            self.ips12010_clear()

    def startup(self):
        ### Generate Metadata
        self.metadata_start_time = datetime.datetime.now().strftime("%d.%m.%Y, %H:%M:%S")
        
        log.info("BlueOxfordCryo_MagnetControl started ...")

        if len(self.provided_devices) != len(self.requested_devices) and len(self.provided_devices):
            log.error(f"BlueOxfordCryo_MagnetControl:Requested {len(self.requested_devices)} devices: {self.requested_devices} but got {len(self.provided_devices)} devices: {self.provided_devices}, does not match, aborting!")
            self.shutdown()
            return
        elif len(self.provided_devices) > 1:
            manager = make_resourcemanager(custom_visalib_path=self.visa_path)
            
            #   Sourcemeter
            self._startup_sourcemeter(manager)

            #   Voltmeter (optional)
            if self.measure_voltmeter:
                self._startup_voltmeter(manager)
                log.info("BlueOxfordCryo_MagnetControl:Measuring 4 probe.")
            else:
                log.info("BlueOxfordCryo_MagnetControl:Measuring 2 probe.")
            
            #   Temperature Controller (optional)
            if self.measure_temperatures:
                self._startup_temperature_controller(manager)
                log.info("BlueOxfordCryo_MagnetControl:Measuring temperatures.")
            #   Magnet Power Supply (optional)
            if self.use_magnet_power_supply:
                self._startup_magnet_power_supply(manager)
                log.info("BlueOxfordCryo_MagnetControl:Using the dedecated magnet power supply instead of the Sourcemeter")
        else:
            log.error(f"BlueOxfordCryo_MagnetControl:No devices provided, shutting down!")
            self.shutdown()
            return
        
        ### Define magnet
        minimum_field_T = self.minimum_magnetic_field_mT*1E-3
        maximum_field_T = self.maximum_magnetic_field_mT*1E-3
        
        if self.sweep_direction_magnet == "up":
            self._magnetic_field_data_T = np.linspace(minimum_field_T, maximum_field_T, self.number_of_datapoints_magnet, dtype=float)
            log.info("BlueOxfordCryo_MagnetControl:Sweeping magnetic field up")
        elif self.sweep_direction_magnet == "down":
            self._magnetic_field_data_T = np.linspace(maximum_field_T, minimum_field_T, self.number_of_datapoints_magnet, dtype=float)
            log.info("BlueOxfordCryo_MagnetControl:Sweeping magnetic field down")
        elif self.sweep_direction_magnet == "both":
            up = np.linspace(minimum_field_T, maximum_field_T, int(self.number_of_datapoints_magnet/2), dtype=float)
            down = np.linspace(maximum_field_T, minimum_field_T, int(self.number_of_datapoints_magnet/2), dtype=float)
            self._magnetic_field_data_T = np.concatenate((up, down), axis=None)
            log.info("BlueOxfordCryo_MagnetControl:Sweeping magnetic field up and down")
        elif self.sweep_direction_magnet == "hysteresis":
            up1 = np.linspace(0, maximum_field_T, int(self.number_of_datapoints_magnet/4), dtype=float)
            down = np.linspace(maximum_field_T, minimum_field_T, int(self.number_of_datapoints_magnet/2), dtype=float)
            up2 = np.linspace(minimum_field_T, 0, int(self.number_of_datapoints_magnet/4), dtype=float)
            self._magnetic_field_data_T = np.concatenate((np.concatenate((up1, down), axis=None), up2), axis=None)
            log.info("BlueOxfordCryo_MagnetControl:Sweeping magnetic field hysteretic from 0 to maximum to minimum to 0")
        if np.sum(np.abs(self._magnetic_field_data_T)) > 0 and not self.use_magnet_power_supply:
            log.warning("BlueOxfordCryo_MagnetControl: ENSURE THAT THE SWITCH HEATER IS ENABLED and the current leeds of the magnet power supply are shorted! Otherwise no magnetic field will be applied even at finite source current.")
            
        #   logging
        if self.filtering:
            log.info(f"BlueOxfordCryo_MagnetControl:Using filtering with {self.filter_count} repeating datapoints under {self.filtering_delay_ms}ms delay.")
        
        if not self.measure_voltmeter and not self.measure_sourcemeter:
            log.warning("BlueOxfordCryo_MagnetControl:Sourcemeter and Voltmeter are disabled, measuring no Voltage / Current!")
        return
    
    def _ramp_sourcemeter_measurement(self, target:float, number_steps:int|None=None, pause_ms:float|None=None) -> float:
        """A function that emulates the `.ramp_to_...()` from the `Keithley 2600 Channel` class due to a bug where the applied current/voltage was always a multiple of muA / mV.\n
        The target must match the `self._apply_...`.

        Args:
            target (float): Target Voltage / Current in Ampere / Volt.
            number_steps (int | None): Number of steps to target. Defaults to self.number_of_steps_measurement when None.
            pause_ms (float | None): Time to remain on one step in milliseconds. Defaults to self.pause_per_step_measurement_ms when None.

        Returns:
            float: Applied Voltage / Current in Ampere / Volt depending if `self._apply_voltage` or `self._apply_current`.
        """
        if number_steps is None:
            number_steps = self.number_of_steps_measurement
        if pause_ms is None:
            pause_ms = self.pause_per_step_measurement_ms
        
        points = np.linspace(self._last_datapoint, target, int(number_steps))
        self._last_datapoint = target
        return_val = None
        for point in points:
            if self._apply_voltage:
                self.keithley2600_channel_measurement.write(f"source.levelv = {point}")
            elif self._apply_current:
                self.keithley2600_channel_measurement.write(f"source.leveli = {point}")
            time.sleep(pause_ms*1E-3)
        
        if self._apply_voltage:
            return_val = self.keithley2600_channel_measurement.voltage
        elif self._apply_current:
            return_val = self.keithley2600_channel_measurement.current
        return return_val
 
    def get_temperature_K(self) -> float|None:
        """Use a temperature controller to measure temperatures. The ITC 503 does not always respond with valid temperatures, hence multiple attempts are necessary.

        Returns:
            tuple[float|None]: T3 returned by the ITC 503S
        """
        _temperature_3 = None
        if self.measure_temperatures:
            try:
                __temperature_3 = 0
                num_tries = 0
                valid = False
                answer = "no answer"
                while not valid and num_tries < self._num_temperature_attempts and not self.should_stop():
                    self.Itc503_clear()
                    time.sleep(self.itc503_delay_s)
                    try:
                        answer = str(self.itc503.temperature_3)
                        if not "-" in answer:   #   Sometimes the separator '-' is returned instead of the full temperature, disregard those readings and request a new one as some digits are probably missing
                            __temperature_3 = float(answer)
                            if __temperature_3 > 0 and len(list(answer)) > 4:
                                _temperature_3 = __temperature_3
                                valid = True
                    except Exception as error:
                        log.warning(f"Failed to find temperature on attempt {num_tries+1}, got '{answer}'K: {error}")
                    num_tries += 1
                
            except Exception as error:
                log.warning(f"Measuring temperature has failed: '{error}'")
                pass
        return _temperature_3
    
    def get_voltage_voltmeter(self) -> float|None:
        """Depending on the averaging and filtering the voltage readout has to be done in different ways.

        Returns:
            float|None: Voltage in Volts. Could be averaged and/or filtered using internal functions of the Agilent 34420A.
        """
        _voltage = None
        
        _read_attempts = 0
        while _read_attempts < self.agilent34420A_read_attempts:
            self.agilent34420A.clear()
            if self.should_stop():
                break
            try:
                if self.built_in_voltmeter_average:
                    #   From the docs of the voltmeter
                    #   bit 5 of the register (standard register) has to be enabled ==> voltmeter has aquired all datapoints for an average to be taken (i.e. for a trigger to be ... triggered)
                    self.agilent34420A.write("INIT")
                    standard_event = 0
                    while not standard_event == 1 and not self.agilent34420A.complete:
                        register = "{0:b}".format(int(self.agilent34420A.status))
                        if len(register) > 5:
                            standard_event = int(register[-6])      #   5th bit in the register = standard register
                    self.agilent34420A.clear()                      #   clear register
                    _voltage = float(self.agilent34420A.ask(":calc:aver:aver?"))
                    self.agilent34420A.write(":calc:func average")  #   reset averaging
                    self.agilent34420A.write("*OPC")                #   signal operation completed
                else:
                    _voltage = float(self.agilent34420A.ask(":read?"))
                break
            except Exception as error:
                
                try:
                    dev_errors = self.agilent34420A.check_errors()
                except:
                    dev_errors = "unknown"
                log.error(f"Measuring voltmeter voltage on attempt {_read_attempts+1}/{self.agilent34420A_read_attempts} has failed: '{error}': Device reported errors: {dev_errors}")
                self.agilent34420A.clear()
                try:
                    self.agilent34420A.id
                except:
                    pass
                time.sleep(self.agilent34420A_failure_delay_s)
            _read_attempts += 1
        return _voltage
    
    def _averaging(self) -> None:
        """Self built averaging.

        Returns
        --------
            current : float|None
                Current of the sourcemeter if `self.measure_current = True` and `self.filter_sourcemeter = True` else None.
            voltage_sourcemeter : float|None
                Voltage of the sourcemeter if `self.measure_current = True` and `self.filter_sourcemeter = True` else None.
            voltage_voltmeter : float|None
                Current of the voltmeter if `self.filter_voltmeter = True` else None.
        """
        current, voltage_sourcemeter, voltage_voltmeter = (None,None,None)
        voltmeter_key = "Voltmeter"
        sourcemeter_key = "Sourcemeter"
        filter_values = {}
        if self.filter_voltmeter and self.measure_voltmeter:
            filter_values[voltmeter_key] = np.zeros(shape=self.filter_count)
        if self.filter_sourcemeter and self.measure_sourcemeter:
            filter_values[sourcemeter_key] = np.zeros(shape=self.filter_count)

        for idx in range(0,self.filter_count):
            if self.should_stop():
                break
            if voltmeter_key in filter_values.keys():
                filter_values[voltmeter_key][idx] = self.get_voltage_voltmeter()
            if sourcemeter_key in filter_values.keys():
                if self.measure_current:
                    filter_values[sourcemeter_key][idx] = self.keithley2600_channel_measurement.current
                if self.measure_voltage:
                    filter_values[sourcemeter_key][idx] = self.keithley2600_channel_measurement.voltage
            time.sleep(self.filtering_delay_ms*1E-3)

        if not self.should_stop():
            if voltmeter_key in filter_values.keys():
                voltage_voltmeter = np.mean(filter_values[voltmeter_key])
            if sourcemeter_key in filter_values.keys():
                if self.measure_current:
                    current = np.mean(filter_values[sourcemeter_key])
                if self.measure_voltage:
                    voltage_sourcemeter = np.mean(filter_values[sourcemeter_key])

        return current, voltage_sourcemeter, voltage_voltmeter
    
    def _slow_ramp_to(self, target:float) -> None:
        """Slowly ramps the Sourcemeter measurement channel to a specific target.

        Args:
            target (float): The target current / voltage in Ampere / Volts.
        """
        slow_ramp_number_of_steps = 1
        if target != 0:
            if self._apply_current:
                slow_ramp_number_of_steps = int(round(abs(target*1E6))*2)   # 2 step per muA / mV
                log.info(f"Detected a non zero first source value {target*1E6}muA ...")
            if self._apply_voltage:
                slow_ramp_number_of_steps = int(round(abs(target*1E3))*2)   # 2 step per muA / mV
                log.info(f"Detected a non zero first source value {target*1E3}mV ...")

        elif self._apply_current and abs(self._last_datapoint-target)*1E6 > 1:
            slow_ramp_number_of_steps = int(round(abs(self._last_datapoint-target)*1E6)*2)   # 2 step per muA / mV
            log.info(f"Detected a sudden change of source input from {self._last_datapoint*1E6}muA to {target*1E6}muA ...")
        elif self._apply_voltage and abs(self._last_datapoint-target)*1E3 > 1:
                slow_ramp_number_of_steps = int(round(abs(self._last_datapoint-target)*1E3)*2)   # 2 step per muA / mV
                log.info(f"Detected a sudden change of source input from {self._last_datapoint*1E3}mV to {target*1E3}mV ...")

        if slow_ramp_number_of_steps < 1:
            slow_ramp_number_of_steps = 1
        slow_ramp_pause_per_step_ms = 20
        log.info(f"Slowly ramping to source value in {slow_ramp_number_of_steps} steps with {slow_ramp_pause_per_step_ms}ms per step, i.e. in {round(slow_ramp_number_of_steps*slow_ramp_pause_per_step_ms*1E-3,1)}s ...")
        self._ramp_sourcemeter_measurement(target=target, number_steps=slow_ramp_number_of_steps, pause_ms=slow_ramp_pause_per_step_ms)
        time.sleep(0.1)
    
    def _Measurement_Sweep(self, magnetic_field_T:float, magnetic_index:int) -> None:
        """Do a 2 probe measurement at a specific magnetic field.

        Args:
            magnetic_field_T (float): Applied magnetic field in Tesla.
            magnetic_index (int): Index of the magnetic field in the list of currents applied to the magnet.
        """
        
        log.info(f"Measuring at {magnetic_field_T*1E3}mT.")

        ### Ensure that sample and source meter are in a stable state at all times
        if (magnetic_index == 0 and self._data_to_measure[0] != 0):
            self._slow_ramp_to(self._data_to_measure[0])
        ###
        
        #   Log time of first measurement
        if self._first_measurement is False:
            self._first_measurement = True
            self._start_time = time.time()
            
        data_point = self._data_to_measure[0]
        for data_index in range(0,len(self._data_to_measure)):
            if self.should_stop():
                log.info("Caught the stop flag in the procedure")
                break
            current,voltage,resistance,voltage_voltmeter,resistance_4probe = (None,None,None,None,None)
            data_point = self._data_to_measure[data_index]

            progress = (magnetic_index*self.number_of_datapoints_measurement + data_index)/(self.number_of_datapoints_measurement*self.number_of_datapoints_magnet)*100
            if self._apply_voltage:
                voltage = self._ramp_sourcemeter_measurement(target=data_point)
            elif self._apply_current:
                current = self._ramp_sourcemeter_measurement(target=data_point)
                    
            try:
                start_time = time.time()
                ### Do averaging
                if self.filtering:
                    if self.measure_voltage:
                        _, voltage, voltage_voltmeter = self._averaging()
                    if self.measure_current:
                        current, _, voltage_voltmeter = self._averaging()

                if self.measure_voltmeter and voltage_voltmeter is None:
                    voltage_voltmeter = self.get_voltage_voltmeter()
                if self.measure_current and self.measure_sourcemeter and current is None:
                    current = self.keithley2600_channel_measurement.current
                if self.measure_voltage and self.measure_sourcemeter and voltage is None:
                    voltage = self.keithley2600_channel_measurement.voltage
                temperature = self.get_temperature_K()
                end_time    = time.time()
                
                voltage     = float(voltage)*1E3            if voltage is not None else None
                current     = float(current)*1E6            if current is not None else None
                resistance  = float(voltage/current)*1E3    if current != 0 and current is not None and voltage is not None else None
                voltage_voltmeter = float(voltage_voltmeter)*1E3 if voltage_voltmeter is not None else None
                resistance_4probe = float(voltage_voltmeter/current)*1E3    if current != 0 and current is not None and voltage_voltmeter is not None else None

                time_started = start_time - self._start_time
                time_finished = end_time - self._start_time

                return_data = {
                    'Voltage Sourcemeter / mV' : voltage if voltage is not None else "",
                    'Voltage Voltmeter / mV'    : voltage_voltmeter if voltage_voltmeter is not None else "",
                    "Current / muA"             : current if current is not None else "",
                    "Magnetic field / mT"       : magnetic_field_T*1E3 if magnetic_field_T is not None else "",
                    "Resistance Sourcemeter / Ohm" : resistance if resistance is not None else "",
                    "Resistance Voltmeter / Ohm"   : resistance_4probe if resistance_4probe is not None else "", 
                    "Time / s"                  : time_started if time_started is not None else "", 
                    "Duration / s"              : time_finished-time_started,
                    "Temperature / K"           : temperature if temperature is not None else "",
                }
                self.emit('results', return_data)
            except Exception as error:
                log.error(f"BlueOxfordCryo_MagnetControl:Invalid data received from device, failed to find values due to an exception: {error}")
                self.keithley2600.clear()
                if self.measure_voltmeter:
                    self.agilent34420A.clear()
            self.emit('progress', progress)
        
        ### Ensure that sample and source meter are in a stable state at all times
        if len(self._magnetic_field_data_T) > 1 and len(self._data_to_measure)>1:
            self._slow_ramp_to(self._data_to_measure[0])    #   go to next initial source value before waiting for the magnet as not to bias the sample for an unnecessary amount of time
        ###

    def _ramp_sourcemeter_magnet(self, target_current_A:float, number_of_steps:int|None=None, pause_ms:float|None=None) -> float|None:
        """Ramps the applied current to the magnet safely.\n
        To ensure that the magnet is never sweeped to quickly (inductance of magnet could damage source meter) the number of steps to the next current value applied on the magnet must be checked.\n
        If the time from one current to the next current is faster than `self._safe_ramp_times_s_per_A` (in seconds/Ampere) the number of steps is modified. Otherwise the default one is used.

        Args:
            target_current_A (float): Current that is to be applied on the magnet in Ampere.
        
        Returns:
            magnetic_field_T (float|None): The applied magnetic field in tesla or None if an error occures.
        """
        if abs(target_current_A) > self._safe_current_muA*1E-6:
            log.error(f"Tried to apply an invalid current of '{round(target_current_A,2)}'A to the Sourcemeter magnet channel, when the maximum is set to '{round(self._safe_current_muA*1E-6,2)}'A, ignoring datapoint!")
        else:
            if self._applied_current_on_magnet_A is None:
                self._applied_current_on_magnet_A = self._magnetic_field_data_T[0]/self.field_to_current_ratio_T_per_A
            
            if number_of_steps is None:
                number_of_steps = self.number_of_steps_magnet
            if pause_ms is None:
                pause_ms = self.pause_per_step_magnet_ms

            sweep_range_A = abs(target_current_A-self._applied_current_on_magnet_A)
            current_ramp_time_s_per_A = number_of_steps*pause_ms*1E-3/sweep_range_A if sweep_range_A > 0 else self._safe_ramp_times_s_per_A
            if abs(current_ramp_time_s_per_A) < abs(self._safe_ramp_times_s_per_A):
                
                safe_number_of_steps = int(( self._safe_ramp_times_s_per_A/(pause_ms*1E-3) ) * sweep_range_A)+1
                
                log.info(f"Unsafe current sweep detected: You are trying to sweep from {round(self._applied_current_on_magnet_A,2)}A to {round(target_current_A,2)}A in {round(current_ramp_time_s_per_A,2)}s/A but safe time is set as {self._safe_ramp_times_s_per_A}s/A -> attempting to sweep in {self._safe_ramp_times_s_per_A}s/A with {safe_number_of_steps} number of steps!")
                
                number_of_steps = safe_number_of_steps
            
            self._applied_current_on_magnet_A = target_current_A

            ramp_currents = np.linspace(self.keithley2600_channel_magnet.current,target_current_A,number_of_steps)
            for current_val in ramp_currents:
                self.keithley2600_channel_magnet.write(f"source.leveli = {current_val}")
                time.sleep(pause_ms*1E-3)
        
        magnetic_field_T = None
        try:
            magnetic_field_T = self.field_to_current_ratio_T_per_A*self.keithley2600_channel_magnet.current
        except:
            pass
        return magnetic_field_T
    
    def _ramp_magnet_powersupply(self,target_field_T:float) -> float|None:
        """Uses the build in fuctions of the IPS120-10 to ramp the magnet to a magnetic field.

        Args:
            target_field_T (float): Field that is to be applied on the magnet in Tesla.
        
        Returns:
            magnetic_field_T (float|None): The applied magnetic field in tesla or None if an error occures.
        """
        self.ips12010_clear()
        magnetic_field_T = None
        self.ips12010.set_field(target_field_T, persistent_mode_control=False)
        
        num_attempts = 0
        valid = False
        while not valid and num_attempts < self._num_magnet_attempts and not self.should_stop():
            self.ips12010_clear()
            answer = self.ips12010.field
            try:
                magnetic_field_T = float(answer)
                valid = True
            except:
                log.warning(f"Failed to find magnetic field on attempt {num_attempts+1}, got '{answer}'T")
            num_attempts += 1
        return magnetic_field_T

    def execute(self):
        if self.keithley2600_connected:
            log.info("BlueOxfordCryo_MagnetControl:Measurement started ...")
            
            self.keithley2600_channel_measurement.source_output = 'ON'
            self.keithley2600_channel_magnet.source_output = 'ON'
            
            if self.measure_voltmeter:
                self.agilent34420A.write(":output:state 1")
            
            if not self.use_magnet_power_supply:    # slowly ramp to the first value of the magnetic field if it is not 0
                if abs(self._magnetic_field_data_T[0]) > 0:
                    start_current_A = self._magnetic_field_data_T[0]/self.field_to_current_ratio_T_per_A
                    num_steps = int(abs(self._magnetic_field_data_T[0]*1E3))
                    pause_ms = 25
                    log.info(f"Detected a non zero first magnetic field {self._magnetic_field_data_T[0]*1E3}mT, sweeping slowly in {num_steps} steps and {round(num_steps*pause_ms*1E-3,1)}s ...")
                    self._ramp_sourcemeter_magnet(target_current_A=start_current_A, number_of_steps=num_steps, pause_ms=pause_ms)

            if (self._apply_current or self._apply_voltage) and (self._apply_current != self._apply_voltage):
                for magnetic_index in range(0,len(self._magnetic_field_data_T)):
                    if self.should_stop():
                        log.info("Caught the stop flag in the procedure")
                        break
                    if self.use_magnet_power_supply:
                        magnetic_field_T = self._ramp_magnet_powersupply(target_field_T=self._magnetic_field_data_T[magnetic_index])
                    else:
                        current_for_magnetic_field_A = self._magnetic_field_data_T[magnetic_index]/self.field_to_current_ratio_T_per_A
                        magnetic_field_T = self._ramp_sourcemeter_magnet(target_current_A=current_for_magnetic_field_A)
                    self._Measurement_Sweep(magnetic_field_T = magnetic_field_T, magnetic_index=magnetic_index)
            else:
                log.error(f"BlueOxfordCryo_MagnetControl:Invalid source selected, shutting down!")
                self.shutdown()
                return
            return
        else:
            self.shutdown()
            return

    def shutdown(self):
        try:
            if self.keithley2600_connected:
                self._slow_ramp_to(target=0.)
                if not self.use_magnet_power_supply:
                    self._ramp_sourcemeter_magnet(target_current_A=0.)
                # self.keithley2600.ChA.shutdown()
                # self.keithley2600.ChB.shutdown()
                self.keithley2600.ChA.source_output = "OFF"
                self.keithley2600.ChB.source_output = "OFF"
                self.keithley2600.shutdown()
                self.keithley2600.adapter.close()
            else:
                log.error("BlueOxfordCryo_MagnetControl:Unable to shutdown Sourcemeter.")
        except:
            log.error("BlueOxfordCryo_MagnetControl:Unable to shutdown Sourcemeter.")
        if self.measure_voltmeter:
            try:
                if self.agilent34420A_connected:
                    self.agilent34420A.write(":output:state 0")
                    self.agilent34420A.reset()
                    self.agilent34420A.shutdown()
                    self.agilent34420A.adapter.close()
                else:
                    log.error("BlueOxfordCryo_MagnetControl:Unable to shutdown Voltmeter.")
            except:
                log.error("BlueOxfordCryo_MagnetControl:Unable to shutdown Voltmeter.")
        if self.measure_temperatures:
            try:
                if self.itc503_connected:
                    self.Itc503_clear()
                    self.itc503.control_mode = "LU"
                    self.itc503.shutdown()
                    self.itc503.adapter.close()
                else:
                    log.error("BlueOxfordCryo_MagnetControl:Unable to shutdown Temperature Controller.")
            except Exception as error:
                log.error(f"BlueOxfordCryo_MagnetControl:Unable to shutdown Temperature Controller: {error}")
        if self.use_magnet_power_supply:
            try:
                if self.ips12010_connected:
                    self.ips12010_clear()
                    self.ips12010.set_field(0)
                    self.ips12010.disable_control()
                    self.ips12010_clear()
                    self.ips12010.shutdown()
                    self.ips12010.adapter.close()
                else:
                    log.error("BlueOxfordCryo_MagnetControl:Unable to shutdown Magnet Power Supply.")
            except Exception as error:
                log.error(f"BlueOxfordCryo_MagnetControl:Unable to shutdown Temperature Controller: {error}")
        super().shutdown()
    
    def get_estimates(self, sequence_length=None, sequence=None):
        time_nplc_sm = 0
        time_nplc_vm = 0
        if self.measure_sourcemeter:
            time_nplc_sm = self.nplc_sourcemeter/50 if self.measure_sourcemeter else 0
        if self.measure_voltmeter:
            time_nplc_vm = self.built_in_voltmeter_average_count*self.nplc_voltmeter/50 if self.built_in_voltmeter_average else self.nplc_voltmeter/50
        time_nplc = time_nplc_sm + time_nplc_vm

        filter_time = 0
        if self.filtering:
            filter_time = self.filter_count*(self.filtering_delay_ms*1E-3 + time_nplc)
        temperature_time = 0
        if self.measure_temperatures:
            temperature_time = self.itc503_delay_s
        

        time_to_datapoint = self.number_of_steps_measurement*(self.pause_per_step_measurement_ms*1E-3 + time_nplc)
        time_spent_on_datapoint = time_nplc if not self.filtering else filter_time
        time_spent_on_datapoint += temperature_time
        sweep_time = self.number_of_datapoints_measurement*( time_to_datapoint + time_spent_on_datapoint )

        time_per_magnetic_field = self.number_of_steps_magnet*self.pause_per_step_magnet_ms*1E-3

        total_time = self.number_of_datapoints_magnet*(time_per_magnetic_field+sweep_time)

        finished_at = datetime.datetime.now() + datetime.timedelta(seconds=total_time)

        estimates = [
            ("Min. duration", "%d min" % round(total_time/60)),
            ("Min. time per sweep", "%d s" % int(sweep_time)),
            ("Min. time per datapoint", "%d ms" % int((time_to_datapoint+time_spent_on_datapoint)*1E3)),
            ("Min. time spent averaging", "%d ms" % int(filter_time*1E3)),
            ("Number of sweeps", "%d" % int(self.number_of_datapoints_magnet)),
            ("Sequence length", str(sequence_length)),
            ('Selected finished at', finished_at.strftime("%H:%M")),
        ]
        return estimates


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = WindowSingleDock(BlueOxfordCryo_MagnetControl)
    window.show()
    sys.exit(app.exec())