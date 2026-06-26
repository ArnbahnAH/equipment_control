#   TODO: Test support (e.g. serial polling, reading)
"""A highlevel implementation for communicating with an `AR488<https://sdfa3.org/david/ar488.html>`__ controller.
"""
import logging, time
log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())
from warnings import warn
import pyvisa
from pymeasure.adapters import VISAAdapter

class AR488:
    #   TODO: Add argument kwargs forwarding of functions to write and query
    #   Note: Macros are "Disabled" on my devices so no highlevel functions for defining/deleting macros are included
    """Commands documentation (Docs): `https://sdfa3.org/david/ar488/commands.html<https://sdfa3.org/david/ar488/commands.html>`__\n
    Github: `https://github.com/Twilight-Logic/AR488<https://github.com/Twilight-Logic/AR488>`__\n
    Manual: `https://raw.githubusercontent.com/Twilight-Logic/AR488/master/AR488-manual.pdf<https://raw.githubusercontent.com/Twilight-Logic/AR488/master/AR488-manual.pdf>`__\n
    
    `Multiple Arduinos on the bus and problems with instruments<https://sdfa3.org/david/ar488/build.html#multiple-arduinos-on-the-bus-and-problems-with-instruments>`__:\n

    *The AR488 can be used in both `controller` mode and `device` mode and only ONE controller can be active at any one time. When there is just one Arduino controller on the bus controlling one or more instruments, this does not present a problem, provided that the Arduino is operating within its current handling limits.*\n

    *However, it is possible to have one AR488 operating as a controller and another as a device simultaneously on the bus along with other instruments. In this situation and without any additional buffering (see the following section: SN7516x GPIB transceiver integrated circuits), problems can arise when two or more Arduinos are connected to the GPIB bus and one of them is powered down. Such problems are manifest by instruments failing to respond to the ++read or other commands, failing to respond to direct instrument commands, or other erratic bus communication problems.*

    Attributes
    ----------
    resource (pyvisa.resources.Resource): 
        The `pyvisa` resource used for communication.
    descriptor (str): 
        The `pyvisa` descriptor.
    manager (pyvisa.ResourceManager): 
        The `pyvisa` resourcemanager used to retrieve the `descriptor` and establish connection.
    query_delay (float, optional): 
        The default delay in seconds to wait for an answer from the device when calling the `self.query` function, uses the `delay` parameter in the `pyvisa` query function. Defaults to 0.01.
    buffer_delay (float, optional): 
        The time in seconds between two write / query commands being send to the AR488. After sending any command the AR488 will automatically wait until the `buffer_delay` has passed before sending the next command issued. Defaults to 0.02.
    """
    resource : pyvisa.resources.Resource
    descriptor : str
    query_delay : float = 0.01
    buffer_delay : float = 0.02
    _last_write: float
    def __init__(self, resource:pyvisa.resources.Resource, query_delay : float = 0.01, buffer_delay : float = 0.02):
        """The `AR488<https://sdfa3.org/david/ar488/>`__ GPIB controller.\n
        Uses the `pyvisa` library to communicate with the controller.

        Args:
            resource (pyvisa.resources.Resource): 
                The `pyvisa` resource used for communication.
            query_delay (float, optional): 
                The default delay in seconds to wait for an answer from the device when calling the `self.query` function, uses the `delay` parameter in the `pyvisa` query function. Defaults to 0.01.
            buffer_delay (float, optional): 
                The time in seconds between two write / query commands being send to the AR488. After sending any command the AR488 will automatically wait until the `buffer_delay` has passed before sending the next command issued. Defaults to 0.02.
        """
        self.resource = resource
        self.descriptor = resource.resource_name
        self.query_delay = query_delay
        self.buffer_delay = buffer_delay

        self._last_write = time.time()

        self.address    #   write once to reset input buffer
    
    ### Docs: Prologix-compatible commands
    @property
    def address(self) -> int|None:
        """
        Implementation of `++addr` with an integer argument.\n
        *This is used to set or query the GPIB address. At present, only primary addresses are supported. In controller mode, the address refers to the GPIB address of the instrument that the operator desires to communicate with. The address of the controller is 0. In device mode, the address represents the address of the interface which is now acting as a device.*

        Args:
            address (int): Primary GPIB address ranging from 1 to 29.

        Raises:
            ValueError: If `address` is set incorrectly.
        ------------------------------------------------------------
        Implementation of `++addr` with no argument.\n
        *When issued without a parameter, the command will return the current GPIB address.*
        
        Returns:
            addr (int|None): Currently selected GPIB address or None if not available."""
        addr = self.query("++addr")
        try:
            addr = int(addr)
            return addr
        except:
            log.warning(f"AR488:Can not find valid selected GPIB address, got: '{addr}'")
            warn(f"AR488:Can not find valid selected GPIB address, got: '{addr}'")
            return None
    @address.setter
    def address(self, address : int) -> None:
        addr = None
        if type(address) == int and address > 0 and address < 30:
            addr = address
            self.write(f"++addr {addr}")
        else:
            raise ValueError(f"AR488:address:address is not valid can only be an integer in range 1-29 not '{address}'")
    
    @property
    def auto(self) -> int|None:
        """
        Implementation of `++auto` with an integer argument.\n
        
        *Configure the instrument to automatically send data back to the controller. When auto is enabled, the user does not have to issue `++read` commands repeatedly. This command has additional options when compared with the Prologix version.*\n

        *When set to zero, auto is disabled.*\n

        *When set to 1, auto is designed to emulate the Prologix setting. The controller will automatically attempt to read a response from the instrument after any instrument command or, in fact, any character sequence that is not a controller command beginning with `++`, has been sent.*\n

        *When set to 2, auto is set to “on-query” mode. The controller will automatically attempt to read the response from the instrument after a character sequence that is not a controller command beginning with ++ is sent to the instrument, but only if that sequence ends in a ? character, i.e. it is a query command such as `*IDN?`.*\n

        *When set to 3, auto is set to “continuous” mode. The controller will execute continuous read operations after the first `++read` command is issued, returning a continuous stream of data from the instrument. The command can be terminated by turning off auto with `++auto 0` or performing a reset with `++rst`.*\n
        
        ***Note**: Some instruments generate a “Query unterminated or “-420” error if they are addressed after sending an instrument command that does not generate a response. This simply means that the instrument has no information to send and this error may be ignored. Alternatively, auto can be turned off (`++auto 0`) and a `++read` command issued following the instrument command to read the instrument response.*
        
        **AR488 must be in `controller` mode for this to take effect.**

        Args:
            enable (bool | int): True / False and 1 / 0 to enable / disable auto forwarding, and 2 & 3 for the above behavior.

        Raises:
            ValueError: If `enable` if set incorrectly.
        ------------------------------------------------------------
        Implementation of `++auto` with no argument.\n
        Returns:
            auto (int|None): Current configuration (0,1,2,3) or None if not available."""
        _auto = self.query("++auto")
        try:
            _auto = int(_auto)
            return _auto
        except:
            log.warning(f"AR488:Can not check if auto is enabled, got: '{_auto}'")
            warn(f"AR488:Can not check if auto is enabled, got: '{_auto}'")
            return None
    @auto.setter
    def auto(self, enable:bool|int) -> None:
        _auto = None
        if enable or enable==1:
            _auto = 1
        elif not enable or enable == 0:
            _auto = 0
        elif enable == 2:
            _auto = 2
        elif enable == 3:
            _auto = 3
        else:
            raise ValueError(f"AR488:auto:enable must be 0,1,2 or True/False, not '{enable}'")
        if _auto is not None:
            self.write(f"++auto {_auto}")
    
    @property
    def End_Of_Interrupt(self) -> int|None:
        """
        Implementation of `++eoi` with an integer argument.\n
        *This command enables or disables the assertion of the `EOI` signal. When a data message is sent in binary format, the `CR/LF` terminators cannot be differentiated from the binary data bytes. In this circumstance, the `EOI` signal can be used as a message terminator. When `ATN` is not asserted and `EOI` is enabled, the `EOI` signal will be briefly asserted to indicate the last character sent in a multi- byte sequence. Some instruments require their command strings to be terminated with an EOI signal in order to properly detect the command.*\n
        
        *The `EOI` line is also used in conjunction with ATN to initiate a parallel poll, however, this command has no bearing on that activity.*

        Args:
            enable (bool | int): True / False or 1 / 0, where 0 disables and 1 enables asserting EOI to signal the last character sent

        Raises:
            ValueError: If `enable` is set incorrectly.
        ------------------------------------------------------------
        Implementation of `++eoi` with no argument.\n
        *When issued without a parameter, the command will return the current configuration.*
        Returns:
            assert_eoi (int|None): 1 or 0 where 0 is disabled and 1 enabled asserting EOI to signal the last character sent or None of not available.
        """
        assert_eoi = self.query("++eoi")
        try:
            assert_eoi = int(assert_eoi)
            return assert_eoi
        except:
            log.warning(f"AR488:Can not find out if EOI signal is asserted, got: '{assert_eoi}'")
            warn(f"AR488:Can not find out if EOI signal is asserted, got: '{assert_eoi}'")
            return None
    @End_Of_Interrupt.setter
    def End_Of_Interrupt(self, enable:bool|int) -> None:
        assert_eoi = None
        if enable or enable==1:
            assert_eoi = 1
        elif not enable or enable == 0:
            assert_eoi = 0
        else:
            raise ValueError(f"AR488:End_Of_Interrupt:enable can only be True/False or 1/0 not '{enable}'")
        
        if assert_eoi is not None:
            self.write(f"++eoi {assert_eoi}")
    
    @property
    def End_Of_Send(self) -> int|None:
        """
        Implementation of `++eos` with an integer argument.\n
        *Specifies the GPIB termination character. When data from the host (e.g. a command sequence) is received over USB, all non-escaped `LF`, `CR` or `Esc` characters are removed and replaced by the GPIB termination character, which is appended to the data sent to the instrument. This command does not affect data being received from the instrument.*
        
        Args:
            character (int|str): 0, 1, 2, 3, where 0=CR+LF, 1=CR, 2=LF, 3=none or their string representation.

        Raises:
            ValueError: If `character` is set incorrectly.
        ------------------------------------------------------------
        Implementation of `++eos` with no argument.\n
        *When issued without a parameter, the command will return the current configuration.*
        Returns:
            eos (int|None): The end of send character with 0=CR+LF, 1=CR, 2=LF, 3=none or None if not available.
        """
        eos = self.query("++eos")
        try:
            eos = int(eos)
            return eos
        except:
            log.warning(f"AR488:Can not find EOS character, got: '{eos}'")
            warn(f"AR488:Can not find EOS character, got: '{eos}'")
            return None
    @End_Of_Send.setter
    def End_Of_Send(self, character:int|str) -> None:
        _character = None
        if type(character) == str:
            if character == "\r\n" or character == "\n\r":
                _character = 0
            elif character == '\r':
                _character = 1
            elif character == '\n':
                _character = 2
        elif type(character) == int:
            _character = character
        
        eos = None
        if _character == 0:
            eos = 0
        elif _character == 1:
            eos = 1
        elif _character == 2:
            eos = 2
        elif _character == 3:
            eos = 3
        else:
            raise ValueError(f"AR488:End_Of_Send:character must only be 0, 1, 2, 3 or a of line-feed or carriage-return character or combination of these, not '{character}'")
        
        if eos is not None:
            self.write(f"++eos {eos}")
    
    @property
    def End_Of_Termination(self) -> int|None:
        """
        Implementation of `++eot_enable` with an integer argument.\n
        *This command enables or disables the appending of a user specified character to the USB output from the interface to the host whenever `EOI` is detected while reading data from the GPIB port. The character to send is specified using the `++eot_char` command.*

        Args:
            enable (bool | int): True / False or 1 / 0 where 0 disables and 1 enables sending the `EOT` character to the USB output.

        Raises:
            ValueError: If `enable` is set incorrectly.
        ------------------------------------------------------------
        Implementation of `++eot_enable` with no argument.\n
        *When issued without a parameter, the command will return the current configuration.*

        Returns:
            eot_enable (int|None): 1 or 0, where 0 disables and 1 enables sending the EOT character to the USB output or None if not available.
        """
        eot_enable = self.query("++eot_enable")
        try:
            eot_enable = int(eot_enable)
            return eot_enable
        except:
            log.warning(f"AR488:Can not find find out of EOT character is send, got: '{eot_enable}'")
            warn(f"AR488:Can not find find out of EOT character is send, got: '{eot_enable}'")
            return None
    @End_Of_Termination.setter
    def End_Of_Termination(self, enable:bool|int) -> None:
        eot_enable = None
        if enable or enable == 1:
            eot_enable = 1
        elif not enable or enable == 0:
            eot_enable = 0
        else:
            raise ValueError(f"AR488:End_Of_Termination:enable mut be True/False or 1/0 not '{enable}'")

        if eot_enable is not None:
            self.write(f"++eot_enable {eot_enable}")
    
    @property
    def End_Of_Termination_CHARacter(self) -> int|None:
        """Implementation of `++eot_char` with an integer argument.\n
        *This command specifies the character to be appended to the USB output from the interface to the host whenever an `EOI` signal is detected while reading data from the GPIB bus. The character is a decimal ASCII character value that is less than 256.*
        
        Args:
            character (str | int): An ASCII character with a value smaller than 256 or the value itself.

        Raises:
            ValueError: If `character` is set incorrectly.
        ------------------------------------------------------------
        Implementation of `++eot_char` with no argument.\n
        Returns:
            eot_char (int|None): Integer with a value smaller than 256 representing the ASCII character used for the EOT signal.
        """
        eot_char = self.query("++eot_char")
        try:
            eot_char = int(eot_char)
            return eot_char
        except:
            log.warning(f"AR488:Can not find the EOT character, got: '{eot_char}'")
            warn(f"AR488:Can not find the EOT character, got: '{eot_char}'")
            return None
    @End_Of_Termination_CHARacter.setter
    def End_Of_Termination_CHARacter(self, character : str|int) -> None:
        eot_char = None
        if type(character) == int:
            eot_char = character
        elif type(character) == str:
            eot_char = ord(character)
        else:
            raise ValueError(f"AR488:End_Of_Termination_CHARacter:character must be a string or integer, but got '{character}'")
            
        if eot_char >= 0 and eot_char < 256:
            self.write(f"++eot_char {eot_char}")
        else:
            raise ValueError(f"AR488:End_Of_Termination_CHARacter:ASCII value of character must be smaller than 256 but got '{eot_char}'")
    
    @property
    def Listen_ONly(self) -> int|None:
        """
        Implementation of `++lon`.\n
        *The `++lon` command configures the controller to listen only to traffic on the GPIB bus. In this mode the interface does require to have a GPIB address assigned so the assigned GPIB address is ignored. Traffic is received irrespective of the currently set GPIB address. The interface can receive but not send, so effectively becomes a “listen-only” device. When issued without a parameter, the command returns the current state of `lon` mode.*

        **AR488 must be in `device` mode for this to take effect.**

        Args:
            enable (bool | int): True / False or 1 / 0, where 0=disabled; 1=enabled.

        Raises:
            ValueError: If `enable` is set incorrectly.
        ------------------------------------------------------------
        Implementation of `++lon` with no argument.\n
        *When issued without a parameter, the command will return the current configuration.*
        Returns:
            lon (int|None): The current state of the lon mode, where 0=disabled; 1=enabled or None if not available.
        """
        lon = self.query("++lon")
        try:
            lon = int(lon)
            return lon
        except:
            log.warning(f"AR488:Can not check if AR488 is in listen only mode, got: '{lon}'")
            warn(f"AR488:Can not check if AR488 is in listen only mode, got: '{lon}'")
            return None
    @Listen_ONly.setter
    def Listen_ONly(self, enable:bool|int) -> None:
        lon = None
        if enable or enable == 1:
            lon = 1
        elif not enable or enable == 0:
            lon = 0
        else:
            raise ValueError(f"AR488:Listen_ONly:enable must be True/False or 1/0 not '{enable}'")
        
        if lon is not None:
            self.write(f"++lon {lon}")
    
    @property
    def mode(self) -> int|None:
        """
        Implementation of `++mode` with an integer argument.\n
        *This command configures the AR488 to serve as a controller or a device.*\n

        *In controller mode the AR488 acts as the Controller-in-Charge (CIC) on the GPIB bus, receiving commands terminated with CRLF over USB and sending them to the currently addressed instrument via the GPIB bus. The controller then passes the received data back over USB to the host.*\n

        *In device mode, the AR488 can act as another device on the GPIB bus. In this mode, the AR488 can act as a GPIB talker or listener and expects to receive commands from another controller (`CIC`). All data received by the AR488 is passed to the host via USB without buffering. All data from the host via USB is buffered until the AR488 is addressed by the controller to talk. At this point the AR488 sends the buffered data to the controller. Since the memory on the controller is limited, the AR488 can buffer only 120 characters at a time.*\n

        *When sending data followed by a command, the buffer must first be read by the controller before a subsequent command can be accepted, otherwise the command will be treated as characters to be appended to the existing data in the buffer. Once the buffer has been read, it is automatically cleared and the parser can then detect the `++` command prefix on the next line. Therefore sufficient delay must be allowed for the buffer to be read before sending a subsequent command.*
        
        Args:
            mode (int): 0 or 1 where 0=device, 1=controller.

        Raises:
            ValueError: If `mode` is set incorrectly.
        ------------------------------------------------------------
        Implementation of `++mode` with no argument.\n
        *If the command is issued without a parameter, the current mode is returned.*
        Returns:
            mode (int|None): 0,1 where 0=device, 1=controller.
        """
        mode = self.query("++mode")
        try:
            mode = int(mode)
            return mode
        except:
            log.warning(f"AR488:Can not check AR488 mode, got: '{mode}'")
            warn(f"AR488:Can not check AR488 mode, got: '{mode}'")
            return None
    @mode.setter
    def mode(self, mode:int) -> None:
        _mode = None
        if mode==0:
            _mode = 0
        elif mode==1:
            _mode = 1
        else:
            raise ValueError(f"AR488:mode:mode must be 0 or 1 not '{mode}'")
        
        if _mode is not None:
            self.write(f"++mode {_mode}")

    @property
    def read_timeout(self) -> int|None:
        """
        Implementation of `++read_tmo_ms` with an integer argument.\n
        *This specifies the timeout value, in milliseconds, that is used by the `++read` (and `++spoll`) commands to wait for a character to be transmitted while reading data from the GPIB bus. The timeout value may be set between 0 and 32,000 milliseconds (32 seconds).*

        **AR488 must be in `controller` mode for this to take effect.**

        Args:
            milliseconds (int): A decimal number between 0 and 32000 representing milliseconds.

        Raises:
            ValueError: If `milliseconds` is set incorrectly.
        ------------------------------------------------------------
        Implementation of `++read_tmo_ms` with no argument.\n
        Returns:
            read_tmo_ms (int|None): Currently configured timeout in milliseconds or None if not available.
        """
        read_tmo_ms = self.query("++read_tmo_ms")
        try:
            read_tmo_ms = int(read_tmo_ms)
            return read_tmo_ms
        except:
            log.warning(f"AR488:Can not determine AR488 read timeout, got: '{read_tmo_ms}'")
            warn(f"AR488:Can not determine AR488 read timeout, got: '{read_tmo_ms}'")
            return None
    @read_timeout.setter
    def read_timeout(self, milliseconds:int) -> None:
        ms = None
        if milliseconds >= 0 and milliseconds <= 32000:
            ms = milliseconds
        else:
            raise ValueError(f"AR488:read_timeout:milliseconds must be an integer between 0 and 32000 but got '{milliseconds}'")
        
        if ms is not None:
            self.write(f"++read_tmo_ms {ms}")
        
    @property
    def Service_ReQuest(self) -> int|None:
        """Implementation of `++srq`.\n
        *This command returns the present status of the `SRQ` signal line. It returns 0 if `SRQ` is not asserted and 1 if `SRQ` is asserted.*

        **AR488 must be in `controller` mode for this to take effect.**

        Returns:
            srq (int|None): 0 or 1 or None if not available.
        """
        srq = self.query("++srq")
        try:
            srq = int(srq)
            return srq
        except:
            log.warning(f"AR488:Can not check if SRQ is asserted, got: '{srq}'")
            warn(f"AR488:Can not check if SRQ is asserted, got: '{srq}'")
            return None
    @property
    def status(self) -> None: #TODO: Understand what this is supposed to do
        """Implementation of `++status` with an integer argument.\n
        *Set or display the status byte that will be sent in response to the serial poll command. When bit 6 of the status byte is set, the `SRQ` signal will be asserted indicating Request For Service (`RQS`). The table below shows the values assigned to individual bits as well as some example meanings that can be associated with them. Although the meaning of each bit will vary depending on the instrument and the manufacturer, bit 6 is always reserved as the `RQS` bit. Other bits can be assigned as required.*\n
        
        === ====== === =========== ========== ======= ========= =============== ============
        Bit   7     6       5          4         3       2             1             0     
        === ====== === =========== ========== ======= ========= =============== ============
        Msg Always RQS Calibration Output     Remote  Auto-zero Auto-range      Operational
            0          enabled or  Avail.     control           enabled.        error      
                       Error       Front/Rear                   Front/ Rear sw.            
        === ====== === =========== ========== ======= ========= =============== ============
        
        *The values of the bits to be set can be added together to arrive at the desired status byte value. For example, to assert `SRQ`, a value of `0x40` (64) would be sufficient. However if we wanted to use bit 1 to indicate an operational error, then a value of `0x41` (65) might be used in the event of the error occurring.*

        **AR488 must be in `device` mode for this to take effect.**

        Args:
            byte (int|str): Status byte as a number to be set or a string of 7 digits representing the binary of the byte. String order would be 7654321, e.g. asserting SRQ + Operational error would be "0100001".

        Raises:
            ValueError: If `byte` is not in range 0 to 255.
        ------------------------------------------------------------
        Implementation of `++status` with no argument.\n
        Returns:
            byte (int|None): Current status byte of the AR488 as an integer.
        """
        byte = self.query("++status")
        try:
            byte = int(byte)
            return byte
        except:
            log.warning(f"AR488:Can not determine AR488 status byte, got: '{byte}'")
            warn(f"AR488:Can not determine AR488 status byte, got: '{byte}'")
            return None
    @status.setter
    def status(self, byte:int|str) -> None:
        _byte = None
        if type(byte)==str and len(byte) == 7:
            byte = int(byte,2)
        if type(byte)==int and byte >= 0 and byte < 256:
            _byte = byte
        else:
            raise ValueError(f"AR488:status:byte must be an integer between 0 and 255 or a seven digit binary representing such a number, not '{byte}'")
        self.write(f"++status {_byte}")
        
    def clear(self) -> None:
        """Implementation of `++clr`.\n
        *This command sends a Selected Device Clear (`SDC`) to the currently addressed instrument. Details of how the instrument should respond may be found in the instrument manual.*

        **AR488 must be in `controller` mode for this to take effect.**
        """
        self.write("++clr")
    
    def help(self, command:str|None = None) -> str:
        """Implementation of `++help`.\n
        *Display the list of commands with a short description, or the short description of given command.*

        Can take up to 60 seconds to execute when listing all commands.
        Args:
            command (str | None): The requested AR488 command (see `Docs<https://sdfa3.org/david/ar488/commands.html>`__ for a list) or None for a list of commands.
            
        Returns:
            help (str): The raw string from the AR488 or a list of string separated by a line break.
        Raises:
            ValueError: If `command` is set incorrectly.
        """
        if command is None:
            _help = self.query(f"++help")
            try:
                start = time.time()
                while time.time() - start < 60:
                    _help += "\n" + self.read_resource()
            except:
                pass
            return _help
        elif type(command) == str:
            return self.query(f"++help {command}")
        else:
            raise ValueError(f"AR488:help:command is invalid must be a known AR488 command (see Docs) or None but is '{command}'")
            
    def InterFace_Clear(self) -> None:
        """Implementation of `++ifc`.\n
        *Assert the GPIB `IFC` signal for 150 microseconds, making the AR488 the Controller-in-Charge on the GPIB bus.*

        **AR488 must be in `controller` mode for this to take effect.**
        """
        self.write("++ifc")
    
    def Local_LockOut(self, lock_all:bool=False) -> None:
        """Implementation of `++llo`.\n
        *Disable front panel operation on the currently addressed instrument. In the original HPIB specification, sending the `LLO` signal to the GPIB bus would lock the `LOCAL` control on ALL instruments on the bus. In the Prologix specification, this command disables front panel operation of the addressed instrument only, in effect taking control of that instrument. The AR488 follows the Prologix specification, but adds a parameter to allow the simultaneous assertion of remote control over all instruments on the GPIB bus as per the HPIB specification.*\n

        *This command requires the Remote Enable (`REN`) line to be asserted otherwise it will be ignored. In controller mode, the `REN` signal is asserted by default unless its status is changed by the `++ren` command.*\n

        *When the `++llo` command is issued without a parameter, it behaves the same as it does on the Prologix controller. The `LLO` signal is sent to the currently addressed instrument and this locks out the `LOCAL` key on the instrument control panel. Because the instrument has been addressed and `REN` is already asserted, the command automatically takes remote control of the instrument. Most instruments will display `REM` on their display or control panel to indicate that `ote` control is active and front/rear panel controls will be disabled.*\n

        *If the `++llo` command is issued with the all parameter, this will send the `LLO` signal to the bus, putting every instrument into remote control mode simultaneously. At this point, instruments will not yet show the `REM` indicator and it may still be possible to operate the front panel controls. On some instruments the `LOCAL` key may be locked out. However, as soon as an instrument has been addressed and sent a command (assuming that a `LOC` signal has not been sent yet first), the controller will automatically lock in remote control of that instrument , the `REM` indicator will be displayed and front/rear panel controls will be disabled.*

        **AR488 must be in `controller` mode for this to take effect.**

        Args:
            lock_all (bool, optional): If True will send the `all` command and lock all instruments else will only lock the assigned instrument. Defaults to False.
        """
        if lock_all:
            self.write("++llo all")
        else:
            self.write("++llo")
    
    def unlock_LOCal(self, unlock_all:bool=False) -> None:
        """Implementation of `++loc`.\n
        *Relinquish remote control and re-enable front panel operation of the currently addressed instrument. This command relinquishes remote control of the instrument by de-asserting `REN` and sending the `GTL` signal.*\n

        *The Remote Enable (`REN`) line must be asserted and the instrument must already be under remote control otherwise the command has no effect.*\n

        *In the original HPIB specification, this command would place all instuments back into local mode, re-enabling the `LOCAL` key and panel controls on ALL instruments currently connected to the GPIB bus. In the Prologix specification, this command relinquishes remote control of the currently addressed instrument only. The AR488 follows the Prologix specification, but adds a parameter to allow the simultaneous release of remote control over all instruments currently addressed as listeners on the GPIB bus as per the HPIB specification.*\n

        *If the command is issued without a parameter, it will re-enable the `LOCAL` key on the control panel on the currently addressed instrument and relinquish remote control of the instrument. If issued with the `all` parameter, it puts all devices on the GPIB bus in local control state. The REM indicator should no longer be visible when the instrument has returned to local control state.*

        **AR488 must be in `controller` mode for this to take effect.**

        Args:
            unlock_all (bool, optional): Unlocks all devices if True else only the selected instrument. Defaults to False.
        """
        if unlock_all:
            self.write("++loc all")
        else:
            self.write("++loc")
    
    def read(self, termination:str|int|None=None) -> str:
        """Implementation of `++read` with an integer argument.\n
        *This command can be used to read data from the currently addressed instrument. Data is read until:*

        - *the `EOI` signal is detected*
        - *a specified character is read*
        - *timeout expires*

        *Timeout is set using the read_tmo_ms command and is the maximum permitted delay for a single character to be read. It is not related to the time taken to read all of the data. For details see the description of the `read_tmo_ms` command.*

        **AR488 must be in `controller` mode for this to take effect.**

        Args:
            termination (str | int | None, optional): "eoi" to read until the EOI signal, an ASCII character or its integer value where the value must be less than 256 or None to read until the timeout occurs. Defaults to None

        Raises:
            ValueError: If `termination` is set incorrectly.

        Returns:
            answer (str): The answer of the addressed device.
        """
        self._wait_for_buffer_time()
        if termination is None:
            return self.query("++read")
        elif termination != "eoi":
            _read = None
            if type(termination) == str:
                _read = ord(termination)
            elif type(termination) == int:
                _read = termination
            else:
                raise ValueError(f"AR488:read:termination must be a string or integer not '{termination}'")
            
            if _read >= 0 and _read < 256:
                return self.query(f"++read {_read}")
            else:
                raise ValueError(f"AR488:read:termination must have ASCII value smaller than 256 but gut value '{_read}'")
        else:
            return self.query("++read eoi")
        
    def reset(self) -> None:
        """Implementation of `++rst`.\n
        *Perform a reset of the controller.*\n

        ***Please note that the reset may fail and hang the board under certain circumstances. These include:***\n

        - *the board has an older bootloader. The older bootloader had an problem with not clearing the `MCUSR` register which triggers another reset while the bootloader is being executed, which causes a perpetual restart cycle. The solution here is to update the bootloader. The newer Optiboot bootloader does not have this problem.*
        - *using a 32u4 board (Micro, Leonardo) programmed with an AVR programmer with no bootloader. There is at present no solution to this problem. When programming with an AVR programmer, use a recent IDE version to export the binaries and upload the version with the bootloader to the board.*

        """
        self.write("++rst") 
    
    def save_configuration(self) -> None:
        """Implementation of `++savecfg`.\n
        *This command saves the current interface configuration. On the Prologix interface setting this to 1 would enable the saving of specific parameters whenever they are changed, including `addr`, `auto`, `eoi`, `eos`, `eot_enable`, `eot_char`, `mode` and `read_tmo_ms`. If supported, the wifi configuration will also be saved using this command.*\n

        *Frequent updates wear out the EEPROM and the Arduino EEPROM has a nominal lifetime of 100,000 writes. In order to minimize writes and preserve the longevity of the EEPROM memory, the AR488 does not, at any time, write configuration parameters “on the fly” every time they are changed. Instead, issuing the `++savecfg` command will update the complete current configuration once. Only values that have changed since the last write will be written.*\n

        *The configuration written to EEPROM will be automatically re-loaded on power-up. The configuration can be reset to default using the ++default command and a new configuration can be saved using the `++savecfg` command.*\n

        *Most, if not all Arduino AVR boards support EEPROM memory, however boards from other vendors may not provide this support. If the command is run on a board that does not support EEPROM, then the following will be returned: EEPROM not supported.*\n

        *The `++savecfg` command will save the following current parameter values: `addr`, `auto`, `eoi`, `eos`, `eot_enable`, `eot_char`, `mode`, `read_tmo_ms` and `verstr`; and if supported, `wifi ssid` and `wifi passkey`.*
        
        """
        self.write("++savecfg")
    
    def serial_poll(self, addresses:None|str|int|list[int|str]|tuple[int|str]=None) -> str|None:
        """Implementation of `++spoll` with and without arguments.\n
        *Performs a serial poll. If no parameters are specified, the command will perform a serial poll of the currently addressed instrument. If a GPIB address is specified, then a serial poll of the instrument at the specified address is performed. The command returns a single 8-bit decimal number representing the status byte of the instrument.*\n

        *The command can also be used to serial poll multiple instruments. Up to 15 addresses can be specified. If the all parameter is specified (or the command `++aspoll` is used), then a serial poll of all 30 primary instrument addresses is performed.*\n

        *When polling multiple addresses, the `++spoll` command will return the address and status byte of the first instrument it encounters that has the `RQS` bit set in its status byte, indicating that it has requested service. The format of the response is ***`SRQ:addr,status`***, for example: `SRQ:3,88` where 3 is the GPIB address of the instrument and 88 is the status byte. The response provides a means to poll a number of instruments and to identify which instrument raised the service request, all in one command. If `SRQ` was not asserted then no response will be returned.*\n

        *When `++srqauto` is set to 1 (for details see the `++srqauto` custom command), the interface will automatically conduct a serial poll of all devices on the GPIB bus whenever it detects that `SRQ` has been asserted and the details of the instrument that raised the request are automatically returned in the format above.*

        **AR488 must be in `controller` mode for this to take effect.**

        Args:
            addresses (None | str | int | list[int | str] | tuple[int | str], optional): None to poll only the currently addressed device, "all" to poll all connected devices, an integer/string for a specific address or a list/tuple of integer/strings for a set of up to 15 addresses to be polled. Defaults to None.

        Raises:
            ValueError: If `addresses` is set incorrectly.

        Returns:
            spoll (str | None): The answer of the AR488 in the format of `SRQ:addr,status` for the first instrument the AR488 encounters that has the `RQS` bit set in its status byte or None if no device requested service and the command might fail.
        """
        if self.Service_ReQuest == 0:
            log.warning("AR488:serial_poll:No service request was found but serial poll is being executed, command will not be executed!")
            warn("AR488:serial_poll:No service request was found but serial poll is being executed, command will not be executed!")
            return None
        
        spoll = None
        if addresses is None:
            return self.query(f"++spoll")
        elif addresses == "all":
            spoll = "all"
        elif type(addresses)==int or type(addresses)==str:
            try:
                addresses = int(addresses)
                spoll = str(addresses)
            except:
                raise ValueError(f"AR488:serial_poll:addresses was found as string but can not be converted to integer address, got '{addresses}'")
        elif type(addresses)==list or type(addresses)==tuple:
            if len(address) < 16:
                spoll = ""
                for address in addresses:
                    spoll += f" {address}"
            else:
                raise ValueError(f"AR488:serial_poll:addresses can only include up to 15 instrument addresses not '{len(addresses)}'")
        else:
            raise ValueError(f"AR488:serial_poll:addresses must be None, integer or list of integers/strings not '{addresses}'")
        
        if spoll is not None:
            return self.query(f"++spoll {spoll}")
    
    def trigger(self, addresses:None|int|str|list[int|str]|tuple[int|str]=None) -> None:
        """Implementation of `++trg` with no argument or integer arguments.\n
        *Sends a `Group Execute Trigger` to selected devices. Up to 15 addresses may be specified and must be separated by spaces. If no address is specified, then the command is sent to the currently addressed instrument. The instrument needs to be set to single trigger mode and remotely controlled by the GPIB controller. Using `++trg`, the instrument can be manually triggered and the result read with `++read`.*

        **AR488 must be in `controller` mode for this to take effect.**

        Args:
            addresses (None | list[int | str] | tuple[int | str], optional): If None will only trigger the currently addressed intrument, if an integer/string will address the instrument with that address, if a list or tuple will trigger all addresses in `addresses`. Defaults to None.

        Raises:
            ValueError: If `addresses` is set incorrectly.
        """
        trg = None
        if addresses is None:
            self.write("++trg")
            return
        elif type(addresses)==int or type(addresses)==str:
            try:
                addresses = int(addresses)
                trg = str(addresses)
            except:
                raise ValueError(f"AR488:trigger:addresses was found as a string but cannot be converted to integer, got '{addresses}'")
        elif len(addresses) > 0 and len(addresses) < 16:
            trg = ""
            for address in addresses:
                trg += f" {address}"
        else:
            raise ValueError(f"AR488:trigger:addresses must be None or a list/tuple of int/str no longer than 15 entries not '{addresses}'")
        
        if trg is not None:
            self.write(f"++trg {trg}")
        
    def version(self, real:bool = False) -> str:
        """Implementation of `++ver` with no argument or string argument.\n
        *Display the controller firmware version. If the version string has been changed with `++setvstr`, then `++ver` will display the new version string. Issuing the command with the parameter real will always display the original AR488 version string.*
        
        Args:
            real (bool, optional): If True will add the "real" argument and return the original firmware version else the changed version. Defaults to False.

        Returns:
            ver (str): The answer of the AR488.
        """
        ver = None
        if real:
            ver = self.query("++ver real")
        else:
            ver = self.query("++ver")
        return ver
    
    def parallel_poll(self) -> int|None:
        """Implementation of `++ppoll`.\n
        *When many devices are involved, Parallel Poll is faster than Serial Poll but is not widely used. With a Parallel Poll, the controller can query up to eight devices quite efficiently using the `DIO` lines. Since there are 8 `DIO` lines, up to 8 devices can be queried at once. In order to get an unambiguous response, each device should ideally assign to a separate data line. Devices assigned to the same line are simply OR’ed. Devices respond to the parallel poll by asserting the `DIO` line they have been assigned.*\n

        *Response to a Parallel Poll is a data byte corresponding to the status of the `DIO` lines when the Parallel Poll request is raised. The state of each individual bit of the 8-bit byte corresponds to the state of each individual `DIO` line. In this way it is possible to determine which instrument raised the request.*\n

        *Because a single bit can only be 0 or 1, the response to a parallel poll is binary, simply indicating whether or not an instrument has raised the request. In order to get further status information, a Serial Poll needs to be conducted on the instrument in question.*

        **AR488 must be in `controller` mode for this to take effect.**

        Returns:
            ppoll (int|None): 0 or 1 indicating if any connected device raised the service request or None if not available.
        """
        ppoll = self.query("++ppoll")
        try:
            ppoll = int(ppoll)
            return ppoll
        except:
            log.warning(f"AR488:parallel_poll:Received an unexpected answer that differs from 0 or 1: '{ppoll}'")
            warn(f"AR488:parallel_poll:Received an unexpected answer that differs from 0 or 1: '{ppoll}'")
            return None
            
    ### Docs: Custom commands
    @property
    def End_Of_Receive(self) -> int|None:
        """
        Implementation of `++eor` with an integer argument.\n
        *End of receive. While `++eos` (end of send) selects the terminator to add to commands and data being sent to the instrument, the `++eor` command selects the expected termination sequence when receiving data from the instrument.*

        *The following termination sequences are supported:*\n
        
        ======   =============== ========
        Option   Sequence        Hex
        ======   =============== ========
        0        CR + LF         0D 0A
        1        CR              0D
        2        LF              0A
        3        None            N/A
        4        LF + CR         0A 0D
        5        ETX             03
        6        CR + LF + ETX   0D 0A 03
        7        EOI signal      N/A
        ======== =============== ========
        
        *The default termination sequence is `CR` + `LF`. If the command is specified with one of the above numeric options, then the corresponding termination sequence will be used to detect the end of the data being transmitted from the instrument. If the command is specified without a parameter, then it will return the current setting. If option 7 (`EOI`) is selected, then `++read eoi` is implied for all `++read` instructions as well as any data being retuned by the instrument in response to direct instrument commands. An EOI is expected to be signalled by the instrument with the last character of any transmission sent. All characters sent over the GPIB bus are passed to the serial port for onward transmission to the host computer.*

        **AR488 must be in `controller` mode for this to take effect.**

        Args:
            character (int): The end of return character with 0=CR + LF, 1=CR, 2=LF, 3=None, 4=LF + CR, 5=ETX, 6=CR + LF + ETX, 7=EOI signal.

        Raises:
            ValueError: If `character` is set incorrectly.
        ------------------------------------------------------------
        Implementation of `++eor` with no argument.\n
        *If the command is specified without a parameter, then it will return the current setting.*
        Returns:
            eor (int|None): The end of return character with 0=CR + LF, 1=CR, 2=LF, 3=None, 4=LF + CR, 5=ETX, 6=CR + LF + ETX, 7=EOI signal or None if not available.
        """
        eor = self.query("++eor")
        try:
            eor = int(eor)
            return eor
        except:
            log.warning(f"AR488:Can not find EOR character, got: '{eor}'")
            warn(f"AR488:Can not find EOR character, got: '{eor}'")
            return None
    @End_Of_Receive.setter
    def End_Of_Receive(self, character:int) -> None:
        if character >=0 and character < 8:
            self.write(f"++eor {character}")
        else:
            raise ValueError(f"AR488:End_Of_Receive:character must be an integer in the range of 0-7 not '{character}'")
    
    @property
    def name(self) -> str:
        """
        Implementation of `++id name` with string arguments.\n
        *This command sets the identification parameters for the interface. Here you can set the instrument name and optional serial number. This command also sets the information that can be used by the interface to respond to a SCPI `*idn?` which may be useful where the instrument itself cannot provide such a response. For further information also see the `++idn` command. The command has one of three invocations and an optional parameter:*\n

        *`++id name`*\n

        *This sets a short name for the interface. The name can be up to 15 characters long and should not include spaces. If the command is specified without a parameter, it will return the current name of the interface. By default, the name is not set and the command will not return a value.*

        **AR488 must be in `controller` mode for this to take effect.**

        Args:
            id (str): Identification string to be defined for the name.
        ------------------------------------------------------------
        Implementation of `++id name` with no arguments.\n
        *By default, the name is not set and the command will not return a value.*

        Returns:
            name (str): Name string of the AR488 set by `++id name`.
        """
        return self.query("++id name")
    @name.setter
    def name(self, id:str) -> None:
        self.write(f"++id name {id}")
    
    @property
    def serial_number(self) -> str:
        """
        Implementation of `++id serial` with string arguments.\n
        *This command sets the identification parameters for the interface. Here you can set the instrument name and optional serial number. This command also sets the information that can be used by the interface to respond to a SCPI `*idn?` which may be useful where the instrument itself cannot provide such a response. For further information also see the `++idn` command. The command has one of three invocations and an optional parameter:*\n

        *`++id serial`*\n

        *This sets an optional serial number for the interface. In the event that there are multiple instances of identical instruments on the bus, each instrument can be given a unique serial number up to 9 digits long. When specified without a parameter, the command returns the currently configured serial number. By default the serial number is not set and the command will return 000000000.*

        **AR488 must be in `controller` mode for this to take effect.**

        Args:
            id (int|str): Identification string to be defined for the serial number.

        Raises:
            ValueError: If `id` is not convertible to an integer or has more than 9 digits,
        ------------------------------------------------------------
        Implementation of `++id serial` with no arguments.\n
        *By default the serial number is not set and the command will return `000000000`.*

        Returns:
            serial (str): Serial number of the AR488 set by `++id serial`
        """
        return self.query("++id serial")
    @serial_number.setter
    def serial_number(self, id:int|str) -> None:
        try:
            id = abs(int(id))
            if id < 1E9:
                self.write(f"++id serial {id}")
            else:
                raise ValueError(f"AR488:serial_number:id must be convertible to an integer, not '{id}'")
        except:
            raise ValueError(f"AR488:serial_number:id must be convertible to an integer, not '{id}'")

    @property
    def version_string(self) -> str:
        """
        Implementation of `++id verstr` with string arguments.\n
        *This command sets the identification parameters for the interface. Here you can set the instrument name and optional serial number. This command also sets the information that can be used by the interface to respond to a SCPI `*idn?` which may be useful where the instrument itself cannot provide such a response. For further information also see the `++idn` command. The command has one of three invocations and an optional parameter:*\n

         *`++id verstr`*\n

        *Sets the version string that the controller responds with on boot-up and in response to the `++ver` command. This may be helpful where software on the computer is expecting a specific string from a known controller, for example 'GPIB-USB'. When no parameter is given, the command returns the current version string.*

        **AR488 must be in `controller` mode for this to take effect.**

        Args:
            id (str): Identification string to be defined for the version string.
        ------------------------------------------------------------
        Implementation of `++id verstr` with no arguments.\n
        *When no parameter is given, the command returns the current version string.*

        Returns:
            verstr (str): Version string of the AR488 set by `++id verstr`
        """
        return self.query("++id verstr")
    @version_string.setter
    def version_string(self, id:str) -> None:
        self.write(f"++id verstr {id}")
    
    @property
    def respond_to_SCPI_idn(self) -> int|None:
        """Implementation of `++idn` with an integer argument.\n
        *This command is used to enable the facility for the interface to respond to a SCPI `*idn?` Command. Some older instruments do no respond to a SCPI ID request but this feature will allow the interface to respond on behalf of the instrument using parameters set with the `++id` command. When set to zero, response to the SCPI `*idn?` command is disabled and the request is passed to the instrument. When set to 1, the interface responds with the name set using the `++idn` name command. When set to 2, the instrument also appends the serial number using the format name-99999999.*

        **AR488 must be in `controller` mode for this to take effect.**

        Args:
            enable (bool | int): True/False or 0, 1, 2 with 2 appending the custom serial number.

        Raises:
            ValueError: If `enable` is set incorrectly.
        ------------------------------------------------------------
        Implementation of `++idn` with no argument.\n

        Returns:
            idn (int|None): 1 / 0 if responds to SCPI *idn? or None if not available.
        """
        idn = self.query("++idn")
        try:
            idn = int(idn)
            return idn
        except:
            log.warning(f"AR488:Can not determine if AR488 responds to SCPI *IDN?, got: '{idn}'")
            warn(f"AR488:Can not determine if AR488 responds to SCPI *IDN?, got: '{idn}'")
            return None
    @respond_to_SCPI_idn.setter
    def respond_to_SCPI_idn(self, enable:bool|int) -> None:
        idn = None
        if enable or enable==1:
            idn = 1
        elif not enable or enable==0:
            idn = 0
        elif enable==2:
            idn = 2
        else:
            raise ValueError(f"AR488:respond_to_SCPI_idn:enable must be 0,1,2 or True/False not {enable}")
        
        if idn is not None:
            self.write(f"++idn {idn}")

    @property
    def Remote_ENabled(self) -> int|None:
        """
        Implementation of `++ren` with an integer argument.\n
        *In controller mode, this command turns the `REN` signal on and off. When `REN` is asserted, the controller can remote-control any device on the BUS. With the `REN` signal turned off, the controller can no longer remote-control devices, but can still communicate with them. This is used primarily for diagnostics.*\n

        *When set to 0, `REN` is un-asserted. When set to 1, `REN` is asserted. By default, in controller mode, `REN` will be asserted.*\n

        *When `REN` is used to control the `SN75161` GPIB transceiver integrated-circuit, this command is unavailable and will simply return Unavailable (see the `Configuration` and the `Building an AR488 GPIB Interface` sections for more information). When issued without a parameter, the command returns the current status of the `REN` signal.*

        **AR488 must be in `controller` mode for this to take effect.**

        Args:
            enable (bool | int): True/False or 1/0 to enable or disable the remote control of devices.

        Raises:
            ValueError: If `enable` is set incorrectly.
        ------------------------------------------------------------
        Implementation of `++ren` with no arguments.\n
        *When issued without a parameter, the command returns the current status of the `REN` signal.*
        Returns:
            ren (int|None): 1 or 0 where 1=REN is asserted, 0=REN is not asserted or None if not available.
        """
        ren = self.query("++ren")
        try:
            ren = int(ren)
            return ren
        except:
            log.warning(f"AR488:Can not check if REN is enabled, got: '{ren}'")
            warn(f"AR488:Can not check if REN is enabled, got: '{ren}'")
            return None
    @Remote_ENabled.setter
    def Remote_ENabled(self, enable:bool|int) -> None:
        ren = None
        if enable or enable==1:
            ren = 1
        elif not enable or enable==0:
            ren = 0
        else:
            raise ValueError(f"AR488:Remote_ENabled:enable must be True/False or 1/0 not '{enable}'")
        
        if ren is not None:
            self.write(f"++ren {ren}")
    
    @property
    def auto_Service_ReQuest(self) -> int|None:
        """
        Implementation of `++srqauto` with an integer argument.\n
        *When conducting a serial poll using a Prologix controller, the procedure requires that the status of the `SRQ` signal be checked with the `++srq` command. If the response is a 1, indicating that `SRQ` is asserted, then an `++spoll` command can be issued to determine the status byte of the currently addressed instrument or optionally an instrument at a specific GPIB address.*\n

        *When polling multiple devices, the AR488 will provide a custom response that includes the address and status byte of the first instrument encountered that has the `RQS` bit set. Usually, the `++spoll` command has to be issued manually to obtain this information.*\n

        *When `++srqauto` is set to 0 (default), in order to obtain the status byte when `SRQ` is asserted, a serial poll has to be conducted manually using the `++spoll` command.*\n

        *When `++srqauto` is set to 1, the interface will automatically detect when the `SRQ` signal has been asserted by an instrument and will automatically conduct a serial poll, returning the address and status byte of the first instrument encountered that has the `RQS` bit set in its status byte. If multiple instruments have asserted `SRQ`, then another subsequent serial poll will be conducted to determine the next instrument that has requested service. The process continues until all instruments that have requested service have had their status byte read and the `SRQ` signal has been cleared.*

        **AR488 must be in `controller` mode for this to take effect.**
        
        Args:
            enable (bool | int): True/False or 1/0 to enable or disable automatic serial polling.

        Raises:
            ValueError: If `enable` is set incorrectly.
        ------------------------------------------------------------
        Implementation of `++srqauto` with no arguments.\n
        *Without parameters, this command returns the present status of the `SRQauto`. It returns 0 if a serial poll is not automatically executed (default) and 1 if a serial poll is automatically executed.*
        Returns:
            srqauto (int|None): 0 or 1 indicating if SRQauto is enabled or None of not available.
        """
        srqauto = self.query("++srqauto")
        try:
            srqauto = int(srqauto)
            return srqauto
        except:
            log.warning(f"AR488:Can not check if SRQauto is enabled, got: '{srqauto}'")
            warn(f"AR488:Can not check if SRQauto is enabled, got: '{srqauto}'")
            return None
    @auto_Service_ReQuest.setter
    def auto_Service_ReQuest(self, enable:bool|int) -> None:    #   TODO: Understand behavior!
        if enable or enable==1:
            self.write("++srqauto 1")
            return
        elif not enable or enable==0:
            self.write("++srqauto 0")
            return
        else:
            raise ValueError(f"AR488:auto_Service_ReQuest:enable must be True/False or 1/0 not '{enable}'")
        
    @property
    def talk_only(self) -> int|None:
        """
        Implementation of `++ton` with an integer argument.\n
        *The `++ton` command configures the controller to send data only on the GPIB bus. When in this mode, the interface does not require to have a GPIB address assigned and the address that is set will be ignored. Data is placed on the GPIB bus as soon as it is received via USB. Only one sender can exist on the bus, but multiple receivers can listen to and accept the transmitted data. The interface can send, but not receive, so effectively becomes a “talk-only” device. When issued without a parameter, the command returns the current state of “ton” mode.*

        **AR488 must be in `device` mode for this to take effect.**
        
        Args:
            enable (bool | int): True/False or 1/0 to enable or disable "talk-only" behaviour.

        Raises:
            ValueError: If `enable` is set incorrectly.
        ------------------------------------------------------------
        Implementation of `++ton` with no arguments.\n
        *When issued without a parameter, the command returns the current state of “ton” mode.*
        Returns:
            ton (int | None): 0 or 1 indicating if "talk-only" mode is enabled or None if not available.
        """
        ton = self.query("++ton")
        try:
            ton = int(ton)
            return ton
        except:
            log.warning(f"AR488:Can not check if talk-only is enabled, got: '{ton}'")
            warn(f"AR488:Can not check if talk-only is enabled, got: '{ton}'")
            return None
    @talk_only.setter
    def talk_only(self, enable:bool|int) -> None:
        if enable or enable==1:
            self.write("++ton 1")
            return
        elif not enable or enable==0:
            self.write("++ton 0")
        else:
            raise ValueError(f"AR488:talk_only:enable must be True/False or 1/0 not '{enable}'")

    def serial_poll_all(self) -> str:
        """Implementation of `++aspoll`.\n
        *Alias equivalent to `++spoll all`. See `++spoll` for further details.*

        Returns:
            aspoll (str): The answer of the AR488 in the format of `SRQ:addr,status` for the first instrument the AR488 encounters that has the `RQS` bit set in its status byte.
        """
        return self.query(f"++aspoll")
    
    def Device_CLear(self) -> None:
        """Implementation of `++dcl`.\n
        *Send Device Clear (`DCL`) to all devices on the GPIB bus.*

        **AR488 must be in `controller` mode for this to take effect.**
        """
        self.write("++dcl")

    def default(self) -> None:
        """Implementation of `++default`.\n
        *This command resets the AR488 to its default configuration.*\n

        *When powered up, the interface will start with default settings in controller mode. However, if the configuration has been saved to EEPROM using the savecfg command, the controller will start with the previously saved settings. This command can be used to reset the controller back to its default configuration.*\n

        *The interface is set to controller mode with the following parameters:*\n
        
        - ***auto**:	    0*
        - ***eoi**:	        0 (disabled)*
        - ***eor**:	        0 (CR+LF)*
        - ***eos**:	        0 (CR+LF)*
        - ***eot_enable**:	0 (disabled)*
        - ***eot_char**:	0*
        - ***GPIB**:	    address - controller 0*
        - ***GPIB**:	    address - primary 1*
        - ***GPIB**:	    address - secondary 0*
        - ***mode**:	    controller*
        - ***read_tmo_ms**:	1200*
        - ***status**:	    byte 0*
        - ***version**:	    string default version string*
        
        ***Note:***\n
        *`Unless the ++savecfg command is used to overwrite the previously saved configuration, the previous configuration will be re-loaded from non-volatile memory the next time that the interface is powered up. To ensure that settings are saved, after using the ++default command, configure the interface as required and then use ++savecfg to save the settings to EEPROM*. The interface can be returned to its default state by using ++default followed by ++savecfg without making any further configuration changes.`*\n

        - *this assumes that the board being used supports saving to EEPROM.*
        """
        self.write("++default")
        
    def repeat(self, count:int, delay:int, command:str) -> None:
        """Implementation of `++repeat` with integer and string arguments.\n
        *Provides a way of repeating the same command multiple times, for example, to request multiple measurements from the instrument.*\n

        *Between 2 and 255 repetitions can be requested. It is also possible to request a delay between 0 to 10,000 milliseconds (or 10 seconds) between each repetition. The parameter buffer has a maximum capacity of 64 characters, so the command string plus any parameters cannot exceed 64 characters in total. Once started, there is no mechanism to stop the repeat loop once it has begun.*\n

        *The command will run the number of iterations requested and stop only when the request is complete.*

        **AR488 must be in `controller` mode for this to take effect.**
        
        Args:
            count (int): Number of repeats between 2 to 255.
            delay (int): Delay in milliseconds in range 0 to 10000.
            command (str): Command string send to the addressed device.

        Raises:
            ValueError: If `count` or `delay` are set incorrectly.
        """
        if count > 1 and count < 256 and delay >=0 and delay <= 10000:
            self.write(f"++repeat {count} {delay} {command}")
        else:
            raise ValueError(f"AR488:repeat:cont must be in range 2-255, delay must be in range 0-10000, but got count '{count}' and delay '{delay}'")
    
    def take_control(self, address:int) -> None:    #TODO: Understand how this should work.
        """Implementation of `++tct` with an integer argument.\n

        *Send the Take Control (TCT) message to the device given as argument to make it the new Controller in Charge. If no error occurs during the execution of the Take Control sequence, the AR488 is set in Device mode automatically. It´s (for now) the responsibility of the user to detect when the Active Controller has finished his job and the Controller In Charge has been passed back to the AR488 (typically the device that took control will send a SRQ message).*

        Args:
            address (int): The GPIB address of the AR488 that should be taken control of.

        Raises:
            ValueError: If address is set incorrectly.
        """
        addr = None
        if type(address) == int and address > 0 and address < 30:
            addr = address
            self.write(f"++tct {addr}")
        else:
            raise ValueError(f"AR488:take_control:address is not valid can only be an integer in range 1-29 not '{address}'")
    

    def delay_bus(self, microseconds:int) -> None:
        """Implementation of `++tmbus` with an integer argument.\n
        *The GPIB bus protocol is designed to allow the bus to synchronise to the speed of the slowest device. However, under some circumstances it may be desirable to slow down the bus. The `tmbus` parameter introduces a periodic delay of between 0 to 30,000 microseconds between certain operations on the bus and so slows down the operation of the GPIB bus. The greater the delay, the slower the bus will operate. Under normal running conditions this parameter should be set to zero, which is the default setting.*
        
        Args:
            microseconds (int): Periodic delay of the GPIB bus in range of 0-30000.

        Raises:
            ValueError: If `microseconds` is set incorrectly.
        """
        if microseconds >= 0 and microseconds <= 30000:
            self.write(f"++tmbus {microseconds}")
        else:
            raise ValueError(f"AR488:delay_bus:microseconds must be an integer between 0 and 30000 not '{microseconds}'")
    
    ### Communication backend
    def write(self, command:str, **kwargs) -> None:
        """Write a command to the AR488 using `pyvisa`.

        Args:
            command (str): The command.
            kwargs (dict): Additional variables send to the pyvisa write function.
        """
        self._wait_for_buffer_time()
        self.resource.write(message=command, **kwargs)
        tmo = [self.resource.timeout].copy()    #   make a true value copy instead of taking a pointer to this value as it is getting changed below
        try:    #   check if written command was received
            self.resource.timeout = int(self.buffer_delay*1E3)  #   reduce timeout for testing if a command is recognised or not
            self.command_recognised(command=command,message=self.read_resource())
        except:
            pass
        self.resource.timeout = tmo[0]
            
    def query(self, command:str, **kwargs) -> str:
        """Query / ask the AR488 using `pyvisa` with the query delay being the `self.query_delay` defined in the constructor.

        Args:
            command (str): The command.
            kwargs (dict): Additional variables send to the pyvisa query function. If `"delay"` is included it will overwrite the `self.query_delay` for this operation only.

        Returns:
            str: The raw answer of the AR488 to the `command`.
        """
        delay = self.query_delay
        if "query_delay" in kwargs.keys():
            delay = kwargs["query_delay"]
            del kwargs["query_delay"]
        self._wait_for_buffer_time()
        answer = self.resource.query(message=command, delay=delay, **kwargs).strip()
        self.command_recognised(command=command,message=answer)
        return answer
    
    def read_resource(self, **kwargs) -> str:
        """Read the AR488 using `pyvisa`.

        Args:
            kwargs (dict): Additional variables send to the pyvisa read function.

        Returns:
            str: The raw answer of the AR488 to the `command`.
        """
        self._wait_for_buffer_time()
        return self.resource.read(**kwargs).strip()
    
    def command_recognised(self, command:str, message:str) -> bool:
        """Checks if the send command was recognised. If message is "Unrecognized command" will return False.

        Args:
            command (str): The command send, to be shown to the user in the log.
            message (str): Message recieved from the device.

        Returns:
            bool: Validity.
        """
        if "Unrecognized command" in message.strip():
            log.error(f"AR488:Command '{command}' was not recognised!")
            warn(f"AR488:Command '{command}' was not recognised!")
            return False
        else:
            return True
    
    def _wait_for_buffer_time(self) -> None:
        time_delta = time.time() - self._last_write
        if time_delta < self.buffer_delay:
            time.sleep(self.buffer_delay-time_delta)
        self._last_write = time.time()

    ### Presentation
    def __repr__(self):
        return self.version()
    
    def __str__(self):
        return f"{self.version(True)} at {self.descriptor}"

