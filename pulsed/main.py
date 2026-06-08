
import sys
import pkgutil
import importlib
from pathlib import Path
import traceback

from PySide6.QtWidgets import QApplication
from .frontend import MainWindow
from .export import PossibleDevies


# this will be run by uv run pulsed
def main():
    prefix = Path(__file__).parent / "impl"
    base = "pulsed.impl."
    modules = list(pkgutil.iter_modules([prefix]))
    #print([m.name for m in modules])

    for a, module_name, is_pkg in modules:
        #print(a,module_name, is_pkg)
        module_name = base + module_name
        if not is_pkg:
            try:
                # TODO maybe sort the module first before triggering the registering
                importlib.import_module(module_name) #triggers @export  registering everything to SupportedProcedureList
            except Exception as e:
                print(f"Error importing {module_name}:", e)
                traceback.print_exc()
                print("Moving on.")

    # sort to fix order we can also just assign a priority and sort after that
    PossibleDevies.sort(key=lambda m: m.uid())
    #print([s.procedure_class for s in SupportedProcedureList])
    assert(len(PossibleDevies) >= 1)

    for device in PossibleDevies:


        print(device.uid())

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    app.exec()

if __name__ == "__main__":
    main()
