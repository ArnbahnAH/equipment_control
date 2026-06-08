"""A header file that provides `pyvisa` and some `pymeasure` backed for handling GPIB devices.\n
**Important**: The information about GPIB devices will always be parsed with the following dictionary keys and values:\n
**{DESCRIPTOR:str, GPIB_ADDRESS:str, ADAPTER_TYPE:str, IDENTIFICATION:str}**\n
Not every method that returns information about GPIB devices will have all these keys but will always return **DESCRIPTOR** and **ADAPTER_TYPE** which are understood by the `Device` class. This class internally creates the appropriate `pymeasure` adapter as `Device.adapter`. This adapter can then be used to create `pymeasure` instrument classes for communication regardles of the type of GPIB adapter used.\n
**Supported adapter types:**\n
- GPIB
- AR488
- RS232
\n
The `Device` class is supposed to provide a `pymeasure` conform adapter for all above adapter types.\n
\n
Communication for finding and resetting devices is handled with `ADAPTER_COMMUNICATION`. This dictionary contains dialects as keys (string given to the user in the log) and a tuple of (VISAAdapter arguments, identification command, reset command) where `VISAAdapter arguments` is a dict for the `Device` class (empty if not needed) and `identification command` and `reset command` can be None or "" if not supported by the device dialect.
"""
import logging, threading, time
from typing import (Optional, LiteralString)
from warnings import warn
import pyvisa   # VISA adapters (GPIB)
from pymeasure.adapters import VISAAdapter
from pymeasure.experiment import Procedure
log = logging.getLogger()
log.addHandler(logging.NullHandler())

### Own libraries
from .ar488 import AR488Adapter, AR488

### "Magic numbers"
DESCRIPTOR      = "Descriptor"
ADAPTER_TYPE    = "Adapter Type"
GPIB_ADDRESS    = "GPIB Address"
IDENTIFICATION  = "Identification"
DIALECT         = "Dialect"

#   Internally used for communications in analyse_port
#   Structure: Dialect : (VISAAdapter arguments, identification command or None, reset command or "")
ADAPTER_COMMUNICATION = {
    "SCPI"    :   ({},"*IDN?","*RST"),
    "OXFORD"  : ({"send_end" : True, "query_delay" : 0.2, "read_termination" : '\r', "write_termination" : '\r', "chunk_size" : 512},"@0V",None),
}   #   Keys: dialect, Value: Tuple(VISAAdapter_args of 'Device', string to be queried for getting information about the device)

