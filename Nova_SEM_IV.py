#   Nova SEM, 2-/4-probe
#   2026

import sys, datetime, logging, time
import numpy as np

from pymeasure.display.Qt import QtWidgets
from pymeasure.experiment import IntegerParameter, FloatParameter, Parameter, ListParameter, BooleanParameter, Metadata
from pymeasure.instruments import Instrument
from pymeasure.instruments.keithley.keithley2400 import Keithley2400

### Own files
from src import WindowSingleDock, DESCRIPTOR, ADAPTER_TYPE, DeviceProcedure, Device, make_resourcemanager

class NovaSEM_IV(DeviceProcedure):
    """This procedure controls the Keithley 2400 Sourcemeter. 2- and 4-probe measurement are possible, with the 4-probe needing an optional voltmeter (procedure is tested with the Agilent 34420A but any SCPI '*read' capable voltmeter should work) and 'Use Voltmeter' set as True.\n

    Current / muA
        The current applied / measured on the channel connected to the sample. All values are directly supplied by the Sourcemeter.
    Voltage Sourcemeter / mV
        The voltage applied / measured on the channel connected to the sample. All values are directly supplied by the Sourcemeter.
    Voltage Voltmeter / mV
        (optional, None if no voltmeter used). The voltage measured by the voltmeter.
    Resistance Sourcemeter / Ohm
        Values calculated from 'Current / muA' and 'Voltage Sourcemeter / mV' or measured with 'Measure Resistance'=True.
    Resistance Voltmeter / Ohm
        Values calculated from 'Current / muA' and 'Voltage Voltmeter / mV'.
    """
    name = "Nova SEM current-voltage control"
    inputs = ["measure_voltmeter","advanced_options","filtering","filter_count","filtering_delay_ms","sweep_direction", "number_of_steps","pause_per_step_ms","terminal","apply_current","apply_voltage","measure_current","measure_voltage","measure_resistance","voltage_limit_mV", "maximum_current_muA", "minimum_current_muA","current_limit_muA","maximum_voltage_mV","minimum_voltage_mV","nplc_sourcemeter","nplc_voltmeter", "number_of_datapoints"]
    tool_tip_information = {"measure_voltmeter" : "Option to use a voltmeter to measure the voltage. Sourcemeter will then only supply current","advanced_options" : "Shows further options, has not impact on measurement","filter_count" : "Number of sampled datapoints per source value","filtering_delay_ms" : "Delay between samples","sweep_direction": "'up': Minimum -> Maximum, 'down': Maximum -> Minimum, 'both': Minimum -> Maximum -> Minimum","number_of_steps" : "Sends multiple steps between measurement source values","nplc_sourcemeter" : "Number of Power Line Cycles for the Sourcemeter","nplc_voltmeter" : "Number of Power Line Cycles for the Voltmeter"}
    displays = inputs
    requested_devices = ["Sourcemeter: Keithley 2400", 
                         "(optional) Voltmeter: Agilent 34420A"]
    default_devices = [{DESCRIPTOR:"GPIB0::10::INSTR", ADAPTER_TYPE:"GPIB"}, 
                       {DESCRIPTOR:"GPIB0::11::INSTR", ADAPTER_TYPE:"GPIB"}]
    provided_devices = []
    visa_path = ""

    ### Metadata
    metadata_start_time = Metadata(name="Date and Time",default="Unknown Error")    # metadata defined in startup()


    ### Four probe
    measure_voltmeter = BooleanParameter(name="Use Voltmeter", default=False)
    nplc_voltmeter = FloatParameter(name="NPLC Voltmeter", minimum=0.02, maximum=200, default = 1, group_by={"measure_voltmeter":True})

    ### Keithley 2400 specific options
    advanced_options = BooleanParameter(name="Advanced Options", default=False)
    terminal = ListParameter(name="Terminal to use", choices=["Front", "Rear"], default="Front", group_by={"advanced_options":True})
    sweep_direction = ListParameter(name="Sweep direction",choices=["up","down","both"], default="up", group_by={"advanced_options":True})
    number_of_steps = IntegerParameter(name="Number of steps to next source value", minimum=1, default=1, group_by={"advanced_options":True})
    pause_per_step_ms = FloatParameter(name="Pause per step to next source value", units="ms", minimum=1, default=1, group_by={"advanced_options":True})

    ### Advanced options for filtering
    filtering = BooleanParameter(name="Apply Repeating Average Filter", default=False, group_by={"advanced_options":True})
    filter_count = IntegerParameter(name="Number of datapoints to average", minimum=1, default=10, group_by={"advanced_options":True, "filtering":True})
    filtering_delay_ms = FloatParameter(name="Delay between filtering repeats", units="ms", minimum=0, default=1, group_by={"advanced_options":True, "filtering":True})
    
    ### Measurement inputs with limits for the Keithley 2400
    nplc_sourcemeter = FloatParameter(name="NPLC Sourcemeter", minimum=0.01, maximum=10, default = 1)
    number_of_datapoints = IntegerParameter(name="Number of Datapoints", minimum=1, default=100)

    ### Measurement inputs with limits for the Keithley 2400
    apply_current = BooleanParameter(name="Apply Current", default=True, group_by={"apply_voltage":False,"measure_voltmeter":False})
    apply_voltage = BooleanParameter(name="Apply Voltage", default=False, group_by={"apply_current":False,"measure_voltmeter":False})
    
    measure_current = BooleanParameter(name="Measure Current", default=False, group_by={"apply_current":False, "measure_voltage":False, "measure_resistance":False,"measure_voltmeter":False})
    measure_voltage = BooleanParameter(name="Measure Voltage", default=True, group_by={"apply_voltage":False, "measure_current":False, "measure_resistance":False})
    measure_resistance = BooleanParameter(name="Measure Resistance", default=False, group_by={"measure_current":False, "measure_voltage":False})

     ## Current measurement
    current_limit_muA = FloatParameter(name="Compliance Current", units="muA", minimum=-1.05E6, maximum=1.05E6, default=1, group_by={"apply_voltage" : True})
    maximum_voltage_mV = FloatParameter(name="Maximal Voltage", units="mV", minimum=-210E3, maximum=210E3, default=100, group_by={"apply_voltage" : True})
    minimum_voltage_mV = FloatParameter(name="Minimum Voltage", units="mV", minimum=-210E3, maximum=210E3, default=0, group_by={"apply_voltage" : True})
    ## Voltage measurement
    voltage_limit_mV = FloatParameter(name="Compliance Voltage", units="mV", minimum=-210E3, maximum=210E3, default=100, group_by={"apply_current" : True})
    maximum_current_muA = FloatParameter(name="Maximal Current", units="muA", minimum=-1.05E6, maximum=1.05E6, default=1, group_by={"apply_current" : True})
    minimum_current_muA = FloatParameter(name="Minimum Current", units="muA", minimum=-1.05E6, maximum=1.05E6, default=0, group_by={"apply_current" : True})
    ## Resistance measurement
    
    ### Measurement data
    DATA_COLUMNS = ['Current / muA', 'Voltage Sourcemeter / mV', 'Voltage Voltmeter / mV', 'Resistance Sourcemeter / Ohm', "Resistance Voltmeter / Ohm"]
    
    ### Internal
    keithley2400 : Keithley2400
    keithley2400_connected = False
    agilent34420A : Instrument
    agilent34420A_connected = False
    _data_to_measure = []
    _apply_current = False
    _apply_voltage = False
    _last_datapoint = 0

    def _voltmeter_write(self, command:str) -> None:
        if self.measure_voltmeter:
            self.agilent34420A.write(command)
    
    def startup(self):
        self.metadata_start_time = datetime.datetime.now().strftime("%d.%m.%Y, %H:%M:%S")
        log = logging.getLogger()
        log.info("NovaSEM_IV started ...")
        manager = make_resourcemanager(custom_visalib_path=self.visa_path)
        if len(self.provided_devices) != len(self.requested_devices) and len(self.provided_devices):
            log.error(f"NovaSEM_IV:Requested {len(self.requested_devices)} devices: {self.requested_devices} but got {len(self.provided_devices)} devices: {self.provided_devices}, does not match, aborting!")
            self.shutdown()
            return
        elif len(self.provided_devices) > 1:
            #   Sourcemeter
            keithley2400_info = self.provided_devices[0]
            keithley2400_descriptor = keithley2400_info[DESCRIPTOR]
            keithley2400_adapter_type = keithley2400_info[ADAPTER_TYPE]
            

            min_timeout_ms = self.nplc_sourcemeter/50*1E3
            timeout_ms = min_timeout_ms + 5000

            generic_sourcemeter = Device(descriptor=keithley2400_descriptor, manager=manager,adapter_type=keithley2400_adapter_type,VISAAdapter_args={"timeout":timeout_ms})
            generic_sourcemeter.clear()
            
            self.keithley2400_connected = generic_sourcemeter.successfully_connected
            
            self.keithley2400 = Keithley2400(adapter=generic_sourcemeter.adapter)
            
            if self.measure_voltmeter:
                #   agilent34420A
                agilent34420A_info = self.provided_devices[1]
                agilent34420A_descriptor = agilent34420A_info[DESCRIPTOR]
                agilent34420A_adapter_type = agilent34420A_info[ADAPTER_TYPE]

                min_timeout_ms = self.nplc_voltmeter/50*1E3
                timeout_ms = min_timeout_ms + 5000
                
                genric_voltmeter = Device(descriptor=agilent34420A_descriptor, 
                                        manager=manager,
                                        adapter_type=agilent34420A_adapter_type,
                                        VISAAdapter_args={"timeout":timeout_ms})
                genric_voltmeter.clear()
                
                self.agilent34420A_connected = genric_voltmeter.successfully_connected
                
                self.agilent34420A = Instrument(genric_voltmeter.adapter, name = "Voltmeter")
        else:
            log.error(f"NovaSEM_IV:No devices provided, shutting down!")
            self.shutdown()
            return
        ### Catch potential connection difficulties by probing for errors (coming from experience)
        try:
            self.keithley2400.check_errors()
        except Exception as error:
            log.error(f"NovaSEM_IV:Sourcemeter could not check for errors, measurement might fail in the near future! Try resetting the instruments and restarting.")

        if self.measure_voltmeter:
            try:
                self.agilent34420A.check_errors()
            except Exception as error:
                log.error(f"NovaSEM_IV:Volt Meter could not check for errors, measurement might fail in the near future! Try resetting the instruments and restarting.")
            
            if not self.agilent34420A_connected:
                log.error(f"NovaSEM_IV:Could not connect agilent34420A, shutting down ...")
                self.shutdown()
        
        if self.keithley2400_connected:
            ### Initiate Sourcemeter
            current_limit = self.current_limit_muA*1E-6 # A
            max_voltage = self.maximum_voltage_mV*1E-3  # V
            min_voltage = self.minimum_voltage_mV*1E-3  # V
            
            voltage_limit = self.voltage_limit_mV*1E-3  # V
            max_current = self.maximum_current_muA*1E-6 # A
            min_current = self.minimum_current_muA*1E-6 # A
            
            ### Make data to measure
            self.keithley2400.clear()
            self.keithley2400.reset()
            minimum = 0
            maximum = 0
            if self.measure_voltmeter and not self.apply_current:
                log.error("NovaSEM_IV:Can only apply current when using a voltmeter.")
                self.shutdown()
                return

            if self.measure_current and not self.measure_voltmeter:
                if self.apply_voltage:
                    minimum = min_voltage
                    maximum = max_voltage
                    self.keithley2400.apply_voltage(compliance_current=current_limit)
                    self.keithley2400.measure_current(nplc=self.nplc_sourcemeter, auto_range=True)
                    self._apply_voltage = True
                else:
                    log.error(f"NovaSEM_IV:Can not measure current and not apply voltage!")
                    self.shutdown()
                    return
            elif self.measure_voltage:
                if self.apply_current:
                    minimum = min_current
                    maximum = max_current
                    self.keithley2400.apply_current(compliance_voltage=voltage_limit)
                    self.keithley2400.measure_voltage(nplc=self.nplc_sourcemeter, auto_range=True)
                    self._apply_current = True
                else:
                    log.error(f"NovaSEM_IV:Can not measure voltage and not apply current!")
                    self.shutdown()
                    return
            elif self.measure_resistance:
                if self.apply_current:
                    minimum = min_current
                    maximum = max_current
                    self.keithley2400.apply_current(compliance_voltage=voltage_limit)
                    self.keithley2400.measure_resistance(nplc=self.nplc_sourcemeter, auto_range=True)
                    self._apply_current = True
                elif self.apply_voltage and not self.measure_voltmeter:
                    minimum = min_voltage
                    maximum = max_voltage
                    self.keithley2400.apply_voltage(compliance_current=current_limit)
                    self.keithley2400.measure_resistance(nplc=self.nplc_sourcemeter, auto_range=True)
                    self._apply_voltage = True
                else:
                    log.error(f"NovaSEM_IV:Can not measure resistance and not apply current or voltage!")
                    self.shutdown()
                    return
            else:
                log.error(f"NovaSEM_IV:Incorrect Source / Sense functions, shutting down ...")
                self.shutdown()
                return
                
            if self.sweep_direction == "up":
                self._data_to_measure = np.linspace(minimum, maximum, self.number_of_datapoints, dtype=float)
                log.info("NovaSEM_IV:Sweeping up")
            elif self.sweep_direction == "down":
                self._data_to_measure = np.linspace(maximum, minimum, self.number_of_datapoints, dtype=float)
                log.info("NovaSEM_IV:Sweeping down")
            elif self.sweep_direction == "both":
                up = np.linspace(minimum, maximum, int(self.number_of_datapoints/2), dtype=float)
                down = np.linspace(maximum, minimum, int(self.number_of_datapoints/2), dtype=float)
                self._data_to_measure = np.concatenate((up, down), axis=None)
                log.info("NovaSEM_IV:Sweeping up and down")

            if self.terminal == "Front":
                self.keithley2400.use_front_terminals()
            elif self.terminal == "Rear":
                self.keithley2400.use_rear_terminals()
            else:
                log.error("NovaSEM_IV:Invalid terminal provided, shutting down ...")
                self.shutdown()
                return
            self.keithley2400.disable_source()

            if self.measure_voltmeter:
                ### Initiate agilent34420A
                self.agilent34420A.clear()
                self.agilent34420A.reset()
                self._voltmeter_write(":sense:function \"voltage\"")
                self._voltmeter_write(":sense:voltage:RANGe:AUTO ON")
                self._voltmeter_write(":sense:voltage:NPLCycles "+str(self.nplc_voltmeter))
                self._voltmeter_write(":output:state 0")
        else:
            if not self.keithley2400_connected:
                log.error(f"NovaSEM_IV:Could not connect Sourcemeter, shutting down ...")
       
        return
    
    def _ramp_sourcemeter_measurement(self, target:float, number_steps:int|None=None, pause_ms:float|None=None) -> None:
        """A function that emulates the `.ramp_to_...()` from the `Keithley 2600 Channel` class due to a bug where the applied current/voltage was always a multiple of muA / mV.\n
        The target must match the `self._apply_...`.

        Args:
            target (float): Target Voltage / Current in Ampere / Volt.
            number_steps (int | None): Number of steps to target. Defaults to self.number_of_steps_measurement when None.
            pause_ms (float | None): Time to remain on one step in milliseconds. Defaults to self.pause_per_step_measurement_ms when None.

        """
        # Returns:
        #     float: Applied Voltage / Current in Ampere / Volt depending if `self._apply_voltage` or `self._apply_current`.
        if number_steps is None:
            number_steps = self.number_of_steps
        if pause_ms is None:
            pause_ms = self.pause_per_step_ms
        
        points = np.linspace(self._last_datapoint, target, int(number_steps))
        self._last_datapoint = target
        for point in points:
            if self.should_stop():
                break
            if self._apply_voltage:
                self.keithley2400.write(f":source:voltage:level {point}")
            elif self._apply_current:
                self.keithley2400.write(f":source:current:level {point}")
            time.sleep(pause_ms*1E-3)
        
        # return_val = None
        # if self._apply_voltage:
        #     return_val = self.keithley2400.voltage
        # elif self._apply_current:
        #     return_val = self.keithley2400.current
        # return return_val
    
    def execute(self):
        log = logging.getLogger()
        if self.keithley2400_connected:
            log.info("NovaSEM_IV:Measurement started ...")
            self.keithley2400.enable_source()

            self._voltmeter_write(':output:state 1')
            
            ### Ensure that sample and source meter are in a stable state at all times
            if abs(self._data_to_measure[0]) > 0:
                slow_ramp_number_of_steps = 1
                if self._apply_current:
                    slow_ramp_number_of_steps = int(self._data_to_measure[0]*1E6)
                elif self._apply_voltage:
                    slow_ramp_number_of_steps = int(self._data_to_measure[0]*1E3)

                if slow_ramp_number_of_steps < 1:
                    slow_ramp_number_of_steps = 1

                slow_ramp_pause_per_step_ms = 10
                log.info(f"Slowly ramping to source value in {slow_ramp_number_of_steps} steps with {slow_ramp_pause_per_step_ms}ms per step, i.e. in {round(slow_ramp_number_of_steps*slow_ramp_pause_per_step_ms*1E-3,1)}s ...")
                self._ramp_sourcemeter_measurement(target=data_point, number_steps=slow_ramp_number_of_steps, pause_ms=slow_ramp_pause_per_step_ms*1E-3)
            ###
                
            for data_index in range(0,len(self._data_to_measure)):
                if self.should_stop():
                    log.info("Caught the stop flag in the procedure")
                    break
                else:
                    data_point = self._data_to_measure[data_index]
                    current, voltage_voltmeter,voltage_keithley2400, resistance_keithley2400 = (None, None, None, None)
                    
                    progress = data_index/self.number_of_datapoints*100

                    if self._apply_voltage:
                        self._ramp_sourcemeter_measurement(target=data_point)
                        voltage_keithley2400 = data_point
                    elif self._apply_current:
                        self._ramp_sourcemeter_measurement(target=data_point)
                        current = data_point

                    try:
                        ### Filtering
                        if self.filtering:
                            filter_values = {'Current / muA':np.zeros(shape=self.filter_count),
                                            'Voltage Sourcemeter / mV':np.zeros(shape=self.filter_count),
                                            'Voltage Voltmeter / mV':np.zeros(shape=self.filter_count),
                                            'Resistance Sourcemeter / Ohm':np.zeros(shape=self.filter_count)}
                            
                            for idx in range(0, self.filter_count):
                                if self.should_stop():
                                    log.info("Caught the stop flag in the procedure")
                                    break

                                if self.measure_voltmeter:
                                    filter_values["Voltage Voltmeter / mV"][idx] = self.agilent34420A.ask(":read?")
                                if self.measure_current:
                                    filter_values['Current / muA'][idx] = self.keithley2400.current
                                if self.measure_voltage:
                                    filter_values['Voltage Sourcemeter / mV'][idx] = self.keithley2400.voltage
                                if self.measure_resistance:
                                    filter_values['Resistance Sourcemeter / Ohm'][idx] = self.keithley2400.resistance
                                time.sleep(self.filtering_delay_ms*1E-3)
                            
                            if self.measure_voltmeter:
                                voltage_voltmeter = np.mean(filter_values["Voltage Voltmeter / mV"])
                            if self.measure_current:
                                current = np.mean(filter_values['Current / muA'])
                            if self.measure_voltage:
                                voltage_keithley2400 = np.mean(filter_values['Voltage Sourcemeter / mV'])
                            if self.measure_resistance:
                                resistance_keithley2400 = np.mean(filter_values['Resistance Sourcemeter / Ohm'])
                        ### no Filtering
                        else:
                            if self.measure_voltmeter:
                                voltage_voltmeter = self.agilent34420A.ask(":read?")
                            if self.measure_voltage:
                                voltage_keithley2400 = self.keithley2400.voltage
                            if self.measure_current:
                                current = self.keithley2400.current
                            if self.measure_resistance:
                                resistance_keithley2400 = self.keithley2400.resistance
                        current             = float(current)*1E6   if current is not None else None
                        voltage_voltmeter   = float(voltage_voltmeter)*1E3  if voltage_voltmeter is not None and self.measure_voltmeter else None
                        voltage_keithley2400= float(voltage_keithley2400)*1E3   if voltage_keithley2400 is not None else None

                        if self.measure_resistance:
                            resistance_keithley2400 = float(resistance_keithley2400)    if resistance_keithley2400 is not None else None
                        else:
                            resistance_keithley2400 = float(voltage_keithley2400/current)*1E3    if current != 0 and voltage_keithley2400 is not None and current is not None else None

                        resistance_4probe = voltage_voltmeter/current*1E3 if voltage_voltmeter is not None and current is not None and current != 0 else None
                        return_data = {
                            'Current / muA' : current if current is not None else '',
                            'Voltage Voltmeter / mV' : voltage_voltmeter if voltage_voltmeter is not None else '',
                            'Voltage Sourcemeter / mV' : voltage_keithley2400 if voltage_keithley2400 is not None else '',
                            'Resistance Sourcemeter / Ohm' : resistance_keithley2400 if resistance_keithley2400 is not None else '',
                            "Resistance Voltmeter / Ohm" : resistance_4probe if resistance_4probe is not None else ''
                        }
                        self.emit('results', return_data)
                    except Exception as error:
                        log.error(f"NovaSEM_IV:Invalid data received from device, failed to find values due to an exception: {error}")
                        self.keithley2400.clear()
                        if self.measure_voltmeter:
                            self.agilent34420A.clear()
                    self.emit('progress', progress)

            self.keithley2400.disable_source()
            self._voltmeter_write(":output:state 0")
            return
        else:
            self.shutdown()
            return

    def shutdown(self):
        log = logging.getLogger()
        try:
            if self.keithley2400_connected:
                self.keithley2400.shutdown()
                self.keithley2400.adapter.close()
            else:
                log.error("NovaSEM_IV:Unable to shutdown Sourcemeter.")
        except:
            log.error("NovaSEM_IV:Unable to shutdown Sourcemeter.")
        if self.measure_voltmeter:
            try:
                if self.agilent34420A_connected:
                    self._voltmeter_write(":output:state 0")
                    self.agilent34420A.shutdown()
                    self.agilent34420A.adapter.close()
                else:
                    log.error("NovaSEM_IV:Unable to shutdown Voltmeter.")
            except:
                log.error("NovaSEM_IV:Unable to shutdown Voltmeter.")
        super().shutdown()
    
    def get_estimates(self, sequence_length=None, sequence=None):
        filter_time = 0
        if self.filtering:
            filter_time = self.filter_count*self.filtering_delay_ms*1E-3
        
        time_nplc = self.nplc_sourcemeter/50 if not self.measure_voltmeter else (self.nplc_sourcemeter+self.nplc_voltmeter)/50

        time_to_datapoint = self.number_of_steps*(self.pause_per_step_ms*1E-3 + time_nplc)
        time_spent_on_datapoint = time_nplc if not self.filtering else self.filter_count*(self.filtering_delay_ms*1E-3 + time_nplc)
        total_time = self.number_of_datapoints*( time_to_datapoint + time_spent_on_datapoint )

        finished_at = datetime.datetime.now() + datetime.timedelta(seconds=total_time)

        estimates = [
            ("Duration", "%d s" % int(total_time)),
            ("Time per datapoint", "%d ms" % int((time_to_datapoint+time_spent_on_datapoint)*1E3)),
            ("Time spent averaging", "%d ms" % int(filter_time*1E3)),
            ("Sequence length", str(sequence_length)),
            ('Finished at', finished_at.strftime("%H:%M")),
        ]
        return estimates

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = WindowSingleDock(NovaSEM_IV)
    window.show()
    sys.exit(app.exec())