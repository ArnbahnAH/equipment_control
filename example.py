#   To show more information to the log-widget in the GUI
import logging, sys
log = logging.getLogger()   # globally is fine

#   Usual pymeasure stuff
from pymeasure.display.Qt import QtWidgets
#   Parameters and Metadata classes
from pymeasure.experiment import IntegerParameter, FloatParameter, Parameter, ListParameter, BooleanParameter, Metadata
#   A generic example instrument
from pymeasure.instruments import Instrument

#   This project
from equipment_control.device import DeviceProcedure, DESCRIPTOR, ADAPTER_TYPE, Device, make_resourcemanager
from equipment_control.windows import WindowSingleDock

import time # for example only
class ExampleProcedure(DeviceProcedure):
    """Example docstring to be displayed in the help window.
    """
    #   properties of DeviceProcedure, supported by any DeviceManagerWindow based GUI
    name = "The name of the procedure to be shown in the window title"
    requested_devices = ["Test device 1"]  # devices you want the user to specify
    #   Default information to be displayed instead of GPIB0::1::INSTR, makes things faster if the devices have a known adapter
    default_devices = [
        {DESCRIPTOR:"pyvisa descriptor of Test device 1", ADAPTER_TYPE:"GPIB"},
    ]   # need to be as many as requested_devices, ADAPTER_TYPE can be GPIB, RS232 or AR488
    inputs = [
        "show_parameter",
        "test_folding_parameter"
    ] #  ALL the input variables like pymeasure wants you to input in a window class, but now in the procedure itself (bundles everything neatly)
    displays = inputs # all the parameters you want to show in the file selector, here all are shown
    tool_tip_information = {
        "show_parameter":"Shows something new", 
        "test_folding_parameter":"Only visible when Make 'Test int' appear is enabled"
    }   # now users know what the parameters do!
    ### THATS IT! Now the DeviceManagerWindow will allow the user to specify these three devices, sould they differ from their default_devices entries

    ### From here do as specified in the pymeasure documentation, like:
    show_parameter = BooleanParameter(name="Make 'Test int' appear", default=False)
    test_folding_parameter = IntegerParameter(name="Test int", minimum=1, maximum=100, default=5, group_by={"show_parameter":True})
    test_metadata = Metadata(name="Meta",default="Not specified, must be done when the procedure is running!")

    DATA_COLUMNS = [
        "Output 1",
        "Output 2"
    ]   # define what is supposed to be output by the procedure

    #   good practice
    test_instrument : Instrument
    test_instrument_connected = False

    def start_a_device(self, device_info:list, manager):
        log.info("This will cause an error if this device is not really connected, but for this example it is fine...")
        #   Information is extracted like given in default_devices:
        descriptor = device_info[DESCRIPTOR]
        adapter_type = device_info[ADAPTER_TYPE]
        #   Now you should use the Device class as it incorporates support for the AR488 adapter or you check the adapter_type and handle it yourself
        device = Device(
            descriptor=descriptor,
            manager=manager,
            adapter_type=adapter_type,
            VISAAdapter_args={} # maybe you need to specify something here, these are the arguments for either the VISAAdapter of pymeasure or the AR488Adapter of equipment_control.ar488, they are very useful to tell pyvisa / the AR488 how to treat the device, i.e. write / read termination, EOS signal, etc ...
        )
        #   get the adapter pymeasure is supposed to use for instrument communication with device.adapter
        self.test_instrument_connected = device.successfully_connected    # for shutting it down
        if device.successfully_connected:   # might be useful if creating the adapter fails for some reason
            adapter = device.adapter
            self.test_instrument = Instrument(adapter=adapter)
        else:
            self.shutdown()

    #   entry point of the procedure
    def startup(self):
        self.test_metadata = "Metadata was successfully written!"
        log.info(f"You selected the int parameter to be '{self.test_folding_parameter}'")

        #   start the devices
        if len(self.provided_devices) == len(self.requested_devices):   # Always better to check than crash later
            #   Get info from the GUI, might be different from default_devices if the user changed it
            info_on_test_device_1 = self.provided_devices[0]
            #   Get the path to the visa library that might be specified by the user via self.visa_path and open a pyvisa resource manager, can also be done via pyvisa.ResourceManager(self.visa_path)
            manager = make_resourcemanager(custom_visalib_path=self.visa_path)
            self.start_a_device(device_info=info_on_test_device_1, manager=manager)
        else:
            log.error("OH! Something went really wrong there, provided_devices was not initiated!")

        return super().startup()
    
    #   executes the procedure
    def execute(self):
        #   some measurement
        for i in range(0,self.test_folding_parameter):
            if self.should_stop():  # very necessary to allow a user to stop the measurement, usually used in the measurement loop
                log.info("I was informed by the GUI to stop the measurement, shutting down...")
                break
            #   emit results
            result = {
                "Output 1" : i,
                "Output 2" : i**2
            }
            self.emit('results',result)
            #   update progressbar
            progress = int(i/self.test_folding_parameter*100)
            self.emit('progress',progress)
            time.sleep(0.5)
            # emit

        return super().execute()

    #   shutdown your devices safely and end the procedure
    def shutdown(self):
        if self.test_instrument_connected:
            self.test_instrument.shutdown()
        else:
            log.error("Instrument was not initiated correctly to be shut down!")
        return super().shutdown()

#   Now open the procedure on execution with a GUI of your choice, like the WindowSingleDock
if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = WindowSingleDock(ExampleProcedure)
    window.show()
    sys.exit(app.exec())