# <center>Installing linux-GPIB</center>

I successfully installed linux-gpib-4.3.7 on Kernel 6.17.0 for Ubuntu 24.04 / Mint 22.02 (6.17.0-14-generic).

### Required installations:
- <strong>I. Kernel drivers (2 possibilities)
- II. User space files
- III. Firmware</strong>

I.2, II and III are discussed in the appropriate "INSTALL" files in the linux-gpib-4.3.7 folder.
III is further discussed in https://www.cl.cam.ac.uk/~osc22/tutorials/gpib_usb_linux.html.<br>
Independent of the method in I. you will need to download the linux-gpib-4.3.7 files. Here: https://linux-gpib.sourceforge.io/ or https://github.com/coolshou/linux-gpib.

### BACKUP all existing files that are changed / modified in any of the below steps!

For the kernel part (see linux-gpib-kernel-4.3.7/INSTALL) or:
## I.1) Build custom kernel
<p><strong>Only possible for kernels version >= 6.13! WILL TAKE MANY HOURS TO COMPLETE building</strong>.<br>
For me the only functioning solution was to compile a whole kernel with the built-in GPIB drivers in the linux kernel which are not installed by default.</p>
    
Making the "custom" kernel (Ubuntu kernel 6.17.0 for me with Mint 22.02. using kernel 6.17.0-14-generic):<br>
I followed https://phoenixnap.com/kb/build-linux-kernel as shown below.

1. Install the build-tools for your system, for me (it is possible that the command below will not give you all necessary tools for building the kernel, if the build fails you have to do your own research based on your distro and kernel, for me some other libraries were missing when using a different method of installing linux-gpib, I am not sure if they impacted the kernel build!):<br>`$ sudo apt-get install fakeroot build-essential devscripts libncurses5 libncurses5-dev`

2. Download the kernel source from your appropriate repository into a user space folder, ideally you use the same or similar kernel as your system is already running.
   
3. Extract the downloaded .tar.gz file.
   
4. Navigate into the extracted folder (in the following: kernel source folder).
   
5. Copy the existing config file your system is actively running with or the one most similar to the downloaded kernel from the /boot folder (for me that was /boot/config-6.17.0-14-generic) into the kernel source folder as .config, i.e.:<br>``$ sudo cp /boot/config-`uname -r` ./.config``<br>or<br>``$ sudo cp /boot/config-x.x.x ./.config``
   
6. For Ubuntu specifically: Disable trusted keys:<br>Open the newly copied .config file and navigate to "CONFIG_SYSTEM_TRUSTED_KEYS" and "SYSTEM_REVOCATION_KEYS" and replace the string with empty strings:<br>It should be:<br>`CONFIG_SYSTEM_TRUSTED_KEYS=""`<br>`CONFIG_SYSTEM_REVOCATION_KEYS=""`
   
7. Ensure .config is up to date with:<br>`$ make oldconfig`<br>Enter as you wish, I just pressed ENTER on all the questions.

8. Configure Makefile to get the name of the kernel you want it to be, open the Makefile in the kernel source folder and enter under EXTRAVERSION<br>For me `EXTRAVERSION = -14-gpib` resulted in kernel name 6.17.0-14-gpib

9.  Configure the kernel to include the GPIB drivers: Enter the menuconfig utility:<br>`$ make menuconfig`<br>Navigate with ENTER and TAB to drivers -> staging drivers -> gpib (newer kernels: drivers -> gpib)<br>Add gpib by pressing M, enter gpib and select necessary drivers (gpib core + at least the ni drivers, I added all of the possibilities) by pressing M. Save into .config with TAB to `<Save>`. Exit.
    
10. Build the kernel (can take very long ~ hours, for me at least 6 hours under highest power settings):<br>`$ make`
    
11. Build kernel modules (also takes long ~ hours):<br>`$ sudo make modules_install`
    
12. Install kernel:<br>`$ sudo make install`

13. Update bootloader (kernel name should now be listed in /lib/modules)<br>`$ sudo update-initramfs -c -k <name you have given your kernel, for me 6.17.0-14-gpib>`<br>`$ sudo update-grub`
    
14. <strong>Read this step before following it!</strong><br>Test and debug. Ensure you can change kernels on boot (with grub) because the kernel might not work out of the box. Otherwise you might have to use a recovery USB stick.<br>Restart and try booting into the new kernel, it should be listed in grub.<br>I got a <strong>KERNEL PANICK</strong> on first boot: <em>"VFS: Unable to mount root fs on unknown-block(0,0)"</em>. The fix for me which enabled the boot, BUT made booting into the kernel much slower: https://unix.stackexchange.com/questions/717619/linux-mint-5-15-0-47-generic-error-out-of-memory-when-booting:<br>Navigate to your initramfs.conf ("nano" is my text editor):<br>```$ sudo nano /etc/initramfs-tools/initramfs.conf```<br>Replace some of the existing variables (keep the old ones with a comment):<br>`MODULES=dep`<br>`COMPRESS=xz`<br>Update initramfs:<br>`$ sudo update-initramfs -u`<br>This worked for me.

