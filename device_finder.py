# DEPRECATED!
# Main file
"""Main file for performing and accessing GUI based measurement with GPIB.\n
Uses the `GPIBDeviceFinderGUI` to find connected devices using the `FindDevices` procedures and allows users to open a measurement window using the `ProcedureManagerWidget` with options provided by the `supported_procedures.SupportedProcedureList`.\n
If you want to add your own procedure:\n
\t  1. Ensure your procedure uses the `procedures.DeviceProcedure` class as a child and declares `inputs` and `displays`.\n
\t  2. Make your own GUI or use one provided in `windows`. Ensure that the only explicit argument of the constructor is a `DeviceProcedure` parent class, i.e. your procedure from 1.\n
\t  3. Use the `GPIBDeviceFinderGUI` to open GPIB devices or load a list of known devices through the GUI and then open the requested procedure, `GPIBDeviceFinderGUI` will then provide your procedure with a list of known devices according to the `DeviceProcedure` class.
"""
# Standard libraries
import sys, os, warnings, tempfile
import logging
log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())
# External libraries
from pymeasure.display.Qt import QtCore, QtWidgets
from pymeasure.display.windows import ManagedWindowBase
from pymeasure.display.manager import Manager
from pymeasure.display.widgets import (
    BrowserWidget,
    InputsWidget,
    TableWidget,
    LogWidget,
    ResultsDialog,
    SequencerWidget,
    FileInputWidget,
)
from pymeasure.experiment import Parameter, ListParameter, BooleanParameter
from pymeasure.experiment import Procedure, Results, unique_filename
# Own libraries
from equipment_control import make_resourcemanager, DeviceManagerWindow, WindowSingleDock, DeviceProcedure
from equipment_control.device import find_devices, DESCRIPTOR, ADAPTER_TYPE, GPIB_ADDRESS, IDENTIFICATION, DIALECT
from Nova_SEM_IV import NovaSEM_IV
from Blue_Oxford_Kryo_control import BlueOxfordCryo_MagnetControl

### Manage supported procedures
class SupportedProcedure:
    """
    A container for supported measurement routines, i.e. procedures.\n
    Connects the procedure class with gui class, i.e. allows other programs to connect a window to a measurement.
    """
    name : str = "No name given"
    procedure_class : DeviceProcedure
    gui_class : DeviceManagerWindow
    def __init__(self, procedure_class : DeviceProcedure, gui_class : DeviceManagerWindow, name : str = ""):
        self.procedure_class = procedure_class
        if name == "":
            if hasattr(self.procedure_class, "name"):
                if self.procedure_class.name != "":
                    self.name = self.procedure_class.name
                else:
                    self.name = self.procedure_class.__name__
            else:
                self.name = self.procedure_class.__name__
        else:
            self.name = name
        self.gui_class = gui_class

SupportedProcedureList : list = [
    SupportedProcedure(NovaSEM_IV, WindowSingleDock),
    SupportedProcedure(BlueOxfordCryo_MagnetControl, WindowSingleDock),
]

