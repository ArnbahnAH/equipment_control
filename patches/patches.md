### Fix for communication issues on Oxford Instruments devices using GPIB and PyVISA-py

As of the 26.06.2026 the PyVISA-py backend for communication with GPIB did not properly forward the EOS charcter and was expecting the EOI to be asserted.<br>As the Oxford ITC503 and IPS120-10 do not assert the EOI signal no reads from the instruments were possible when using the PyVISA-py backend!<br>
The issue has been fixed and can be installed via their GitHub:<br>`$ python3 -m pip install git+https://github.com/pyvisa/pyvisa-py.git`<br>
The fix is explained here: https://github.com/pyvisa/pyvisa-py/pull/597.<br>
The provided `.patch` files are fixing the issue as well.