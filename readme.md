# <p style="text-align: center;"> Equipment-control </br>

#### A custom backed for communicating with devices which incorporates support for the AR488 adapter. Based on the pymeasure <em>Procedure</em> and <em>ManagedWindowBase</em> with additional GUI elements allowing for device selection and forwarding to a <em>Procedure</em>.

### Installation
Install the VISA drivers (see instructions in `gpib-installation`).<br>
Install Python 3.12.3 or newer (`$ python` or `$ python3` in the console).
- Check the version with `$ python3 -V`
- If the version is incorrect then use the path to the executable (where you installed python)
- Ideally make a virtual environment with `$ python3 -m venv *name of the environment*`
- Activate the environment with:
  1. Linux: `$ source *name of the environment*/bin/activate`
  2. Windows: `$ *name of the environment*\Scripts\Activate.ps1` you might need to allow scripts to run for this `$ Set-ExecutionPolicy Unrestricted -Scope Process`
- Update pip with `$ python3 -m pip install --upgrade pip`

Installing the project with measurement procedures:
- clone the repo with `$ git clone https://github.com/aghuth/equipment_control` or download the files
- enter the downloaded folder
- install build tools `$ python3 -m pip install --upgrade build`
- build the project with `$ python3 -m build`
- install the project with `$ python3 -m pip install ./`

To install only the project: `$ python3 -m pip install git+https://github.com/aghuth/equipment_control`.

Ensure you have the rights to access serial ports on your operating system.<br>
On linux ensure that libxcb-cursor0 is installed.

### How to use
This projects measurement routines are based on pymeasure's procedures. To write a measurement do as described in their documentation https://pymeasure.readthedocs.io/en/latest/tutorial/procedure.html#using-procedures, <strong>BUT</strong> to use this projects benefits replace the following:
- `Procedure` --> `DeviceProcedure` for the measurement procedure
- `ManagedWindowBase` --> `DeviceManagerWindow` for the GUI class (existing ones are in `windows.py`)
- `inputs` and `displays` are now defined inside the procedure!
- DeviceProcedures can request devices with `request_devices` and give default devices as `default_devices` to the GUI
- DeviceProcedures can ask a DeviceManagerWindow to show tool-tips for parameters with the `tool_tip_information` dict

For an example on how to use the features of this project follow the example in `example.py` or take a look at the real procedures below.

### Procedures
- #### Nova_SEM_IV.py
    <p>Procedure to measure current-voltage characteristics on the Nova SEM using the Keithley 2400 sourcementer and Agilent 34420A voltmeter. 2-probe and 4-probe are possible as well as measuring U(I) and I(U).</p>
- #### Blue_Oxford_Kryo_control.py
    <p>Procedure to measure current-voltage characteristics and control the magnet for the blue oxford cryostat. Possible are 2-probe and 4-probe U(I), I(U) and their magnetic field dependence. Reading the temperature is also implemented allowing for a U(T) measurement.</p>

### Contents
device.py
------------------------------------------------------------
<p><strong><em>DESCRIPTOR, ADAPTER_TYPE, GPIB_ADDRESS and IDENTIFICATION</strong></em><br>
Magic variables representing strings for dictionaries that are supposed to transmit information about a device, they are "Descriptor", "Adapter Type", "GPIB Address" and "Identification" respectively.</p>

<p><strong><em>ADAPTER_COMMUNICATION</strong></em><br>
A dictionary that is used by find_devices and reset_all_connected_devices to do basic communication with devices. The keys are names of dialects (i.e. 'SCPI', etc...) that are displayed in the log. The values are a tuple of (VISAAdapter arguments, identification command, reset command) where <em>VISAAdapter arguments</em> is a dict for the Device class (empty if not needed) and <em>identification command</em> and <em>reset command</em> can be None or "" if not supported by the device dialect.

<p><strong><em>Device</strong></em><br>
A class that creates a pyvisa adapter based on the user input of the adapter type. Supported are 'GPIB', 'AR488' and 'RS232'. The Device.adapter is then an abstraction for the actual low level implementation by pyvisa or the AR488Adapter from ar488.py. This class is necessary as pyvisa has no native support for AR488 adapters only serial (RS232) and GPIB (using a VISA library like NI-VISA).</p>

<p><strong><em>make_resourcemanager</strong></em><br>
Makes a pyvisa resource manager. Abstraction for the native pyvisa implementation with no further changes.</p>