### GPIB device base class for communication (handles AR488 & GPIB communication)
class Device:
    """
    Wrapper for pyvisa and pymeasure objects describing a device.\n
    Expects SCPI support.\n
    Takes 'GPIB', 'AR488' and 'RS232' connected devices and returns a `pymeasure` VISAAdapter 'Device.adapter' to be used in `pymeasure` `pymeasure.instruments.Instrument` class and its subclasses.
    
    Attributes
    ----------
    adapter : pymeasure.adapters.VISAAdapter | ar488.AR488Adapter
        `Adapter<https://pymeasure.readthedocs.io/en/stable/api/adapters.html>`__ used by pymeasure to communicate with the device. Defaults to None.
    successfully_connected : bool
        True if the Device class encountered no errors upon connecting and the GPIB device was accessible.
    descriptor : str
        Device descriptor used and understood by pyvisa and pymeasure, e.g. 'GPIB0::10::INSTR'.
    adapter_type : str
        Description of the adapter used by the device, can be 'GPIB', 'AR488' or 'RS232'. Defaults to 'Not known'.
    manager : pyvisa.ResourceManager
        Resource manager that found the device.
    
    Methods
    -------
    close() -> None:
        Closes the `pyvisa` connection. Should always be called when the device is not used anymore so that it is ready for a new owner.
    clear() -> None:
        Clears the GPIB bus if such an adapter is used ('GPIB' or 'AR488').
    """
    ### Descriptions
    successfully_connected : bool = False
    descriptor : str
    adapter_type : str = 'Not known'
    gpib_address : str = 'Not known'
    ### Operants
    manager : pyvisa.ResourceManager
    adapter : VISAAdapter|AR488Adapter = None
    ### Internal definitions
    id_separator : str = ','
    
    def __init__(self, descriptor:str, manager:pyvisa.ResourceManager, adapter_type:str="GPIB", VISAAdapter_args : dict = {}) -> None:
        """Creates a wrapper for pyvisa and pymeasure objects for different `adapter_types` and returns an `Device.adapter` object (`pymeasure` VISAAdapter) to be used in `pymeasure` instrument classes.

        Args:
            descriptor (str): Device descriptor used and understood by pyvisa and pymeasure, e.g. 'GPIB0::10::INSTR', 'ASRL5::INSTR', etc..
            manager (pyvisa.ResourceManager): pyvisa resource manager that found the device with the `descriptor`.
            **VISAAdapter_args (dict): Additional arguments that can be sent to the self.adapter on initialization. These will be forwarded to the `pyvisa` resource (with the exception of '`query_delay`' (see pymeasure docs), to issue this use `adapter.connection.query_delay`).
            adapter_type (str): Defines the type of connector used, can be `'GPIB'`, `'AR488'` or `'RS232'` for GPIB-connector, AR488 arduino or the RS232 connection. Defaults to 'GPIB'.
        """
        ### Process information
        self.descriptor = descriptor
        self.manager = manager
        ### Define access to the device
        error_msg = lambda adapter_type, error : f"Device:Failed to initialise Device as '{adapter_type}': An exception occurred: '{error}', check if the device is connected and the descriptor '{self.descriptor}' and manager '{self.manager}' are valid. If the device does not respond to SCPI commands ignore this and following warnings."
        if adapter_type == "GPIB":
            if 'GPIB' not in descriptor:
                log.warning(f"Device:adapter_type was set to 'GPIB' but descriptor {descriptor} does not match, proceed anyways.")
                warn(f"Device:adapter_type was set to 'GPIB' but descriptor {descriptor} does not match, proceed anyways.")
            try:
                self._open_as_GPIB(VISAAdapter_args=VISAAdapter_args)
            except Exception as initialisation_error:
                log.error(error_msg("GPIB",initialisation_error))
                warn(error_msg("GPIB",initialisation_error))
                return
        elif adapter_type == "AR488":
            try:
                self._open_as_AR488(VISAAdapter_args=VISAAdapter_args)
            except Exception as initialisation_error:
                log.error(error_msg("AR488",initialisation_error))
                warn(error_msg("AR488",initialisation_error))
                return
        elif adapter_type == "RS232":
            try:
                self._open_as_RS232(VISAAdapter_args=VISAAdapter_args)
            except Exception as initialisation_error:
                log.error(error_msg("RS232",initialisation_error))
                warn(error_msg("RS232",initialisation_error))
                return
        else:
            log.error(f"Device:Incorrect adapter_type, must be 'GPIB', 'AR488' or 'RS232' not '{adapter_type}'.")
            raise ValueError(f"Device:Incorrect adapter_type, must be 'GPIB', 'AR488' or 'RS232' not '{adapter_type}'.")
        pass
    
    def _open_as_GPIB(self, VISAAdapter_args) -> None:
        ### Generate pyvisa & pymeasure classes
        self.adapter_type = "GPIB"
        visalib = self.manager.visalib
        self.adapter = VISAAdapter(resource_name=self.descriptor, visa_library=visalib, **VISAAdapter_args)
        self._find_address_GPIB()
        ### Generate information about the device
        self.successfully_connected = True
    
    def _open_as_RS232(self, VISAAdapter_args) -> None:
        ### Generate pyvisa & pymeasure classes
        self.adapter_type = "RS232"
        visalib = self.manager.visalib
        self.adapter = VISAAdapter(resource_name=self.descriptor, visa_library=visalib, **VISAAdapter_args)
        ### Generate information about the device
        self.successfully_connected = True
        
    def _open_as_AR488(self, VISAAdapter_args) -> None:
        ### Generate pyvisa & pymeasure classes
        self.adapter_type = "AR488"
        visalib = self.manager.visalib
        self.adapter = AR488Adapter(resource_name=self.descriptor, visa_library=visalib, **VISAAdapter_args)
        self._find_address_AR488()
        ### Generate information about the device
        self.successfully_connected = True
    
    def _find_address_GPIB(self):
        try:
            positions = [i for i, x in enumerate(self.descriptor) if ':' == x]
            if len(positions) > 1:
                position_0 = -1
                substrings = []
                for position_1 in positions:
                    substring = self.descriptor[position_0+1:position_1]
                    substrings.append(substring)
                    position_0 = position_1
                if len(substrings) >= 2:
                    self.gpib_address = substrings[2]
                else:
                    log.warning(f"Device:Could not find  GPIB_ADDRESS of '{self.descriptor}', format of descriptor response is unsupported, expected 'GPIBx::y::INSTR' with primary address 'y'.")
            else:
                log.warning(f"Device:Could not find  GPIB_ADDRESS of '{self.descriptor}', format of descriptor response is unsupported, expected separator ':'.")
        except Exception as error:
            log.warning(f"Device:Could not find GPIB_ADDRESS of '{self.descriptor}' due to an exception: '{error}'")
        pass

    def _find_address_AR488(self):
        address = None
        try:
            address = self.adapter.ar488.address
        except Exception as error:
            log.warning(f"Device:Could not find GPIB_ADDRESS of '{self.descriptor}' using the AR488 class due to an exception: {error}")
        
        if type(address) == int:
            self.gpib_address = str(address)
        else:
            log.warning(f"Device:Could not find GPIB_ADDRESS of '{self.descriptor}' using the AR488 class, AR488 did not respond with a valid response, got '{address}' but expected integer.")
        pass
    
    def close(self) -> None:
        """Closes the `pyvisa` connection to the device.
        """
        if self.adapter is not None:
            try:
                self.adapter.connection.close()
            except Exception as error:
                log.warning(f"Device: Adapter of resource '{self.descriptor}' can not be closed due to an exception: '{error}'")
        else:
            log.debug(f"Device: Resource '{self.descriptor}' can not be closed as it was not opened successfully!")
        self.successfully_connected = False
    
    def clear(self) -> None:
        """Sends the device clear signal over the GPIB bus if the adapter is connected to GPIB, i.e. 'GPIB' and 'AR488'."""
        if self.successfully_connected:
            if self.adapter_type == "GPIB":
                self.adapter.connection.clear()
            elif self.adapter_type == "AR488":
                try:
                    self.adapter.ar488.clear()
                except Exception as error:
                    log.warning(f"Device:No instrument seems to be connected to AR488 '{self.descriptor}', can not clear the instrument: {error}")
            else:
                log.debug(f"Device:Can not clear the GPIB bus for an adapter of type '{self.adapter_type}'!")
                warn(f"Device:Can not clear the GPIB bus for an adapter of type '{self.adapter_type}'!")
        else:
            log.debug(f"Device: Resource '{self.descriptor}' can not be cleared as it was not opened successfully!")

    def __repr__(self) -> str:
        return "<Device(%s, %s>" % (self.descriptor, self.manager)
    def __str__(self) -> str:
        return "Device %s" % (self.descriptor)