15. Test by rebooting and running<br>`$ modprobe tnt4882`<br>`$ modprobe ni_usb_gpib`<br>If you dont get the error <em>"Exec format error"</em> the installation was probably successful. I always get <em>"libkmod: ERROR ../libkmod/libkmod-config.c:712 kmod_config_parse: /etc/modprobe.d/gpib_modprobe.conf line 4: ignoring bad line starting with 'wait;'"</em> but it works anyways.

## I.2) Installing linux-gpib-4.3.7 drivers in existing kernel:
Not successfull for me, but try it using the INSTALL file in the linux-gpib-4.3.7/linux-gpib-kernel-4.3.7 folder.

## II) Install user space part:
Ensure you are using a kernel that has the kernel drivers from part I) installed. Verify with<br>```$ uname -r```<br>Cross check the name with I.1) your custom kernel or I.2) the kernel that the linux-gpib-kernel-4.3.7 drivers are installed in. You can just follow the INSTALL file in linux-gpib-4.3.7/linux-gpib-user-4.3.7, below are listed the steps as they worked for me.

1. Navigate to the linux-gpib-4.3.7/linux-gpib-user-4.3.7 (in the following: user folder).

2. In the user folder create ./configure script if not already there with<br>`$ ./bootstrap`
   
3. Configure with the system configure directory of your distro, for me: /etc:<br>`$ ./configure --sysconfdir=/etc`
   
4. Clean the space if necessary with `$ make clean`
   
5. Make the files: <br>`$ make`
   
6. Install:<br>`$ sudo make install`
   
7. Verify that the folder containing the file "libgpib.so" is listed in the file "/etc/ld.so.conf". If not add it into the ld.so.conf file, I had to add "/usr/lib".<br>Update the config with `$ ldconfig`
   
8. Usually linux-gpib wants its own group calles "gpib" (listed in the udev rules in /etc/udev/rules.d/98-gpib-generic.rules), add it using:<br>`$ groupadd gpib`<br>If not configured differently, the firmware (discussed below) will want the group "plugdev" add it aswell or change the configuration as I did to "gpib" wherever it says "plugdev".<br>Add yourselve to the group/s by adding your name behind them in the /etc/group file.<br>You can also change the default group in the /etc/udev/rules.d/98-gpib-generic.rules file.
   
9.  Add the device ports that gpib adapters will be listed as in /dev using:<br>`$ sudo make device_files_install`<br>Should create /dev/gpibx (x=0,...,15)<br>If you did the permissions correctly you should not have to repeat this step every time you plug in a GPIB adapter!<br>I had issues with this as my /dev/gpibx disappeared between log-ins and did not appear again after plugging in a GPIB adapter.<br>I solved this by adding a file into /etc/modprobe.d (I called it "gpib_modprobe.conf"). In this file I added the following lines (from this forum post: https://linux-gpib-general.narkive.com/4ky0VDDi/making-file-pemissions-dev-gpib0-permanent):<br>`alias char-major-160 gpib_common`<br>`alias gpib0 tnt4882`<br>`install tnt4882 /sbin/modprobe --ignore-install tnt4882; wait; sleep 6;`<br>`wait; /usr/local/sbin/gpib_config --minor 0`<br>Now when plugging in a GPIB device you just have to wait 6 seconds and the /dev/gpibx devices appear and can be used with gpib_config used by the firmware loader (you will see this command in step III when accessing the /usr/local/lib/udev/gpib_udev_fxloader file)
    
10. The installation of the user space part is completed, but for the NI USB B adapter you will need firmware from III).
    
11. Test it by running<br>`$ gpib_config`<br>If you dont have a GPIB adapter plugged in this will return an error but as long as it complains about a missing device and not that "gpib_config" is missing you should be fine.<br>Try <br>`$ ibtest`<br>You dont need to do anything here as you dont have firmware installed yet but if the command does not fail immediately the installation probably worked.<br>You could try an adapter like the NI USB HS (3923/709b) that does not require a firmware and use ibtest to communicate with connected devices if you want further testing before installing firmware and modifying existing config files as done in III).

