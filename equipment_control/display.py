"""A header file that overhauls the default `pymeasure` gui by adding control over devices and their adapters (GPIB / AR488 / RS232). Adds the `DeviceManagerWindow` as a replacement for the `pymeasure.display.windows.ManagedWindowBase`.
"""
import logging, tempfile, threading
from pymeasure.experiment import (
    Results,
    unique_filename,
    IntegerParameter,
    FloatParameter,
    Parameter,
    ListParameter,
    BooleanParameter
)
from pymeasure.display.Qt import QtCore, QtWidgets
from pymeasure.display.windows import ManagedWindowBase
from pymeasure.display.manager import Manager
from pymeasure.display.widgets import (
    BrowserWidget,
    InputsWidget,
    SequencerWidget,
    FileInputWidget,
    EstimatorWidget,
)

from .device import DESCRIPTOR, ADAPTER_TYPE, IDENTIFICATION, DeviceProcedure, make_resourcemanager, find_devices, reset_all_connected_devices

### Widgets
class VISAPathManagerWidget(QtWidgets.QWidget):
    """A `PyQt5` widget to allow for selecting a custom VISA library using the `get_visa_path` function.

    Attributes
    ----------
    visa_path : str
        The VISA path input by the user. Defaults to '@py' if selected.
    
    Methods
    ----------
    get_visa_path() -> str
        Returns the string written by the user in the input box.
    """
    visa_path : str = "@py"
    use_custom_visa : bool = False
    def __init__(self, parent):
        """A `PyQt5` widget to allow for selecting a custom VISA library using the `get_visa_path` function.

        Args:
            parent (_type_, optional): Parent `PyQt5` window class. Defaults to None.
        """
        super().__init__(parent)
        self._setup_ui()
        self._layout()
    
    def _setup_ui(self):
        ### Handle VISA input by user
        self.use_custom_visa_widget = QtWidgets.QCheckBox("Use custom VISA library", self)
        self.use_custom_visa_widget.clicked.connect(self._change_use_custom_visa)
        self.use_custom_visa_widget.setToolTip("Decide if pyvisa should automatically select the VISA library or use a manual input.")
        # Add input box for visa path
        self.custom_visa_path_textbox_label = QtWidgets.QLabel("Path to VISA library:",self)
        self.custom_visa_path_textbox = QtWidgets.QLineEdit(self)
        self.custom_visa_path_textbox.setText(str(self.visa_path))
        self.custom_visa_path_textbox.setToolTip("Path to the VISA library or a pyvisa recognised string. Default is '@py'.")
        
    def _layout(self):
        vbox = QtWidgets.QVBoxLayout(self)
        # manual VISA selector
        vbox.addWidget(self.use_custom_visa_widget)
        # VISA path textbox
        vbox.addWidget(self.custom_visa_path_textbox_label)
        vbox.addWidget(self.custom_visa_path_textbox)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Minimum,QtWidgets.QSizePolicy.Policy.Maximum)
        self._update_custom_visa_textbox()
        
    # VISA path options
    def _change_use_custom_visa(self):
        self.use_custom_visa = not self.use_custom_visa
        self._update_custom_visa_textbox()
    
    def _update_custom_visa_textbox(self):
        if self.use_custom_visa:
            self.custom_visa_path_textbox_label.show()
            self.custom_visa_path_textbox.show()
        else:
            self.custom_visa_path_textbox_label.hide()
            self.custom_visa_path_textbox.hide()
    
    # Output of the VISAPathManagerWidget has to be called by the parent to take effect
    def get_visa_path(self) -> str:
        """Get the path to the VISA library.

        Returns:
            str: The VISA path input by the user or empty string if not selected. Defaults to '@py'.
        """
        visapath = ''
        if self.use_custom_visa:
            self.visa_path = self.custom_visa_path_textbox.text()
            visapath = self.visa_path
        return visapath
              
