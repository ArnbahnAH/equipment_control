## Adapters
- Nova: NI USB B (3923/702b)
- Blue Oxford Kryo: NI USB HS (3923/709b)<br>
## Support
A list of supported devices on National Instruments (NI) drivers is given in https://www.ni.com/de/support/documentation/compatibility/21/ni-hardware-and-operating-system-compatibility.html.<br>
- Both the NI USB B and NI USB HS do not work on the linux version of NI-488.2.
- Both adapters do not work on modern windows versions of NI-488.2. NI claims support up to version 21.5, it has been tested to work on version 17.6.
- Both adapters have been tested to work on version 17.5 of NI-VISA, newer versions are not tested.
- Both adapters work on linux-gpib-4.3.7.
## Installation
#### Linux:
Follow the `INSTALL_linux-gpib.md` guide for linux-gpib-4.3.7.
#### Windows:
You will need an account for national instruments website to register their software!<br>
Download and install NI-488.2:
- 17.6: https://www.ni.com/de/support/downloads/drivers/download.ni-488-2.html#306147
- 21.5: https://www.ni.com/de/support/downloads/drivers/download.ni-488-2.html#442610<br>

Download and install NI-VISA:
- 17.5: https://www.ni.com/de/support/downloads/drivers/download.ni-visa.html#306040