def make_resourcemanager(custom_visalib_path : Optional[LiteralString] = None) -> pyvisa.ResourceManager | None:
    """Makes a pyvisa ResourceManager.

    Args:
        custom_visalib_path (Optional[LiteralString], optional): Path to the VISA library, gets changed if the path was incorrect but another one was found. Defaults to None.

    Raises:
        Exception: When pyvisa cannot create a ResourceManager due to an unknown exception.

    Returns:
        pyvisa.ResourceManager: ResourceManager based in the custom path if it was possible otherwise it will search for a different VISA library.
    """
    pyvisa_resourcemanager = None
    error = 'No errors encountered'
    if (custom_visalib_path is not None) and (custom_visalib_path!=''):
        try:
            pyvisa_resourcemanager = pyvisa.ResourceManager(custom_visalib_path)
        except Exception as error:
            log.warning(f"make_resourcemanager:'{custom_visalib_path}' is not a valid VISA library according to pyvisa: {error}")
            try:
                pyvisa_resourcemanager = pyvisa.ResourceManager()
                custom_visalib_path = pyvisa_resourcemanager.visalib.library_path
            except Exception as error:
                log.warning(f"make_resourcemanager: Unable to make a pyvisa Resource Manager due to an exeption: {error}")
                pass
    else:
        try:
            pyvisa_resourcemanager = pyvisa.ResourceManager()
            custom_visalib_path = pyvisa_resourcemanager.visalib.library_path
        except Exception as error:
            pass
    if pyvisa_resourcemanager is None:
        log.error(f"make_resourcemanager: Unable to make a pyvisa Resource Manager due to an exeption: {error}")
    return pyvisa_resourcemanager