## III) Firmware:
You will also need the firmware for the NI USB B adapter:
- Nova: NI USB B (3923/702b)
- Blue Oxford Kryo: NI USB HS (3923/709b)<br>
Test which one you need by plugging it in and running<br>
`$ lsusb`<br>
Follow https://www.cl.cam.ac.uk/~osc22/tutorials/gpib_usb_linux.html if below does not work.<br>
1. Download the firmware "linux_gpib_firmware"
   
2. Rename "ni_gpib_usb_b" to "ni_usb_gpib"
   
3. Copy all folders into /lib/firmware
   
4. Modify the default firmware loader config in /usr/local/lib/udev/gpib_udev_fxloader.
<br>Change DATADIR to the firmware folder:<br>`DATADIR=/lib/firmware`

<br>Change all occurences of "$ DATADIR/usb/" to "$ DATADIR/".
<br>Add the loader for the ni-usb-b and ni-usb-hs firmware by adding the following into the "case $PRODUCT in" statement:<br>
```
# ni-usb-b with firmware
3923/702a/*)
if [ -x /usr/bin/logger ]; then
        /usr/bin/logger -t $0 "Running gpib_config for $PRODUCT"
fi
        gpib_config $GPIB_CONFIG_OPTIONS
        ;;
# ni-usb-hs
3923/709b/*)
if [ -x /usr/bin/logger ]; then
        /usr/bin/logger -t $0 "Running gpib_config for $PRODUCT"
fi
        gpib_config $GPIB_CONFIG_OPTIONS
        ;;
```

5. Modify the /etc/gpib.conf file: I replaced everything in that file with the following:<br>
```
interface {
        minor = 0               /* interface config for /dev/gpib0 */
        board_type = "ni_pci"   /* type of interface board being used */
        name = "L0"             /* optional name, allows you to get a board descriptor using ibfind() */
        pad = 0                 /* primary address of interface */
        sad = 0
        eos = 0x0a              /* end of string is line-feed */
        set-eot = yes           /* send EOI at end of writes */
        timeout = T3s           /* timeout for commands */
        master = yes            /* board is system controller */
        set-xeos = no
}
```

6. Modify the rules in /etc/udev/rules.d/99-ni_usb_gpib.rules. The device 3923 should have both a and b support, as we now have a firmware installed, i.e. replace "702a" with "702[ab]" so that you have the following first line:<br>`SUBSYSTEM=="usb", ACTION=="add", ATTR{idVendor}=="3923", ATTR{idProduct}=="702[ab]", ENV{DEVICE}="$devnode", RUN+="/usr/local/lib/udev/gpib_udev_fxloader"`<br>I also have a file named /etc/udev/rules.d/99-linux_gpib_ni_usb.rules containing the following:<br>
```
SUBSYSTEM=="usb", ACTION=="add", ENV{DEVTYPE}=="usb_device", ATTR{idVendor}=="3923", ATTR{idProduct}=="702[ab]", MODE="660", GROUP="plugdev", SYMLINK+="usb_gpib"
SUBSYSTEM=="usb", ACTION=="add", ENV{DEVTYPE}=="usb_device", ATTR{idVendor}=="3923", ATTR{idProduct}=="702[ab]", RUN+="/lib/udev/ni_usb_gpib"
KERNEL=="gpib[0-9]*", ACTION=="add", MODE="660", GROUP="plugdev"
```
For this you will need the "plugdev" group or just change it to "gpib".

7. Install fxload:<br>`$ sudo apt-get install fxload`<br>As you could see there is firmware for more adapters, I suspect you could make those (like Agilent ones) work the same way as we did here for NI, by modifying the /usr/local/lib/udev/gpib_udev_fxloader similarly to 4.

## Testing
1. Reboot into the kernel that has the GPIB support

2. Plug in the GPIB adapter and see if it shows up with<br>`$ lsusb`<br>Name should contain 3923 (national istruments adapter) and 702a, 702b or 709b

3. Check if /dev/gpibx is showing up, if not, you might not have permission to access the group "gpib" or the "gpib_config" tool has not been loaded on boot, check out II-9.) again.

4. Test it using <br>`$ ibtest`<br>Select d (device), turn on a device with known primary GPIB address<br>Enter the address<br>Press w for writing<br>Write `*IDN?`<br>Press r for reading<br>Input a number (like 100) in the given range<br>Should return the identification of the device (if SCPI conform)<br>If this fails then the installation did not work. Check if all the files are modified correctly (see above) or follow the installation tutorials for the firmware, especially https://www.cl.cam.ac.uk/~osc22/tutorials/gpib_usb_linux.html.<br>You might need to play around with any or all of the above mentioned config files from III) to load the firmware with fxload automatically. Alternatively you could try loading the firmware manually with fxload but that would be tediouse as it has to be repeated every time you plug in a GPIB device.