class DeviceManagerWidget(QtWidgets.QWidget):
    """A `PyQt5` widget to allow for selecting known devices using the `get_selected_device` function.

    Attributes
    ----------
    possible_devices : list[dict]
        The list of device information given on startup or before updating the QWidget or before executing `update_descriptors()`.
    descriptor : str
        The selected descriptor of a device. Defaults to "GPIB0::10::INSTR".
    adapter_type : str
        The selected adapter type, is always an element of `possible_adapter_types`. Defaults to "GPIB".
    possible_adapter_types : list[str]
        A list of possible adapter types for the user to select from.
    
    Methods
    ---------
    get_selected_device() -> dict
        Returns to information about the currently selected device in a dictionary, always contains {DESCRIPTOR:str, ADAPTER_TYPE:str}.
    update_descriptors() -> None
        Updates the widgets content based on the `possible_devices` list. Update `possible_devices` before executing.
    """
    _parent : ManagedWindowBase # a ManagedWindowBase parent class
    # from parent class provided
    possible_devices : list[dict]
    show_automatic_options : bool = False
    # attributes to be accessed by parent class
    descriptor : str = "GPIB0::1::INSTR"
    adapter_type : str = "GPIB"
    # internal
    # possible device options
    possible_adapter_types : list[str] = ["GPIB", "AR488", "RS232"]
    _possible_descriptors : list[str] = []
    
    def __init__(self, parent, possible_devices : list[dict], default_information : dict|None = None):
        """A `PyQt5` widget to allow for selecting known devices using the `get_selected_device` function.

        Args:
            parent (ManagedWindowBase): The parent `PyQt5` window class.
            possible_devices (list[dict]): A list of possible devices for the user to select from, each element is a dictionary that has to at least include the keys ADAPTER_TYPE and DESCRIPTOR. Where ADAPTER_TYPE must be in `possible_adapter_types`. An empty list will not allow the user to select anything and must use manual input text boxes.
        """
        super().__init__(parent)
        self._parent = parent
        self.possible_devices = possible_devices
        self.get_possible_devices(default_devices=default_information)
        self._setup_ui()
        self._layout()
    
    # Get devices provided by parent class
    def get_possible_devices(self, default_devices : dict|None):
        for device in self.possible_devices:
            # Must follow the nomenclature of "FindDevices" procedure from GPIB Device Finder
            descriptor = device[DESCRIPTOR]
            if descriptor not in self._possible_descriptors:
                self._possible_descriptors.append(descriptor)
                
        if default_devices is not None:
            self.descriptor = default_devices[DESCRIPTOR]    
            self.adapter_type = default_devices[ADAPTER_TYPE]

        if len(self.possible_devices) > 0:
            self.show_automatic_options = True
        else:
            self.show_automatic_options = False
    
    # Define the GUI layout of this widget
    def _setup_ui(self):
        ### Handle device parameters
        self.manual_device_selection_widget = QtWidgets.QCheckBox()
        self.manual_device_selection_widget.click()
        self.manual_device_selection_widget.clicked.connect(self.change_show_automatic_options)
        self.manual_device_selection_widget.setToolTip("Show options for already detected devices or use a manual text-based input.")
        # Add descriptor
        self.manual_descriptor_widget = QtWidgets.QLineEdit()
        self.manual_descriptor_widget.setText(str(self.descriptor))
        self.manual_descriptor_widget.setToolTip("Descriptor of the adapter used, has to be in a format recognised by your VISA library.")
        # Add a box with information about the selected device if devices are parsed
        self.automatic_device_info_widget = QtWidgets.QLineEdit()
        self.automatic_device_info_widget.setReadOnly(True)
        self.automatic_device_info_widget.setToolTip("Identification found by SCPI '*idn?' command or 'Not known' if not obtainable.")
        # Add adapter types
        self.adapter_type_widget = QtWidgets.QComboBox()
        for adapter_type in self.possible_adapter_types:
            self.adapter_type_widget.addItem(str(adapter_type))
        self.adapter_type_widget.activated.connect(self._get_adapter_type)
        # Add gpib address and descriptor
        self.automatic_descriptor_widget = QtWidgets.QComboBox()
        self.update_descriptors()
        self.automatic_descriptor_widget.activated.connect(self._get_descriptor_automatic)
        self.automatic_gpib_address_widget = QtWidgets.QComboBox()
    
    def _layout(self):
        main_layout = QtWidgets.QVBoxLayout()
        self.manual_frame = QtWidgets.QFrame()
        self.automatic_frame = QtWidgets.QFrame()
        manual_vbox = QtWidgets.QVBoxLayout()
        automatic_vbox = QtWidgets.QVBoxLayout()
        selector_layout = QtWidgets.QHBoxLayout()
        adapter_type_layout = QtWidgets.QVBoxLayout()
        manual_device_selection_layout = QtWidgets.QVBoxLayout()

        # manual device selector
        manual_device_selection_layout.addWidget(QtWidgets.QLabel("M:"))
        # self.manual_device_selection_widget.setFixedWidth(15)
        manual_device_selection_layout.addWidget(self.manual_device_selection_widget)
        manual_device_selection_layout.setContentsMargins(0, 4, 0, 0)

        adapter_type_layout.addWidget(QtWidgets.QLabel("Adapter:"))
        # self.adapter_type_widget.setFixedWidth(65)
        adapter_type_layout.addWidget(self.adapter_type_widget)
        adapter_type_layout.setContentsMargins(0, 10, 0, 0)

        manual_vbox.addWidget(QtWidgets.QLabel("Descriptor:"))
        # self.manual_descriptor_widget.setFixedWidth(200)
        manual_vbox.addWidget(self.manual_descriptor_widget)
        manual_vbox.setContentsMargins(0, 10, 0, 0)

        automatic_vbox.addWidget(QtWidgets.QLabel("Descriptor:"))
        # self.automatic_descriptor_widget.setFixedWidth(200)
        automatic_vbox.addWidget(self.automatic_descriptor_widget)
        automatic_vbox.setContentsMargins(0, 10, 0, 0)

        self.manual_frame.setLayout(manual_vbox)
        self.automatic_frame.setLayout(automatic_vbox)

        selector_layout.addLayout(manual_device_selection_layout)
        selector_layout.addLayout(adapter_type_layout)
        selector_layout.addWidget(self.manual_frame)
        selector_layout.addWidget(self.automatic_frame)
        selector_layout.setAlignment(self,QtCore.Qt.AlignTop)

        main_layout.addLayout(selector_layout)
        # self.automatic_device_info_widget.setFixedWidth(290)
        main_layout.addWidget(self.automatic_device_info_widget)

        main_layout.setContentsMargins(-1, 1, -1, 1)

        self.setLayout(main_layout)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Minimum,QtWidgets.QSizePolicy.Policy.Maximum)

        # Update SelectBoxes on startup
        self._update_manual_device_input_options()
        self._get_adapter_type(None)
        self._get_descriptor_automatic(None)
        self._update_selected_device_info()

    # Widget actions to update attributes used by parent class
    ## manual readout necessary upon piping the device information
    def _get_descriptor_manual(self):
        self.descriptor = self.manual_descriptor_widget.text()
    ## automatic readout
    def _get_descriptor_automatic(self, index : int|None = None):
        if self.show_automatic_options:
            if len(self._possible_descriptors) > 0:
                if index is None:
                    self.descriptor = self._possible_descriptors[self.automatic_descriptor_widget.currentIndex()]
                else:
                    if index in range(0,len(self._possible_descriptors)):
                        self.descriptor = self._possible_descriptors[index]
        self._update_selected_device_info()
    
    def _get_adapter_type(self, index : int|None = None):
        if index is None and self.adapter_type_widget.count() > 0:
            self.adapter_type = self.possible_adapter_types[self.adapter_type_widget.currentIndex()]
        else:
            if index in range(0,len(self.possible_adapter_types)):
                self.adapter_type = self.possible_adapter_types[index]
        self._get_descriptor_automatic()
        self._update_selected_device_info()
    
    ### Updates
    def update_descriptors(self):
        for old_entry in self._possible_descriptors:
            index = self.automatic_descriptor_widget.findText(old_entry)
            self.automatic_descriptor_widget.removeItem(index)
        self._possible_descriptors = []
        for device in self.possible_devices:
            # Must follow the nomenclature of "FindDevices" procedure from GPIB Device Finder
            descriptor = device[DESCRIPTOR]
            self._possible_descriptors.append(descriptor)
            self.automatic_descriptor_widget.addItem(descriptor)

    def _update_selected_device_info(self):
        if self.show_automatic_options:
            information_shown = "Unknown device"
            possible_matches_adapter= []
            possible_matches_descriptor = []
            for device_idx in range(0,len(self.possible_devices)):
                device = self.possible_devices[device_idx]
                device_infos = device.items()
                for device_info_item in device_infos:
                    if self.descriptor in device_info_item:
                        possible_matches_descriptor.append(device_idx)
                    if self.adapter_type in device_info_item:
                        possible_matches_adapter.append(device_idx)
            
            for match_idx in possible_matches_adapter:
                if match_idx in possible_matches_descriptor:
                    ident = self.possible_devices[match_idx][IDENTIFICATION]
                    info_str = str(ident)
                    information_shown = info_str
            self.automatic_device_info_widget.setText(information_shown)
                
    # Widget actions to update the layout
    def change_show_automatic_options(self):
        self.show_automatic_options = not self.manual_device_selection_widget.isChecked()
        self._update_manual_device_input_options()
        self._get_descriptor_automatic()
        self._update_selected_device_info()
    
    def _update_manual_device_input_options(self):
        if self.show_automatic_options:
            self.show_automatic_options = True
            self.manual_frame.hide()
            self.automatic_frame.show()
            self.automatic_device_info_widget.show()
            self._update_selected_device_info()
        else:
            self.manual_frame.show()
            self.automatic_frame.hide()
            self.automatic_device_info_widget.hide()
    
    # Output of the DeviceManagerWidget has to be called by the parent to take effect
    def get_selected_device(self) -> dict:
        """Returns the selected device information in a dictionary.

        Returns:
            dict: Contains {DESCRIPTOR:str, ADAPTER_TYPE:str}.
        """
        self._get_adapter_type(None)
        if self.show_automatic_options:
            self._get_descriptor_automatic(None)
        else:
            self._get_descriptor_manual()
            
        return_dict = {
            DESCRIPTOR : self.descriptor,
            ADAPTER_TYPE : self.adapter_type,
        }
        return return_dict

