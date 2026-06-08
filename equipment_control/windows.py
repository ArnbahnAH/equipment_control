"""
A header file containing possible `pymeasure` `PyQt` GUI applications for measurements. 
"""
import logging
from pymeasure.display.widgets import PlotWidget,TableWidget,LogWidget
from pymeasure.display.widgets.dock_widget import DockWidget
# Own files
from .device import DeviceProcedure
from .display import DeviceManagerWindow

class WindowSingleDock(DeviceManagerWindow):
    procedure_class : DeviceProcedure
    def __init__(self, 
                 procedure : DeviceProcedure, 
                 DockWidgetArgs : dict = {}, 
                 TableWidgetArgs : dict = {}, 
                 LogWidgetArgs : dict = {},
                 log : logging.Logger = logging.getLogger()):
        if not hasattr(procedure, "inputs") or not hasattr(procedure, "displays"):
            raise TypeError("WindowSingleDock: 'procedure' must be a DeviceProcedure with attributes 'inputs' and 'displays'!")

        self.procedure_class = procedure
        self.plot_widget = DockWidget(name="Plot",
                                  procedure_class = self.procedure_class,
                                  x_axis_labels = [self.procedure_class.DATA_COLUMNS[0]],
                                  y_axis_labels = [self.procedure_class.DATA_COLUMNS[1]],
                                  **DockWidgetArgs)
        self.table_widget = TableWidget(name="Table",
                                   columns=self.procedure_class.DATA_COLUMNS,
                                   by_column=True,
                                   **TableWidgetArgs)
        self.log_widget = LogWidget(name="Log",
                                 **LogWidgetArgs)
        
        self.plot_widget.clear_widget()
        self.table_widget.clear_widget()
        
        widget_list = (self.plot_widget,self.table_widget,self.log_widget)
        
        super().__init__(procedure_class=self.procedure_class,
                         inputs=self.procedure_class.inputs,
                         displays=self.procedure_class.displays,
                         widget_list=widget_list,
                         inputs_in_scrollarea=True,
                         sequencer=True,
                         sequencer_inputs=self.procedure_class.inputs)
        
        self.file_input.extensions = ["csv", "txt", "dat"]
        log.addHandler(self.log_widget.handler)
        log.setLevel(self.log_level)
        log.info("WindowSingleDock connected to logging.")