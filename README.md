STM32Loader
===========

Python script which will talk to the STM32 native bootloader to upload
and download firmware.

Original Version by: Ivan A-R <ivan@tuxotronic.org>.


Usage
-----

```
./stm32loader.py [-hqVewvr] -p port [-l length] [-b baud] [-a address] [file.bin]
    -h          This help
    -q          Quiet
    -V          Verbose
    -e          Erase (note: this is required on previously written memory)
    -w          Write
    -v          Verify (recommended)
    -r          Read
    -p port     Serial port (example: /dev/tty.usbserial-ftCYPMYJ or COM5)
    -l length   Length of read
    -b baud     Baud speed (default: 115200)
    -a address  Target address
    -g address  Address to start running at (0x08000000, usually)
```


Example
-------

```
stm32loader.py -p /dev/tty.usbserial-ftCYPMYJ -e -w -v somefile.bin
```

This will pre-erase flash, write `somefile.bin` to the flash
on the device, and then perform a verification after writing is finished.