class HelpWindow(QtWidgets.QWidget):
    """A window displaying additional information about a procedure through its docstring.
    """
    def __init__(self, parent, window_title:str, formated_text:str, markdown:bool=False, html:bool=False,**QTextEdit_kwargs):
        QtWidgets.QWidget.__init__(self)
        self.setWindowTitle(window_title)
        layout = QtWidgets.QGridLayout()
        self.setLayout(layout)
        textbox = QtWidgets.QTextEdit(parent=self,**QTextEdit_kwargs)
        if markdown:
            textbox.setMarkdown(formated_text)
        elif html:
            textbox.setHtml(formated_text)
        else:
            textbox.setText(formated_text)
        layout.addWidget(textbox, 0, 0)
    

class DeviceControlWindow(QtWidgets.QWidget):
    """A window allowing for control of connected devices through a procedure.\n
    Abilities are:
    - Finding devices
    - Resetting devices
    - Managing the VISA library to be used through the `VISAPathManagerWidget`
    - Selecting devices through the `DeviceManagerWidget` for each requested device by the procedure.
    """
    _provide_devices = False
    multithreading = False
    def __init__(self, parent, procedure_class:DeviceProcedure, procedure_title:str):
        QtWidgets.QWidget.__init__(self)
        self.setWindowTitle(procedure_title)
        self.procedure_class = procedure_class
        self._setup_ui()
        self._layout()

    def _setup_ui(self):
        log = logging.getLogger()
        #   Button to enable multithreaded device search
        self.fast_search_button = QtWidgets.QCheckBox('Parallel search', self)
        self.fast_search_button.setToolTip("Use multithreading to scan independent adapters faster, can cause issues when multiple devices are connected over the same bus.")
        #   Button to find devices
        self.probe_device_button = QtWidgets.QPushButton('Find devices', self)
        self.probe_device_button.clicked.connect(self._probe_devices)
        self.probe_device_button.setToolTip("Probe for connected devices and update the device selection below.")
        #   Button to reset devices
        self.reset_device_button = QtWidgets.QPushButton('Reset devices', self)
        self.reset_device_button.clicked.connect(self._reset_devices)
        self.reset_device_button.setToolTip("Resets all connected devices. Do not run during measurements or when others are using some connected devices! Might be necessary if a device hangs or responds with faulty answers.")
        #   Widget to input a visa path
        self.visa_manager = VISAPathManagerWidget(parent=self)
        #   Widgets to input information about connected devices
        if hasattr(self.procedure_class, "requested_devices") and hasattr(self.procedure_class, "_possible_devices") and hasattr(self.procedure_class, "provided_devices"):
            self._provide_devices = True
            self.device_manager = []
            if hasattr(self.procedure_class, "default_devices") and len(self.procedure_class.default_devices)==len(self.procedure_class.requested_devices):
                for requested_index in range(0,len(self.procedure_class.requested_devices)):
                    self.device_manager.append(DeviceManagerWidget(parent=self, possible_devices=self.procedure_class._possible_devices, default_information=self.procedure_class.default_devices[requested_index]))  
            else:
                log.debug("DeviceControlWindow:Procedure has not defined enough default devices.")
                for requested_index in range(0,len(self.procedure_class.requested_devices)):
                    self.device_manager.append(DeviceManagerWidget(parent=self, possible_devices=self.procedure_class._possible_devices))  
        else:
            log.error(f"DeviceControlWindow:Procedure class {self.procedure_class.__name__} is not a valid DeviceProcedure, could not provide any devices, please ensure that the procedure class has attributes 'requested_devices', '_possible_devices' and 'provided_devices'!")
        ###
    
    def _layout(self):
        #   Buttons to show a help window and for probing devices
        main_layout = QtWidgets.QVBoxLayout(self)
        if self._provide_devices or self._provide_devices:
            button_box = QtWidgets.QWidget(self)
            info_probe_devices_hbox = QtWidgets.QHBoxLayout()
            info_probe_devices_hbox.setSpacing(10)
            info_probe_devices_hbox.setContentsMargins(-1, 6, 6, -1)
            if self._provide_devices: 
                info_probe_devices_hbox.addWidget(self.probe_device_button)
                info_probe_devices_hbox.addWidget(self.reset_device_button)
                info_probe_devices_hbox.addWidget(self.fast_search_button)
            info_probe_devices_hbox.addStretch()
            button_box.setLayout(info_probe_devices_hbox)
            button_box.setFixedHeight(36)
            main_layout.addWidget(button_box)

        if self._provide_devices:
            #   VISA manager
            visa_manager_box = QtWidgets.QVBoxLayout()
            visa_manager_box.addWidget(QtWidgets.QLabel("VISA Manager"))
            visa_manager_box.addWidget(self.visa_manager)
            main_layout.addLayout(visa_manager_box)
            #   Device managers
            groupBox = QtWidgets.QGroupBox("Requested Devices")
            formLayout = QtWidgets.QFormLayout()
            for device_index in range(0,len(self.procedure_class.requested_devices)):
                device_name = self.procedure_class.requested_devices[device_index]
                device_box = QtWidgets.QVBoxLayout()
                device_box.addWidget(QtWidgets.QLabel(device_name))
                device_box.addWidget(self.device_manager[device_index])
                device_box.setContentsMargins(-1, -1, -1, -1)
                formLayout.addRow(device_box)
            groupBox.setLayout(formLayout)
            scroll = QtWidgets.QScrollArea()
            scroll.setWidget(groupBox)
            scroll.setWidgetResizable(True)
            main_layout.addWidget(scroll)
        main_layout.setAlignment(self,QtCore.Qt.AlignTop)
        self.setLayout(main_layout)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Minimum,QtWidgets.QSizePolicy.Policy.Maximum)

    def _probe_devices_internal(self):
        log = logging.getLogger()
        manager = make_resourcemanager(self.visa_manager.get_visa_path())
        self.procedure_class._possible_devices = find_devices(manager=manager, multithreading=self.manual_device_selection_widget.isChecked())
        log.info("DeviceControlWindow:Finished searching for devices...")
        self._update_device_manager_widgets()

    def _probe_devices(self, event) -> None:
        """If `procedure_class` is of class `DeviceProcedure` this method will search for connected, valid GPIB devices and list those in the procedure_class's _possible_devices list.\n
        This method will also update / create the list `self.device_manager` containing `DeviceManagerWidget`s for every device in `procedure_class.requested_devices`.
        """
        log = logging.getLogger()
        log.info("DeviceControlWindow:Searching for devices...")
        finder_thread = threading.Thread(target=self._probe_devices_internal)
        finder_thread.start()
    
    def _update_device_manager_widgets(self):
        for device_index in range(0, len(self.procedure_class.requested_devices)):
            self.device_manager[device_index].possible_devices = self.procedure_class._possible_devices
            self.device_manager[device_index].update_descriptors()
            self.device_manager[device_index].update()
    
    def _reset_devices_internal(self):
        manager = make_resourcemanager(custom_visalib_path=self.visa_manager.get_visa_path())
        reset_all_connected_devices(manager=manager, multithreading=self.manual_device_selection_widget.isChecked())
        log = logging.getLogger()
        log.info("DeviceControlWindow:Finished resetting devices...")

    def _reset_devices(self, event) -> None:
        log = logging.getLogger()
        log.warning("DeviceControlWindow:Resetting all connected devices...")
        reset_thread = threading.Thread(target=self._reset_devices_internal)
        reset_thread.start()

