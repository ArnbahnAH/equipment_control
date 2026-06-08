import sys
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QFormLayout,
                               QHBoxLayout, QDoubleSpinBox, QFrame, QVBoxLayout,
                               QPushButton, QCheckBox, QMessageBox)
from PySide6.QtGui import QPainter, QPen, QBrush, QPolygon, QFont
from PySide6.QtCore import Qt, QRectF, QPoint# Ergänzt, da in PyQt5.QtCore meist Qt genutzt wird

import numpy as np
import matplotlib.pyplot as plt
from qtpy.QtWidgets import QComboBox


from .impl.keithley2400pulse import Keithley2400Pulse
from .config import get_storage, dump_to_file
from .export import PossibleDevies




class PulseWidget(QWidget):
    """
    misc widget to make the square wave drawing
    """
    def __init__(self, high_ms, low_ms):
        super().__init__()
        self.setMinimumSize(600, 350)

        self.high_ms = high_ms
        self.low_ms = low_ms
        self.factor = 50 # µs / px

        self.high_px = self.convert_ms_to_pixel(self.high_ms)
        self.low_px = self.convert_ms_to_pixel(self.low_ms)

    def set_times(self, high_px, low_px, high_ms, low_ms):
        self.high_px = high_px
        self.low_px = low_px
        self.high_ms = high_ms
        self.low_ms = low_ms
        self.update()

    def draw_arrow(self, painter, start_point, direction):
        arrow_size = 8
        x, y = start_point.x(), start_point.y()

        if direction == "left":
            poly = QPolygon([
                QPoint(x, y),
                QPoint(x + arrow_size, y - arrow_size // 2),
                QPoint(x + arrow_size, y + arrow_size // 2)
            ])
        elif direction == "right":
            poly = QPolygon([
                QPoint(x, y),
                QPoint(x - arrow_size, y - arrow_size // 2),
                QPoint(x - arrow_size, y + arrow_size // 2)
            ])
        painter.drawPolygon(poly)

    def convert_ms_to_pixel(self, t):
        """
        we want to convert ms to px
        t will be in ms
        factor will be in µs/px
        """
        return t * 1e3 / self.factor

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        #painter.translate(100, 0)#self.offset_x, self.offset_y)

        grid_spacing = self.factor # will represent 2.5ms per grid cell
        grid_pen = QPen(Qt.GlobalColor.gray, 0.5, Qt.PenStyle.SolidLine)
        painter.setPen(grid_pen)
        for x in range(0, self.width(), grid_spacing):
            painter.drawLine(x, 0, x, self.height())
        for y in range(0, self.height(), grid_spacing):
            painter.drawLine(0, y, self.width(), y)

        start_x = 50
        y_high = 120
        y_low = 220
        cycles = int(self.width() / (self.high_px + self.low_px))

        wave_pen = QPen(Qt.blue, 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.MiterJoin)
        painter.setPen(wave_pen)

        current_x = start_x
        painter.drawLine(10, y_low, start_x, y_low)

        for i in range(cycles+1):
            painter.drawLine(current_x, y_low, current_x, y_high)

            next_x = int(current_x + self.high_px)
            painter.drawLine(current_x, y_high, next_x, y_high)
            if i == 0:
                high_end_x_first = next_x

            current_x = next_x
            painter.drawLine(current_x, y_high, current_x, y_low)

            next_x = int(current_x + self.low_px)
            painter.drawLine(current_x, y_low, next_x, y_low)
            if i == 0:
                low_end_x_first = next_x

            current_x = next_x


        painter.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        painter.setBrush(QBrush(Qt.darkRed))

        y_dim_high = 70
        dim_pen = QPen(Qt.darkRed, 1.5, Qt.PenStyle.SolidLine)
        line_pen = QPen(Qt.gray, 1, Qt.PenStyle.DashLine)

        painter.setPen(line_pen)
        painter.drawLine(start_x, y_high, start_x, y_dim_high - 15)
        painter.drawLine(high_end_x_first, y_high, high_end_x_first, y_dim_high - 15)

        painter.setPen(dim_pen)
        painter.drawLine(start_x, y_dim_high, high_end_x_first, y_dim_high)
        self.draw_arrow(painter, QPoint(start_x, y_dim_high), "left")
        self.draw_arrow(painter, QPoint(high_end_x_first, y_dim_high), "right")

        text_high = f"High: {self.high_ms} ms"
        box_width = max(self.high_px, self.factor * 20)
        mid_high_x = start_x + (self.high_px / 2)
        text_box = QRectF(mid_high_x - (box_width / 2), y_dim_high - 20, box_width, 20)

        painter.setPen(Qt.black)
        painter.drawText(text_box, Qt.AlignmentFlag.AlignCenter, text_high)

        y_dim_low = 270

        painter.setPen(line_pen)
        painter.drawLine(high_end_x_first, y_low, high_end_x_first, y_dim_low + 15)
        painter.drawLine(low_end_x_first, y_low, low_end_x_first, y_dim_low + 15)

        painter.setPen(dim_pen)
        painter.drawLine(high_end_x_first, y_dim_low, low_end_x_first, y_dim_low)
        self.draw_arrow(painter, QPoint(high_end_x_first, y_dim_low), "left")
        self.draw_arrow(painter, QPoint(low_end_x_first, y_dim_low), "right")

        text_low = f"Low: {self.low_ms} ms"
        painter.setPen(Qt.black)
        box_width = max(self.low_px, self.factor * 20)
        mid_high_x = high_end_x_first + (self.low_px / 2)
        text_box = QRectF(mid_high_x - (box_width / 2), y_dim_low + 5, box_width, 20)

        painter.setPen(Qt.black)
        painter.drawText(text_box, Qt.AlignmentFlag.AlignCenter, text_low)

        painter.setPen(Qt.GlobalColor.darkGray)
        painter.setFont(QFont("Arial", 9, QFont.Weight.Normal))


        text_grid = f"Gridspacing: {grid_spacing * self.factor * 1e-3}ms"
        padding = 10
        box_width = 150
        box_height = 20
        text_box_grid = QRectF(
            self.width() - box_width - padding,
            self.height() - box_height - padding,
            box_width,
            box_height
        )
        painter.drawText(text_box_grid, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, text_grid)



class MainWindow(QMainWindow):

    smu = None
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Pulsewindow")
        self.resize(420, 200)

        main_widget = QWidget()
        layout = QHBoxLayout(main_widget)

        high_ms = 4
        low_ms = 4


        self.pulse_widget = PulseWidget(high_ms, low_ms)


        self.deviceSelectionBox = QComboBox()
        for Device in PossibleDevies:
            self.deviceSelectionBox.addItem(Device.uid(), Device)

        idx = self.deviceSelectionBox.findData(Keithley2400Pulse)
        if idx != -1:
            self.deviceSelectionBox.setCurrentIndex(idx)


        self.high_spin = QDoubleSpinBox()
        self.high_spin.setRange(0.5, 100.0)
        self.high_spin.setSuffix(" ms")
        self.high_spin.setSingleStep(0.5)
        self.high_spin.setDecimals(1)
        self.high_spin.setValue(high_ms)


        self.low_spin = QDoubleSpinBox()
        self.low_spin.setRange(0.5, 100.0)
        self.low_spin.setSuffix(" ms")
        self.low_spin.setSingleStep(0.5)
        self.low_spin.setDecimals(1)
        self.low_spin.setValue(high_ms)

        self.high_spin.valueChanged.connect(self.on_value_changed)
        self.low_spin.valueChanged.connect(self.on_value_changed)




        #keithley2400 can provide ~20W i.e. 20V @ 1A
        self.current_spin = QDoubleSpinBox()
        self.current_spin.setRange(0.001, 1000.0)
        self.current_spin.setDecimals(3)
        self.current_spin.setSingleStep(10.0)
        self.current_spin.setSuffix(" mA")
        self.current_spin.setValue(100.0)
        self.current_spin.setToolTip("Keep in mind that the Keithley2400 only delivers 20W 1.05A at 20V is max")



        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        #We could go upto 210V at 0.1A according to the specs
        #self.volt_spin = QDoubleSpinBox()
        #self.volt_spin.setRange(0.001, 20.0)
        #self.volt_spin.setDecimals(3)
        #self.volt_spin.setSingleStep(1.0)
        #self.volt_spin.setSuffix(" V")
        #self.volt_spin.setValue(20.0)

        self.measure_check = QCheckBox("Measure?") #TODO modify time bounds depending on this setting
        self.measure_check.setToolTip("Measuring while running a pulse gives a lower bound of 2ms for high or low time.")
        self.measure_check.toggled.connect(self.handle_measure_check)
        self.measure_check.setChecked(True)

        self.start_btn = QPushButton("Start Pulse")
        self.stop_btn = QPushButton("Stop Pulse")
        self.test_btn = QPushButton("Test Pulse")
        self.start_btn.clicked.connect(self.handle_start)
        self.stop_btn.clicked.connect(self.handle_stop)
        self.test_btn.clicked.connect(self.handle_test)
        self.stop_btn.setEnabled(False)
        self.test_btn.setToolTip("Runs a test run afterwards you get to chekc on the timings in matplotlib")

        controls = QFormLayout()
        controls.addRow("Impl:", self.deviceSelectionBox)
        controls.addRow("High-Time ms:", self.high_spin)
        controls.addRow("Low-Time ms:", self.low_spin)
        controls.addRow("Current:", self.current_spin)

        controls.addRow(line)
        #controls.addRow("Volt range:", self.volt_spin)
        controls.addRow(self.measure_check)
        controls.addRow(self.start_btn)
        controls.addRow(self.stop_btn)
        controls.addRow(self.test_btn)


        layout.addWidget(self.pulse_widget, 0)
        layout.addLayout(controls, 0)

        self.setCentralWidget(main_widget)
        self.on_value_changed()

    def __deinit__(self):
        if self.smu is not None:
            self.smu.stop()
        STORAGE = get_storage()
        dump_to_file()


    def handle_measure_check(self, measuring):
        # essentially change the lower bounds if measuring
        if measuring:
            self.high_spin.setRange(2.0, 100.0)
            self.low_spin.setRange(2.0, 100.0)
            if self.high_spin.value() <= 2.0:
                self.high_spin.setValue(2.0)
            if self.low_spin.value() <= 2.0:
                self.low_spin.setValue(2.0)
        else:
            self.high_spin.setRange(0.64, 100.0)
            self.low_spin.setRange(0.64, 100.0)

        pass
    def handle_start(self):
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

        curr = self.current_spin.value() * 1e-3
        thigh = self.high_spin.value()
        tlow = self.low_spin.value()



        # TODO hmmm......

        if self.smu is None:

            SMUDevice = self.deviceSelectionBox.currentData()
            #print("Testing smudevice:", SMUDevice.uid())
            try:
                port = SMUDevice.find_device()
                self.smu = SMUDevice(port=port)
                if self.measure_check.isChecked():
                    self.smu.start(curr, thigh, tlow)
                else:
                    # potentially faster but its not stable and no feedback
                    self.smu.start(curr, thigh, tlow, measure=False)
            except:
                self.handle_stop()
                QMessageBox.critical(
                    self,
                    "Device Not Found",
                    f"Could not connect to the {SMUDevice.uid()} SMU.\n\nPlease check the USB/GPIB cable and try again."
                )
        pass

    def handle_stop(self):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

        if self.smu is not None:
            self.smu.stop()

        self.smu = None

        pass

    def handle_test(self):
        curr = self.current_spin.value() * 1e-3
        thigh = self.high_spin.value()
        tlow = self.low_spin.value()

        if self.smu is None:
            SMUDevice = self.deviceSelectionBox.currentData()
            #print("Testing smudevice:", SMUDevice.uid())
            try:
                port = SMUDevice.find_device()
                self.smu = SMUDevice(port=port)
                self.smu.test(curr, thigh, tlow)
            except:
                QMessageBox.critical(
                    self,
                    "Device Not Found",
                    f"Could not connect to the {SMUDevice.uid()} SMU.\n\nPlease check the USB/GPIB cable and try again."
                )
        self.smu = None

        pass

    def on_value_changed(self):
        high_ms = self.high_spin.value()
        low_ms = self.low_spin.value()

        high_px = self.pulse_widget.convert_ms_to_pixel(high_ms)
        low_px = self.pulse_widget.convert_ms_to_pixel(low_ms)


        self.pulse_widget.set_times(high_px, low_px, high_ms, low_ms)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