### Functions allowing for easy probing of connected devices and extracting information
def valid_connector(descriptor:str, manager:pyvisa.ResourceManager) -> tuple[bool, str|None, str]:
    """Used by the `DeviceManagerWindow` class and the `GPIBDeviceFinderGUI` as prerequisites for opening a `Device` class with the appropriate adapter string returned by this function.\n
    Checks if a descriptor of a `pyvisa` resource is a valid connector to be probed as an GPIB device / adapter and maps the resource to the appropriate adapter type.\n
    Supports "GPIB", "AR488" and "RS232".\n
    Method:\n
    Read resource name and \n
    - if GPIB is found --> GPIB
    - if serial (ASRL) is found and `++ver` is successfully executed --> AR488
    - if serial (ASRL) is found and not AR488 --> RS232

    Args
    -------
        descriptor : str
            DESCRIPTOR of a `pyvisa` resource.
        manager : pyvisa.ResourceManager
            Manager of `pyvisa` to check if VISA library can open and access the resource.

    Returns
    -------
        adapter_type : str | None
            Name of the adapter to be used by the `Device` class to open the resource. If resource is not accessible or not supported will return None.
        info : str
            An information string about the state of the resource.
    """
    valid = False
    adapter_type = None
    info = "not supported"

    if "GPIB" in descriptor:
        try:
            resource = manager.open_resource(descriptor)
            valid = True
            adapter_type = "GPIB"
            info = "recognised as 'GPIB'"
            resource.close()
        except:
            info = f"recognised as 'GPIB' but can not be opened by VISA manager @ '{manager}', ensure the manager is correct or use a different VISA library"
    elif "ASRL" in descriptor:
        adapter_type = "RS232"
        info = "recognised as 'Serial'"
        #   Try to open as AR488
        try:
            resource = manager.open_resource(descriptor)
            try:
                ar488 = AR488(resource)
                ver = ar488.version()
                valid = True
                adapter_type = "AR488"
                info = f"recognised as 'AR488' {ver}"
            except:
                valid = True
                adapter_type = "RS232"
                info = "recognised as 'Serial' but is not 'AR488', treating as 'RS232'"
            resource.close()
        except:
            adapter_type = None
            info = f"recognised as 'Serial' but can not be opened by VISA manager @ '{manager}', ensure the manager is correct or use a different VISA library"
    return valid, adapter_type, info

def find_devices(manager:pyvisa.ResourceManager, excluded:list[str]=["ttyS"], multithreading:bool=True) -> list[dict]:
    """Automatically searches for connected devices, i.e. probes all ports marked as valid by the `valid_connector` function.

    Args
    -------
        manager : pyvisa.ResourceManager
            The manager to be used to find resources using `pyvisa`.
        excluded : list[str], optional
            List of strings that are excluded from the descriptor of any valid resource to speed up finding resources. Defaults to ["ttyS"].
        multithreading : bool, optional
            Use multithreading to analyse ports, can speed up the aquisition of possible_devices for independent ports. If two devices share the same bus multithreading can lead to undesired results and should not be used. Defaults to True.
    Returns
    -------
        possible_devices : list[dict]
            List of possible devices as dictionaries, as expected by `DeviceProcedure`: With keys: {DESCRIPTOR, GPIB_ADDRESS, ADAPTER_TYPE, IDENTIFICATION, DIALECT}
    """
    possible_devices = []
    resource_list = manager.list_resources()
    ### Clean list of resources
    valid_resources = []
    num_valid_resources = 0
    if len(resource_list) > 0:
        for resource in resource_list:
            exclude_resource = False
            for excluded_str in excluded:
                if excluded_str in resource:
                    exclude_resource = True
                    break
            if not exclude_resource:
                num_valid_resources += 1
                valid_resources.append(resource)
            else:
                log.debug(f"find_devices:Skipping '{resource}', descriptor contains excluded string, exluded are '{excluded}'")
    else:
        log.error("find_devices:No connections found!")
        return possible_devices

    if num_valid_resources == 0:
        log.error("find_devices:No valid connections found!")
        return possible_devices

    log.info(f"find_devices:{num_valid_resources} valid connections found!")

    ### Open thread for every possible device
    thread_list = [None for _ in range(0,num_valid_resources)]
    ### Singlethreadding
    if not multithreading:
        return_data = dict()
        for index in range(0, num_valid_resources):
            resource = valid_resources[index]
            analyse_port(return_data,index,resource,manager)
            data, valid, _, info = return_data[str(index)]

            if valid:
                if data is not None:
                    log.info(f"find_devices:Opened '{resource}', connection is {info}: {data[IDENTIFICATION]}")
                    possible_devices.append(data)
                    log.debug(f"{resource}: {data}")
                else:
                    log.warning(f"find_devices:Could not find information about '{resource}' but connection is {info}. Might be a valid resource.")
            else:
                log.info(f"find_devices:Skipped '{resource}', connection is {info}")

    ### Multithreading
    else:
        thread_return_data = dict()
        for thread_index in range(0, num_valid_resources):
            resource = valid_resources[thread_index]
            
            thread_return_data[str(thread_index)] = [None, False, None, "unknown error"]
            thread = threading.Thread(target=analyse_port, args=(thread_return_data,thread_index,resource,manager))
            thread.start()
            thread_list[thread_index] = thread
            
        ### Wait until all threads are finished and read the data
        for thread_index in range(0,num_valid_resources):
            resource = valid_resources[thread_index]
            if str(thread_index) in thread_return_data.keys():
                thread_list[thread_index].join()
                data, valid, _, info = thread_return_data[str(thread_index)]
                if valid:
                    if data is not None:
                        log.info(f"find_devices:Thread {thread_index} opened '{resource}', connection is {info}: {data[IDENTIFICATION]}")
                        possible_devices.append(data)
                        log.debug(f"{resource}: {data}")
                    else:
                        log.warning(f"find_devices:Thread {thread_index} could not find information about '{resource}' but connection is {info}. Might be a valid resource.")
                else:
                    log.info(f"find_devices:Thread {thread_index} skipped '{resource}', connection is {info}")

    return possible_devices