### Windows base class
class DeviceManagerWindow(ManagedWindowBase):
    """A custom version of the pymeasure `ManagedWindowBase` class.\n
    If `show_devices=True` it will handle procedures of the `DeviceProcedure` class and read their `requested_devices` list, showin a `DeviceManagerWidget` per requested device. Options are displayed via their `_possible_devices` list to allow a user to select a device from a list of known devices. The default devices shown are the `default_devices` of the `DeviceProcedure`. It also shows a `VISAPathManagerWidget` to allow a user to select a custom VISA library.\n
    Selected devices are passed to the `DeviceProcedure` upon calling the queue() function by starting a measurement with the `Procedure` startup() function.\n
    If `show_help=True` will show a button that opens a text-window displaying the doc-string of the selected `procedure_class`.\n

    
    Attributes
    ----------
    procedure_class : DeviceProcedure
        A procedure that is a parent class of the `DeviceProcedure` class.
    show_devices : bool, optional
        Show option to select devices. If False will not attempt to provide devices to the `procedure_class` via `procedure_class.provided_devices`, else will attempt to provide devices. Defaults to True.
    show_help : bool, optional
        Option to display a button to show the doc-string of the `procedure_class` as a text-window. Defaults to True.
    help_format : str, optional
        `"markdown"`, `"html"` or `"plain"`. Will choose how the help window will format the doc-string of `procedure_class`. Defaults to "markdown".
    show_tool_tips : bool, optional
        If True will show tool-tips for parameters in the `procedure_class` using information from the `DeviceProcedure.tool_tip_information` dictionary. Defaults to True.
    use_right_dock : bool, optional
        If True will display various elements on the right of the window to make more space for inputs. Defaults to True
    """
    procedure_class : DeviceProcedure
    show_devices : bool = True
    show_help : bool = True
    help_format : str = "plain" # ["markdown", "html", "plain"]
    show_tool_tips : bool = True
    use_right_dock : bool = True
    _show_help : bool = False

    # Overload ManagedWindowBase layout to add the VISAPathManagerWidget and the DeviceManagerWidget
    def _setup_ui(self):
        ### Added
        log = logging.getLogger()
        title = self.procedure_class.__name__
        if hasattr(self.procedure_class, "name"):
            title = self.procedure_class.name if self.procedure_class.name != "" else self.procedure_class.__name__
        else:
            log.warning(f"DeviceManagerWindow:Procedure class {self.procedure_class.__name__} has no name.")
        self.setWindowTitle(title)
        if self.show_help:
            if hasattr(self.procedure_class, "__doc__"):
                markdown = False
                html = False
                if self.help_format == "markdown":
                    markdown = True
                elif self.help_format == "html":
                    html = True
                self._show_help = True
                self.help_window = HelpWindow(parent=self, window_title="Help for "+title, formated_text=self.procedure_class.__doc__, markdown=markdown, html=html, readOnly=True)
                self.help_button = QtWidgets.QPushButton(parent=self, text="Help")
                self.help_button.clicked.connect(self._open_help_window)
                self.help_button.setToolTip("Display a window with further information about the procedure.")
            else:
                log.error(f"DeviceManagerWindow:Could not show help option as procedure class {self.procedure_class.__name__} has no doc-string to show!")
        #   Button to manage devices
        self.device_control_window = DeviceControlWindow(parent=self, procedure_class=self.procedure_class, procedure_title=title)
        self.device_manager_button = QtWidgets.QPushButton(parent=self, text="Manage Connected Devices")
        self.device_manager_button.clicked.connect(self._open_device_manager)
        self.device_manager_button.setToolTip("Display a window to control the connected devices for this procedure.")
        ###

        self.queue_button = QtWidgets.QPushButton('Queue', self)
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
        ### Added
        #   Make tool-tips
        if self.show_tool_tips:
            information_dict = None
            if hasattr(self.procedure_class, "tool_tip_information"):
                information_dict = getattr(self.procedure_class, "tool_tip_information")
            parameters = self.inputs._procedure.parameter_objects()
            for name in self.procedure_class.inputs:
                try:
                    parameter = parameters[name]
                    ui_element = getattr(self.inputs,name)
                    information = ""
                    if information_dict is not None:
                        if name in information_dict.keys():
                            information = information_dict[name]
                    tool_tip = self.make_tool_tip(parameter=parameter, information=information)
                    ui_element.setToolTip(tool_tip)
                except:
                    pass
        ###

        if self.enable_file_input:
            self.file_input = FileInputWidget(parent=self)

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

        if self.use_estimator:
            self.estimator = EstimatorWidget(
                parent=self
            )
            ### Added
            try:
                #   TODO:Find origin of this PySide 6 exclusive bug!
                self.estimator.update_thread.setObjectName("Estimator-Thread (cant be closed properly with PySide6)")
            except:
                pass
            ###

    def _layout(self):
        self.main = QtWidgets.QWidget(self)
        
        ### Added
        #   Buttons to show a help window and for probing devices
        if self._show_help and self.show_devices or self.show_devices or self._show_help:
            button_dock = QtWidgets.QWidget(self)
            info_probe_devices_hbox = QtWidgets.QHBoxLayout()
            info_probe_devices_hbox.setSpacing(10)
            info_probe_devices_hbox.setContentsMargins(-1, 6, 6, -1)
            if self.show_devices: 
                info_probe_devices_hbox.addWidget(self.device_manager_button)
            if self._show_help:
                info_probe_devices_hbox.addWidget(self.help_button)
            info_probe_devices_hbox.addStretch()
            button_dock.setLayout(info_probe_devices_hbox)
            button_dock.setFixedHeight(36)
            dock = QtWidgets.QDockWidget()
            dock.setWidget(button_dock)
            dock.setFeatures(QtWidgets.QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
            ### Changed
            if self.use_right_dock:
                self.addDockWidget(QtCore.Qt.DockWidgetArea.RightDockWidgetArea, dock)
            else:
                self.addDockWidget(QtCore.Qt.DockWidgetArea.LeftDockWidgetArea, dock)
            ###

        inputs_dock = QtWidgets.QWidget(self)
        inputs_vbox = QtWidgets.QVBoxLayout(self.main)

        queue_abort_hbox = QtWidgets.QHBoxLayout()
        queue_abort_hbox.setSpacing(10)
        queue_abort_hbox.setContentsMargins(-1, 5, -1, 5)
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

        dock = QtWidgets.QDockWidget('Input Parameters')
        dock.setWidget(inputs_dock)
        dock.setFeatures(QtWidgets.QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        self.addDockWidget(QtCore.Qt.DockWidgetArea.LeftDockWidgetArea, dock)

        if self.use_sequencer:
            sequencer_dock = QtWidgets.QDockWidget('Sequencer')
            sequencer_dock.setWidget(self.sequencer)
            sequencer_dock.setFeatures(QtWidgets.QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
            ### Changed
            if self.use_right_dock:
                self.addDockWidget(QtCore.Qt.DockWidgetArea.RightDockWidgetArea, sequencer_dock)
            else:
                self.addDockWidget(QtCore.Qt.DockWidgetArea.LeftDockWidgetArea, sequencer_dock)
            ###

        if self.use_estimator:
            estimator_dock = QtWidgets.QDockWidget('Estimator')
            estimator_dock.setWidget(self.estimator)
            estimator_dock.setFeatures(QtWidgets.QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
            ### Changed
            if self.use_right_dock:
                self.addDockWidget(QtCore.Qt.DockWidgetArea.RightDockWidgetArea, estimator_dock)
            else:
                self.addDockWidget(QtCore.Qt.DockWidgetArea.LeftDockWidgetArea, estimator_dock)
            ###

        self.tabs = QtWidgets.QTabWidget(self.main)
        for wdg in self.widget_list:
            self.tabs.addTab(wdg, wdg.name)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        splitter.addWidget(self.tabs)
        splitter.addWidget(self.browser_widget)
        splitter.setSizes([700,150])

        vbox = QtWidgets.QVBoxLayout(self.main)
        vbox.setSpacing(0)
        vbox.addWidget(splitter)

        self.main.setLayout(vbox)
        self.setCentralWidget(self.main)
        self.main.show()
        self.resize(1600, 900)
        
    def queue(self, procedure=None):
        ### Added
        if self.device_control_window._provide_devices:
            provided_devices = []
            devices = self.procedure_class.requested_devices
            for device_index in range(0,len(devices)):
                provided_device = self.device_control_window.device_manager[device_index].get_selected_device()
                provided_devices.append(provided_device)
            self.procedure_class.provided_devices = provided_devices
            self.procedure_class.visa_path = self.device_control_window.visa_manager.get_visa_path()
        ###
        
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
            except KeyError as E:
                if not E.args[0].startswith("The following placeholder-keys are not valid:"):
                    raise E from None
                log = logging.getLogger()
                log.error(f"Invalid filename provided: {E.args[0]}")
                return
        else:
            filename = tempfile.mktemp(prefix='TempFile_', suffix='.csv')

        results = Results(procedure, filename)

        experiment = self.new_experiment(results)
        self.manager.queue(experiment)

    ### Own methods for actions on button pushes
    def make_tool_tip(self, parameter:IntegerParameter|FloatParameter|Parameter|ListParameter|BooleanParameter, information:str="") -> str:
        """Creates a tool-tip string for a `pymeasure` `Parameter` using the default, units, maxiumum and minimum attributes.

        Args:
            parameter (IntegerParameter | FloatParameter | Parameter | ListParameter | BooleanParameter): A parameter defined in a procedure.
            information (str | None, optional): Custom information about the parameter to be displayed. Defaults to empty string.

        Returns:
            str: Tool-tip in shape `information. Default value: ... . Range ... to ...`.
        """
        tool_tip = information
        if information != "" and information[-1] != '.':
            tool_tip += "."

        default = str(getattr(parameter,"default")) if hasattr(parameter,"default") and getattr(parameter,"default")!=None else ""
        units   = str(getattr(parameter,"units")  ) if hasattr(parameter,"units") and getattr(parameter,"units")!=None else ""
        maximum = str(getattr(parameter,"maximum")) if hasattr(parameter,"maximum") else ""
        minimum = str(getattr(parameter,"minimum")) if hasattr(parameter,"minimum") else ""


        if default != "":
            tool_tip += f" Default value: '{default}'{units}."
        if maximum != "" and minimum != "":
            try:
                _maximum = float(maximum)
                _minimum = float(minimum)
                if abs(_minimum) > 1E3:
                    tool_tip += f" Range: '{_minimum:.2E}'{units}"
                else:
                    tool_tip += f" Range: '{_minimum}'{units}"
                if abs(_maximum) > 1E3:
                    tool_tip += f" to '{_maximum:.2E}'{units}."
                else:
                    tool_tip += f" to '{_maximum}'{units}."
            except:
                tool_tip += f" Range: '{minimum}'{units} to '{maximum}'{units}."
            
        return tool_tip
            
    def _open_help_window(self, event):
        if self._show_help:
            self.help_window.show()
        else:
            log = logging.getLogger()
            log.warning(f"DeviceManagerWindow:Can not show help, no text available.")

    def _open_device_manager(self, event):
        if self.show_devices:
            self.device_control_window.show()
        else:
            log = logging.getLogger()
            log.warning(f"DeviceManagerWindow:Can not show device control window, displaying devices is disabled.")