class AR488Adapter(VISAAdapter):
    #   TODO: Fix read UnicodeDecodeError of pyvisa when reading from device
    """A wrappter of the `pymeasure` VISAAdapter class to work with an `AR488<https://sdfa3.org/david/ar488.html>`__ GPIB adapter.\n
    Automatically configures the AR488 to `auto 0` to mitigate "Query Untermianted" error and allows classes that inherit or use this adapter for reading data (e.g. the `ask` function) to automatically use the AR488 `++read` command. Furthermore the `ar488` attritute can be used to program the AR488.
    
    Attributes
    ----------
    ar488 : AR488
        The AR488 class used for reading and writing data with `read` and `write`. Note some functionalities like reading/writing binary or bytes are not directly supported by the AR488 and thus use the standard `pymeasure` VISAAdapter implementation.
    """
    ar488 : AR488
    default_termination : int|str|None = "eoi"
    number_of_read_attempts : int = 1
    auto_mode : int = 0
    _last_command : str = ""
    _ar488_overwrite_visa_commands : list[str] = ["read_termination","write_termination","send_end"]    # commands that the pyvisa library cant set for a serial port but the AR488 can understand
    def __init__(self, resource_name:str, visa_library:str='', auto_mode:int=0, default_termination : int|str|None = "eoi", reading_attempts:int=1, log:logging.Logger=None, **kwargs):
        """A wrappter of the `pymeasure` VISAAdapter class to work with an `AR488<https://sdfa3.org/david/ar488.html>`__ GPIB adapter.\n
        Automatically configures the AR488 to `auto 0` to mitigate "Query Untermianted" error and allows classes that inherit or use this adapter for reading data (e.g. the `ask` function) to automatically use the AR488 `++read` command. Furthermore the `ar488` attritute can be used to program the AR488.
        
        Adapter class for the VISA library, using PyVISA to communicate with instruments.

        The workhorse of our library, used by most instruments.

        Args:
            resource_name (str): 
                A `VISA resource string <https://pyvisa.readthedocs.io/en/latest/introduction/names.html>`__ or GPIB address integer that identifies the target of the connection
            visa_library (str):
                PyVISA VisaLibrary Instance, path of the VISA library or VisaLibrary spec string (``@py`` or ``@ivi``). If not given, the default for the platform will be used.
            auto_mode (int):
                1 / 0 to enable / disable auto forwarding, and 2 & 3 for "on-query" and "continuouse" mode, see `AR488.auto` or `++auto` documentation.
            default_termination (int | str | None):
                Termination used by the AR488 `++read` function, can be "eoi" to read until the EOI signal, an ASCII character or its integer value where the value must be less than 256 or None to read until the timeout occurs. Will be defined when using `kwargs` to define "read_termination" but can be overwritten with this variable. Defaults to None.
            reading_attempts (int):
                Number of attempts made to read data from the AR488, wait `timeout` inbetween attempts.
            log (logging.Logger):
                Parent logger of the 'Adapter' logger.
            kwargs (dict):
                Keyword arguments for configuring the PyVISA connection.

        :Kwargs:
            Keyword arguments are used to configure the connection created by PyVISA. This is
            complicated by the fact that *which* arguments are valid depends on the interface (e.g.
            serial, GPIB, TCPI/IP, USB) determined by the current ``resource_name``.

            The implementation for the AR488 also allows to configure properties of the AR488 class within of `kwargs`. Additionally the `kwargs` arguments for pyvisa: `read_termination`, `write_termination`, `timeout`, `query_delay` and `send_end` are configured to modify the appropriate AR488 properties similarly as the `pyvisa` backend would for a real GPIB adapter.

            A flexible process is used to easily define reasonable *default values* for
            different instrument interfaces, but also enable the instrument user to *override any
            setting* if their situation demands it.

            A kwarg that names a pyVISA interface type (most commonly ``asrl``, ``gpib``, ``tcpip``, or
            ``usb``) is a dictionary with keyword arguments defining defaults specific to that
            interface. Example: ``asrl={'baud_rate': 4200}``.

            All other kwargs are either generally valid (e.g. ``timeout=500``) or override any default
            settings from the interface-specific entries above. For example, passing
            ``baud_rate=115200`` when connecting via a resource name ``ASRL1`` would override a
            default of 4200 defined as above.

            See :ref:`connection_settings` for how to tweak settings when *connecting* to an instrument.
            See :ref:`default_connection_settings` for how to best define default settings when
            *implementing an instrument*.
        """
        pyvisa_kwargs = {}
        for arg in kwargs.keys():
            if hasattr(pyvisa.resources.Resource, arg) and arg not in self._ar488_overwrite_visa_commands:
                pyvisa_kwargs[arg] = kwargs[arg]

        super().__init__(resource_name, visa_library, log, **pyvisa_kwargs)
        
        self.ar488 = AR488(resource=self.connection)

        for arg in kwargs.keys():
            var = [kwargs[arg]].copy()[0]
            #   AR488 owned attributed
            if hasattr(self.ar488, arg):    
                setattr(self.ar488, arg, var)
            #   VISA arguments that are not supported by a serial port but the AR488 can immitate
            elif arg == "read_termination":
                self.ar488.End_Of_Termination = 1
                self.ar488.End_Of_Termination_CHARacter = var
                self.default_termination = var
            elif arg == "write_termination":
                self.ar488.End_Of_Send = var
            elif arg == "send_end":
                self.ar488.End_Of_Interrupt = var
            #   Arguments that a pyvisa serial port and the AR488 can understand
            elif arg == "timeout":
                self.ar488.read_timeout = var
            elif arg == "query_delay" or arg == "wait_for":
                self.ar488.query_delay = var
            

        # bring AR488 into stable state and set it to controller mode with auto forewarding disabled to mitigate "Query Unterminated" errors
        if default_termination is not None and self.default_termination is None:
            self.default_termination = default_termination
            self.ar488.End_Of_Termination = 1
            if ord(default_termination) != self.ar488.End_Of_Termination_CHARacter:
                self.ar488.End_Of_Termination_CHARacter = default_termination

        self.number_of_read_attempts = reading_attempts
        if auto_mode != 0:
            self.ar488.mode = 1
        self.ar488.auto = auto_mode
        self.auto_mode = auto_mode
    
    # Wrapper functions for the Adapter object
    def write(self, command:str, **kwargs) -> None:
        """Write a string command to the instrument appending `write_termination`.

        :param command: command string to be sent to the instrument
        :param kwargs: Keyword arguments for the ar488 write function.
        """
        self._last_command = command
        self.ar488.write(command, **kwargs)

    def write_bytes(self, content, **kwargs):
        """Write the bytes `content` to the instrument."""
        warn((f"AR488Adapter:ar488:writing bytes is not a functionality of the AR488 adapter."))
        super().write_bytes(content, **kwargs)

    def read(self, **pyvisa_kwargs) -> str:
        """Read up to (excluding) `self.default_termination` for the `++read` for the whole read buffer.\n
        Attempts to use the AR488's `++read` functionality when `auto 0` else read using pyvisa.\n
        When reading with `++read` will automatically adjust AR488 to read with the provided terminator (`self.default_termination`) by avoiding using the timeout due to slow measurements.
        
        Args:
            **pyvisa_kwargs (Any): Arguments for the `pyvisa` read function, including `termination` or `read_termination`.

        Returns:
            answer (str): The answer of the addressed device as string or `"Reading Error"` if AR488 or pyvisa failed to read data.
        
        Raises:
            ValueError: If the AR488 does not respond after `self.number_of_read_attempts` attempts.
        """
        
        answer = "Reading Error"
        reading_attempt = 0
        successfull = False
        while not successfull and reading_attempt < self.number_of_read_attempts:
            reading_attempt += 1
            try:
                if self.auto_mode == 0:
                    answer = self.ar488.read(self.default_termination)
                else:
                    answer = self.ar488.read_resource(**pyvisa_kwargs)
                successfull = True
            except Exception as error:
                log.error(f"AR488Adapter:Reading data after command '{self._last_command}' at attempt {reading_attempt} failed due to an error: {error}")
                warn(f"AR488Adapter:Reading data after command '{self._last_command}' at attempt {reading_attempt} failed due to an error: {error}")
                if reading_attempt < self.number_of_read_attempts:
                    time.sleep(self.ar488.query_delay)
        if not successfull:
            raise IOError(f"AR488Adapter could not read from AR488 after {self.number_of_read_attempts} attempts!")
        else:
            return answer

    def read_bytes(self, count, **kwargs):
        """Read a certain number of bytes from the instrument.

        :param int count: Number of bytes to read. A value of -1 indicates to
            read the whole read buffer.
        :param kwargs: Keyword arguments for the adapter.
        :returns bytes: Bytes response of the instrument (including termination).
        """
        warn(f"AR488Adapter:reading bytes is not a functionality of the AR488 adapter.")
        return super().read_bytes(count, **kwargs)

    def write_binary_values(self, command, values, *args, **kwargs):
        """Write binary values to the device.

        :param command: Command to send.
        :param values: The values to transmit.
        :param \\*args, \\**kwargs: Further arguments to hand to the Adapter.
        """
        warn(f"AR488Adapter:writing binary values is not a functionality of the AR488 adapter.")
        super().write_binary_values(command, values, *args, **kwargs)

    def read_binary_values(self, **kwargs):
        """Read binary values from the device."""
        warn(f"AR488Adapter:reading binary values is not a functionality of the AR488 adapter.")
        return super().read_binary_values(**kwargs)
    
    def ask(self, command:str) -> str:
        """ Writes the command to the instrument and returns the resulting
        ASCII response

        .. deprecated:: 0.11
           Call `Instrument.ask` instead.

        :param command: SCPI command string to be sent to the instrument
        :returns: String ASCII response of the instrument
        """
        warn("`Adapter.ask` is deprecated, call `Instrument.ask` instead.", FutureWarning)
        self.write(command=command)
        time.sleep(self.ar488.query_delay)
        return self.read()
    
    def __repr__(self):
        return "<AR488Adapter(resource='%s')>" % self.ar488.descriptor
    
    def __str__(self):
        return f"AR488Adapter: {self.ar488.__str__()}"