### Procedure Manager
class ProcedureManagerWidget(QtWidgets.QWidget):
    """A widget to allow opening supported procedures that are stored in a list `SupportedProcedureList` as classes `SupportedProcedure`.\n
    Shows a list selection of procedures as well as a button to open the selected procedure.\n
    Supported procedures must provide a window (gui_class) and the procedure_class itself.
    """
    _parent : ManagedWindowBase # GPIBDeviceFinderGUI
    _procedures : list[SupportedProcedure] = []
    _selected_procedure : SupportedProcedure
    def __init__(self, parent, procedures : list[SupportedProcedure]=SupportedProcedureList):
        """A widget to open procedures in a window using the list of `SupportedProcedure` `procedures`.

        Args:
            parent (DeviceManagerWindow, optional): Parent window class must have function `get_known_devices` that returns the known devices. Defaults to None.
            procedures (list[SupportedProcedure], optional): A list of supported procedures, each element must contain the PyQt window `gui_class` to open the `procedure_class` in. Defaults to SupportedProcedureList.
        """
        super().__init__(parent)
        self._parent = parent
        self._procedures = procedures
        self._selected_procedure = procedures[0]
        self._setup_ui()
        self._layout()
        
    def _setup_ui(self):
        # Add drop-down list of supported procedures
        self.procedure_list = QtWidgets.QComboBox(self)
        self._get_procedures()
        self.procedure_list.activated.connect(self.get_selected_procedure)
        # Add button to open a procedure
        self.button = QtWidgets.QPushButton("Open measurement window")
        self.button.clicked.connect(self.open_procedure_window)

    def _layout(self):
        vbox = QtWidgets.QVBoxLayout(self)
        vbox.addWidget(QtWidgets.QLabel("List of supported measurement routines:"))
        vbox.addWidget(self.procedure_list)
        vbox.addWidget(self.button)

    def get_known_devices(self) -> list:
        possible_devices = []
        if hasattr(self._parent, "get_known_devices"):
            gui_devices : list = self._parent.get_known_devices()
            if len(gui_devices) > 0:
                for device in gui_devices:
                    # device_data is pandas DataFrame
                    device_data = device.to_dict(orient='records')
                    for device_info in device_data:
                        possible_devices.append(device_info)
        else:
            log = logging.getLogger()
            log.error(f"ProcedureManagerWidget:Parent window class {self._parent.__name__} has no function 'get_known_devices()->list', can not provide any devices.")
        return possible_devices
    
    # Actions for QtWidgets
    def _get_procedures(self):
        log = logging.getLogger()
        log.info("ProcedureManagerWidget:Loading supported procedures ...")
        if type(self._procedures) == list:
            for supported_procedure in self._procedures:
                try:
                    procedure_name = supported_procedure.name
                    self.procedure_list.addItem(procedure_name)
                except Exception as error:
                    log.error(f"ProcedureManagerWidget:An error occured when typing to add procedure '{supported_procedure}': {error}")
        else:
            log.error(f"ProcedureManagerWidget:procedures must be a list of SupportedProcedure")
        pass

    def get_selected_procedure(self, index:int):
        """Allows a QtWidget.QtComboBox to return a value at index `index`.

        Args:
            index (int): Index assigned by QtWidget.QtComboBox on selection.
        """
        self._selected_procedure : SupportedProcedure = self._procedures[index]
    
    def open_procedure_window(self):
        """Opens a new pymeasure GUI using the prebuilt SupportedProcedure class.
        """
        log = logging.getLogger()
        found = False
        for supported_procedure_index in range(0,len(self._procedures)):
            supported_procedure : SupportedProcedure = self._procedures[supported_procedure_index]
            if supported_procedure.name == self._selected_procedure.name:
                found = True
                procedure_class = supported_procedure.procedure_class
                if hasattr(procedure_class,'_possible_devices'):
                    procedure_class._possible_devices = self.get_known_devices()
                else:
                    log.warning(f"ProcedureManagerWidget:Selected procedure '{procedure_class.__name__}' has no attribute '_possible_devices', can not provide know devices to measurement routine!")
                gui_class = supported_procedure.gui_class
                window = gui_class(procedure_class)
                window.show()
        if not found:
            log.error(f"ProcedureManagerWidget:Could not open {self._selected_procedure.name}, is not supported!")

### GPIB Device Finder 
class FindDevices(Procedure):
    """A procedure that uses `pyvisa` and `pymeasure` to find connected GPIB devices and lists their properties.
    """
    use_custom_visalib = BooleanParameter('Use custom VISA library', default=False)
    visalib = Parameter('Path to VISA library', default="@py", group_by='use_custom_visalib', group_condition=True)
    inputs = ["use_custom_visalib","visalib"]
    
    DATA_COLUMNS = [DESCRIPTOR, ADAPTER_TYPE, GPIB_ADDRESS, DIALECT, IDENTIFICATION]

    def startup(self):
        log = logging.getLogger()
        log.info("FindDevices:Successfully loaded FindDevices!")

    def execute(self):
        log = logging.getLogger()
        log.info("FindDevices:Searching for devices ...")
        if self.use_custom_visalib:
            manager = make_resourcemanager(custom_visalib_path=self.visalib)
        else:
            manager = make_resourcemanager()

        data = find_devices(manager=manager)
        num_resources = len(data)

        if num_resources > 0:
            for resource_idx in range(0,num_resources):
                self.emit('results', data[resource_idx])
                self.emit('progress',round(resource_idx/num_resources*100))
            return
        else:
            log.error("FindDevices:No devices found!")
            self.emit('progress',100)
            return
    