def analyse_port(thread_return_data:dict, thread_index:int, resource:str, manager:pyvisa.ResourceManager) -> None:
    """A function that scans a specific port, requires a valid resource name and manager.\n
    Used for multithreading purposes.

    Args
    -----
        thread_return_data : dict
            The dictionary with key `thread_index` containing the information found about the connected device on the port with `pyvisa` descriptor `resource` in the format {DESCRIPTOR, GPIB_ADDRESS, ADAPTER_TYPE, IDENTIFICATION, DIALECT}.
        thread_index : int
            A unique number identifying the thread running this function.
        resource : str
            The `pyvisa` descriptor of the port to open.
        manager : pyvisa.ResourceManager)
            The `pyvisa` manager to be used to open the `resource`.
        adapter_type : str
            The type of adapter expected by the `Device` class.
    """
    valid, adapter_type, info = valid_connector(descriptor=resource, manager=manager)
    thread_return_data[str(thread_index)] = [None, valid, adapter_type, info]
    if valid:
        successful = False
        device_dialect  = "Not known"
        identification = "Not known"
        #   Search for dialect of the device from a list of known ones
        found_right_dialect = False
        for device_dialect in ADAPTER_COMMUNICATION.keys():
            VISAAdapter_args        = ADAPTER_COMMUNICATION[device_dialect][0]
            identification_command  = ADAPTER_COMMUNICATION[device_dialect][1]

            device = Device(descriptor=resource, 
                            manager=manager, 
                            adapter_type=adapter_type, 
                            VISAAdapter_args=VISAAdapter_args)
            successful = device.successfully_connected
            #   Find identification
            device.clear()
            if identification_command is None or identification_command=="":
                log.warning(f"analyse_port:Device '{resource}' is recognised as {device_dialect} but no identification command is known for this dialect!")
            else:
                try:
                    identification = device.adapter.ask(identification_command).strip()
                    found_right_dialect = True
                    thread_return_data[str(thread_index)][3] += f" and responds to {device_dialect} '{identification_command}'"
                except:
                    log.debug(f"analyse_port:Device '{resource}' does not respond to {device_dialect} '{identification_command}'.")
                    device.clear()
            device.close()
            if found_right_dialect:
                break
        
        if not found_right_dialect:
            log.warning(f"analyse_port:Device '{resource}' does not respond to any of these dialects: {list(ADAPTER_COMMUNICATION.keys())}!")
            device_dialect  = "Not known"

        if successful:
            data = {
                DESCRIPTOR : str(device.descriptor).replace(',',' '),
                GPIB_ADDRESS : str(device.gpib_address).replace(',',' '),
                ADAPTER_TYPE : str(adapter_type).replace(',',' '),
                IDENTIFICATION : str(identification).replace(',',' '),
                DIALECT : device_dialect
            }
            thread_return_data[str(thread_index)][0] = data
        else:
            log.error(f"analyse_port: Thread {thread_index} could not open '{resource}'!")