<p><strong><em>valid_connector</strong></em><br>
A function that evaluates if a descriptor of an instrument for a given pyvisa resource manager is supported by the Device class. Returns the adapter type and some information to be displayed in logs.</p>

<p><strong><em>find_devices</strong></em><br>
A function that uses pyvisa to find connected devices and filters them based on a list of excluded strings. For each descriptor that is not excluded find_devices will spawn a new thread executing an instance of analyse_port.</p>

<p><strong><em>analyse_port</strong></em><br>
A function that analyses a given descriptor and manager combination to evaluate if the resource is supported by Device and find further information for that class.</p>

<p><strong><em>reset_all_connected_devices</strong></em><br>
Uses find_devices to search all connected devices and clears them uses the reset command from ADAPTER_COMMUNICATION if available but always clears using Device.clear().</p>

<p><strong><em>DeviceProcedure</strong></em><br>
An implementation of the pymeasure 'Procedure' class with additional variables that allow for requesting and accepting certain devices. By adding a device in 'requested_devices' using a simple name string a 'DeviceManagerWindow' that opens this procedure will be able to parse a device into 'provided_devices' at the same index. Each entry is the a dictionary of shape {DESCRIPTOR:str, ADAPTER_TYPE:str} which can then be parsed into a Device class that creates an adapter. This adapter can be used for direct communication (via 'write' and 'ask'=query) or it can be used to open a pymeasure instrument class based on the device used.</p>

display.py
------------------------------------------------------------
<p><strong><em>VISAPathManagerWidget</strong></em><br>
A simple PyQt widget that allows for the input of a custom VISA path, can be read using the 'get_visa_path' function.</p>

<p><strong><em>DeviceManagerWidget</strong></em><br>
A PyQt widget that allows a user to select an instrument based on a selection of adapter types and a pyvisa descriptor. If connected devices are known they can be displayed by unselecting the checkbox, then a list of known descriptors is presented. Selecting a descriptor and adapter type in the latter mode will also display an information string. Information can be returned with 'get_selected_device' as a dictionary of the above mentioned magic variables.</p>

<p><strong><em>HelpWindow</strong></em><br>
A simple PyQt window that shows the docstring of a procedure as a text.</p>

<p><strong><em>DeviceControlWindow</strong></em><br>
A PyQt window that presents a list of DeviceManagerWidgets for each device in the procedures 'requested_devices' list. Also shown is a VISAPathManagerWidget and two buttons one for finding devices using 'find_devices' and one for resetting devices using 'reset_all_connected_devices'.</p>

<p><strong><em>DeviceManagerWindow</strong></em><br>
An implementation of pymeasures 'ManagedWindowBase' that allows to show a DeviceControlWindow and HelpWindow. Has to be opened with 'procedure_class' as an instance of a DeviceProcedure. When queuing a measurement this class will transfer the VISA path and set of provided_devices from the VISAPathManagerWidget and DeviceManagerWidgets to the DeviceProcedure.</p>

windows.py:
------------------------------------------------------------
<p><strong><em>WindowSingleDock</strong></em><br>
A window based on the 'DeviceManagerWindow' with one dock widget (plot), log and table.</p>

ar488.py:
---------
<p><strong><em>AR488</strong></em><br>
A class that allows for easier usage of an AR488 adapter. Most commands are implemented as properties and methods.</p> 

<p><strong><em>AR488Adapter</strong></em><br>
A custom version of the pyvisa 'VISAAdapter' for the AR488 that behaves similarly to a GPIB or serial adapter with 'write' and 'read' being overwritten to allow for the usage of the AR488 in controller and device mode.</p>

### Known Issues
- Oxford Instruments devices do not work on linux-gpib with PyVISA-py, a fix is available: https://github.com/pyvisa/pyvisa-py/pull/597 and being implemented into PyVISA-py. No issues with the NI drivers on windows.
- PySide6 throws an error when closing a window that has an estimator widget, says that "QThread: Destroyed while thread 'Estimator-Thread (cant be closed properly with PySide6)' is still running". Is not an issue for measurements.
- The pymeasure dock widget (and plot widget) implementation with qtgraph sometimes fails to render a measurement with a numpy error hinting at failing to convert a datapoint to a meaningful value, the entire application has to be restarted to solve this issue. This is purely a rendering problem and does not affect any running measurement, simply re-open the measurement when it is finished with a freshly started GUI. Parameters can then be re-applied for the next measurement.
- OpenGL has issues on updating a pymeasure plot, also hinting at the painter, crashes on measurements. Can be avoided by not using OpenGL.