### GPIB Device Finder GUI
class GPIBDeviceFinderGUI(ManagedWindowBase):
    """A `pymeasure` `ManagedWindowBase` class that additionally allows users to open supported procedures / measurements in the GUI with one button click.
    """
    temporary_files = []
    saved_files = []
    supported_procedures : list[SupportedProcedure]
    use_procedure_manager : bool = True
    def __init__(self,
                 supported_procedures : list[SupportedProcedure] = SupportedProcedureList,
                 TableWidgetArgs : dict = {}, 
                 LogWidgetArgs : dict = {},
                 log : logging.Logger = logging.getLogger()):
        self.procedure = FindDevices
        self.inputs = self.procedure.inputs
        self.supported_procedures = supported_procedures
        
        self.log_widget = LogWidget(name="Log", **LogWidgetArgs)
        self.device_table = TableWidget(name="Devices", columns=self.procedure.DATA_COLUMNS, by_column=False, **TableWidgetArgs)
        
        widget_list = (self.device_table, self.log_widget)
        super().__init__(procedure_class=self.procedure,
                         inputs=self.inputs,
                         displays=self.inputs,
                         widget_list=widget_list,
                         sequencer=True,
                         sequencer_inputs=self.inputs,
                         enable_file_input=True)
        
        if self.enable_file_input:
            self.file_input.filename_input.setText("GPIB_devices_{date}")
            
        self.store_measurement = False
        self.use_procedure_manager = True
        
        log.addHandler(self.log_widget.handler)
        log.setLevel(self.log_level)
        log.info("GPIBDeviceFinderGUI connected to logging.")
        self.setWindowTitle("GPIB Device Finder")
    
    # Overload ManagedWindowBase functions
    def _setup_ui(self):

        self.queue_button = QtWidgets.QPushButton('Find devices', self)
        self.queue_button.clicked.connect(self._queue)

        self.abort_button = QtWidgets.QPushButton('Abort', self)
        self.abort_button.setEnabled(False)
        self.abort_button.clicked.connect(self.abort)

        self.browser_widget = BrowserWidget(
            self.procedure_class,
            self.displays,
            [],  # This value will be patched by subclasses, if needed
            parent=self
        )
        self.browser_widget.show_button.clicked.connect(self.show_experiments)
        self.browser_widget.hide_button.clicked.connect(self.hide_experiments)
        self.browser_widget.clear_button.clicked.connect(self.clear_experiments)
        self.browser_widget.open_button.clicked.connect(self.open_experiment)
        self.browser = self.browser_widget.browser

        self.browser.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.browser.customContextMenuRequested.connect(self.browser_item_menu)
        self.browser.itemChanged.connect(self.browser_item_changed)

        self.inputs = InputsWidget(
            self.procedure_class,
            self.inputs,
            parent=self,
            hide_groups=self.hide_groups,
            inputs_in_scrollarea=self.inputs_in_scrollarea,
        )
        if self.enable_file_input:
            self.file_input = FileInputWidget(parent=self)
        
        if self.use_procedure_manager:
            self.procedure_manager = ProcedureManagerWidget(parent=self, procedures=self.supported_procedures)
        
        self.manager = Manager(self.widget_list,
                               self.browser,
                               log_level=self.log_level,
                               parent=self)
        self.manager.abort_returned.connect(self.abort_returned)
        self.manager.queued.connect(self.queued)
        self.manager.running.connect(self.running)
        self.manager.finished.connect(self.finished)
        self.manager.log.connect(self.log.handle)

        if self.use_sequencer:
            self.sequencer = SequencerWidget(
                self.sequencer_inputs,
                self.sequence_file,
                parent=self
            )

    def _layout(self):
        self.main = QtWidgets.QWidget(self)

        inputs_dock = QtWidgets.QWidget(self)
        inputs_vbox = QtWidgets.QVBoxLayout(self.main)

        queue_abort_hbox = QtWidgets.QHBoxLayout()
        queue_abort_hbox.setSpacing(10)
        queue_abort_hbox.setContentsMargins(-1, 6, -1, 6)
        queue_abort_hbox.addWidget(self.queue_button)
        queue_abort_hbox.addWidget(self.abort_button)
        queue_abort_hbox.addStretch()

        inputs_vbox.addWidget(self.inputs)
        inputs_vbox.addSpacing(15)
        if self.enable_file_input:
            inputs_vbox.addWidget(self.file_input)
            inputs_vbox.addSpacing(15)

        inputs_vbox.addLayout(queue_abort_hbox)

        inputs_vbox.addStretch(0)
        inputs_dock.setLayout(inputs_vbox)

        dock = QtWidgets.QDockWidget('Device Parameters')
        dock.setWidget(inputs_dock)
        dock.setFeatures(QtWidgets.QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        self.addDockWidget(QtCore.Qt.DockWidgetArea.LeftDockWidgetArea, dock)

        if self.use_procedure_manager:
            procedure_manager_dock = QtWidgets.QDockWidget('Procedure Manager')
            procedure_manager_dock.setWidget(self.procedure_manager)
            procedure_manager_dock.setFeatures(QtWidgets.QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
            self.addDockWidget(QtCore.Qt.DockWidgetArea.LeftDockWidgetArea, procedure_manager_dock)
        
        if self.use_sequencer:
            sequencer_dock = QtWidgets.QDockWidget('Sequencer')
            sequencer_dock.setWidget(self.sequencer)
            sequencer_dock.setFeatures(QtWidgets.QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
            self.addDockWidget(QtCore.Qt.DockWidgetArea.LeftDockWidgetArea, sequencer_dock)

        self.tabs = QtWidgets.QTabWidget(self.main)
        for wdg in self.widget_list:
            self.tabs.addTab(wdg, wdg.name)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        splitter.addWidget(self.tabs)
        splitter.addWidget(self.browser_widget)

        vbox = QtWidgets.QVBoxLayout(self.main)
        vbox.setSpacing(0)
        vbox.addWidget(splitter)

        self.main.setLayout(vbox)
        self.setCentralWidget(self.main)
        self.main.show()
        self.resize(1000, 800)
    
    def queue(self, procedure=None):
        # Check if the filename and the directory inputs are available
        if not self.enable_file_input:
            raise NotImplementedError("Queue method must be overwritten if the filename- and "
                                      "directory-inputs are disabled.")

        if procedure is None:
            procedure = self.make_procedure()

        if self.store_measurement:
            try:
                filename = unique_filename(
                    self.directory,
                    prefix=self.file_input.filename_base,
                    datetimeformat="",
                    procedure=procedure,
                    ext=self.file_input.filename_extension,
                )
                self.saved_files.append(filename)
            except KeyError as E:
                if not E.args[0].startswith("The following placeholder-keys are not valid:"):
                    raise E from None
                log.error(f"Invalid filename provided: {E.args[0]}")
                return
        else:
            filename = tempfile.mktemp(prefix='GPIB_devices_tempfile_', suffix='.csv')
            self.temporary_files.append(filename)

        results = Results(procedure, filename)

        experiment = self.new_experiment(results)
        self.manager.queue(experiment)
    
    def open_experiment(self): # like the normal implementation, but save file in self.saved_files
        dialog = ResultsDialog(self.procedure_class,
                               widget_list=self.widget_list)
        if dialog.exec():
            filenames = dialog.selectedFiles()
            for filename in map(str, filenames):
                if filename in self.manager.experiments:
                    QtWidgets.QMessageBox.warning(
                        self, "Load Error",
                        "The file %s cannot be opened twice." % os.path.basename(filename)
                    )
                elif filename == '':
                    return
                else:
                    self.saved_files.append(filename) # Additional to normal function
                    results = Results.load(filename)
                    experiment = self.new_experiment(results) 
                    for curve in experiment.curve_list:
                        if curve:
                            curve.update_data()
                    experiment.browser_item.progressbar.setValue(100)
                    self.manager.load(experiment)
                    log = logging.getLogger()
                    log.info('Opened data file %s' % filename)
    
    def quit(self, evt=None):
        if self.manager.is_running():
            self.abort()
        for file in self.temporary_files:
            try:
                os.remove(file)
            except Exception as error:
                log = logging.getLogger()
                log.error(f"GPIBDeviceFinderGUI:Could not remove temporary file '{file}' upon closing window due to an exception: {error}")
                warnings.warn(f"GPIBDeviceFinderGUI:Could not remove temporary file '{file}' upon closing window due to an exception: {error}")
        
        self.close()
    
    # Additional function that allows user to open a procedure in the GUI
    def get_known_devices(self) -> list:
        """Finds all known devices from this session including all devices from loaded savefiles.

        Returns:
            list[pd.DataFrame]: List of pandas dataframes as given by the `pymeasure` Results class.
        """
        log = logging.getLogger()
        raw_device_data = []
        if len(self.saved_files) > 0 or len(self.temporary_files) > 0:
            for device_file_name in self.saved_files:
                log.info(f"GPIBDeviceFinderGUI:Opening {device_file_name} and extracting GPIB devices...")
                results = Results.load(device_file_name)
                raw_device_data.append(results.data)
            for device_file_name in self.temporary_files:
                log.info(f"GPIBDeviceFinderGUI:Opening {device_file_name} and extracting GPIB devices...")
                results = Results.load(device_file_name)
                raw_device_data.append(results.data)
        else:
            log.info(f"GPIBDeviceFinderGUI:Could not find any known devices, please search for devices first or use manual input.")
        return raw_device_data
    
if __name__ == "__main__":
    # try:
    #     pyqtgraph.setConfigOption("useOpenGL", True)
    # except Exception as error:
    #     log.warning(f"Can not use OpenGL due to an exception: {error}")
    app = QtWidgets.QApplication(sys.argv)
    window = GPIBDeviceFinderGUI()
    window.show()
    app.exec()