def reset_all_connected_devices(manager:pyvisa.ResourceManager, multithreading:bool=True) -> None:
    """Find and reset + clear all devices. Give crude information about the status of devices in the log. Can help if a device hangs and does not respond to commands properly.\n
    Might have to be executed multiple times.

    Args
    ------
    manager : pyvisa.ResourceManager
            The manager to be used to find resources using `pyvisa`.
    multithreading : bool, optional
        Use multithreading to analyse ports, can speed up the aquisition of possible_devices for independent ports. If two devices share the same bus multithreading can lead to undesired results and should not be used. Defaults to True.
    """
    devices = find_devices(manager=manager, multithreading=multithreading)
    for dev in devices:
        device = Device(descriptor=dev[DESCRIPTOR], manager=manager, adapter_type=dev[ADAPTER_TYPE],VISAAdapter_args=ADAPTER_COMMUNICATION[dev[DIALECT]][0])
        reset_command = ADAPTER_COMMUNICATION[dev[DIALECT]][2]
        try:
            log.info(f"reset_all_connected_devices:Clearing '{dev[DESCRIPTOR]}'.")
            device.clear()
            time.sleep(0.1)
            if reset_command is None or reset_command=="":
                log.warning(f"reset_all_connected_devices:Device '{dev[DESCRIPTOR]}' is recognised as '{dev[DIALECT]}' but no reset command is known, can not reset device!")
            else:
                log.info(f"reset_all_connected_devices:Resetting '{dev[DESCRIPTOR]}' with '{reset_command}'.")
                device.adapter.write(reset_command)
        except Exception as error:
            log.error(f"reset_all_connected_devices:Encountered an error with device '{dev[DESCRIPTOR]}': '{error}'")

### Procedures base class
class DeviceProcedure(Procedure):
    """
        Template for procedures used by the `DeviceManagerWindow`, **all children must declare attributes `inputs` and `displays`** and can declare `requested_devices` explicitly if measurement requires selecting a GPIB device via a GUI. Then, using the right GUI class, `provided_devices` becomes available.\n
        A core layout for parsing information about GPIB devices is:\n
        *GPIB information transfer:* **{DESCRIPTOR:str, ADAPTER_TYPE:str}**\n
        Here `DESCRIPTOR` is the `pyvisa` assigned descriptor of a device, `ADAPTER_TYPE` is the type of adapter used, i.e. 'GPIB', 'AR488' pr 'RS232'.
    
        Attributes
        ----------
        inputs : list[str]
            A list of the names of the procedure parameter (name of the variable) that are supposed to be treated as input variables to the procedure from the pymeasure GUI.
        displays : list[str]
             A list of the names of the procedure parameter (name of the variable) that are supposed to be displayed in the pymeasure GUI.
        requested_devices : list[str]
            A list of names for devices that the procedure needs.
        default_devices : list[dict]]
            Default devices shown to the `DeviceManagerWidget` when no devices are provided externally. Each device in `requested_devices` needs a dictionary in this list, where the shape of the dictionary is the same as `GPIB information transfer` but only `DESCRIPTOR` and `ADAPTER_TYPE` are necessary.
        name : str
            Name of the measurement to be shown in the window title.
        tool_tip_information : dict
            Information about parameters shown in the `DeviceManagerWindow`. Variable names of the parameter in the class are the keys and the value is the information string to be displayed.
        provided_devices : list[dict]
            A list of dictionaries of information about the selected device, where each are of shape `GPIB information transfer` (see above). Will always contain DESCRIPTOR and ADAPTER_TYPE. Defaults to empty list.
        visa_path : str
            The path to the VISA library provided by the same object that defines `provided_devices`. Defaults to empty string if not provided.
        _possible_devices : list[dict]
            A list returned by a `find_devices` if procedure was opened via an `DeviceManagerWindow`. It contains all possible, known devices in form of dictionaries of shape `GPIB information transfer` (see above) which can be used to suggest devices to a user. `_possible_devices` can be used but is not required. Defaults to empty list.
    """
    # to declare
    inputs : list[str] = []             # declare explicitly in parent class!
    displays : list[str] = []           # declare explicitly in parent class!
    requested_devices : list[str]=[]    # declare explicitly in parent class if you want to get devices from a DeviceManagerWidget
    default_devices : list[dict] = {}   # declare explicitly in parent class if you want to show default devices in a DeviceManagerWidget
    tool_tip_information : dict = {}
    name : str = ""
    # to accept
    provided_devices : list[dict]=[]    # returned by the DeviceManagerWidget, has same length as requested_devices, is provide by the GIU class for the measurement
    visa_path : str = ""               # path to the VISA library provided by DeviceManagerWidget, can be empty string if not provided
    # not to be declared or accepted
    _possible_devices : list[dict]=[]   # parent class does not have to accept this, is provide by the GPIB Device Finder