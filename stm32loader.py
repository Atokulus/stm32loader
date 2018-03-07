#!/usr/bin/env python

# -*- coding: utf-8 -*-
# vim: sw=4:ts=4:si:et:enc=utf-8

# Author: Ivan A-R <ivan@tuxotronic.org>
# GitHub repository: https://github.com/jsnyder/stm32loader
#
# This file is part of stm32loader.
#
# stm32loader is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free
# Software Foundation; either version 3, or (at your option) any later
# version.
#
# stm32loader is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License
# for more details.
#
# You should have received a copy of the GNU General Public License
# along with stm32loader; see the file COPYING3.  If not see
# <http://www.gnu.org/licenses/>.

from functools import reduce
import sys
import getopt
import serial
import time


# Verbose level
QUIET = 20

CHIP_IDS = {
    # see ST AN2606
    0x412: "STM32 Low-density",
    0x410: "STM32 Medium-density",
    0x414: "STM32 High-density",
    0x420: "STM32 Medium-density value line",
    0x428: "STM32 High-density value line",
    0x430: "STM32 XL-density",
    0x416: "STM32 Medium-density ultralow power line",
    0x411: "STM32F2xx",
    0x413: "STM32F4xx",
}


def debug(level, message):
    if QUIET >= level:
        print(message, file=sys.stderr)


class CmdException(Exception):
    pass


class CommandInterface:

    class Command:
        # See ST AN3155
        GET = 0x00
        GET_VERSION = 0x01
        GET_ID = 0x02
        READ_MEMORY = 0x11
        GO = 0x21
        WRITE_MEMORY = 0x31
        ERASE = 0x43
        EXTENDED_ERASE = 0x44
        WRITE_PROTECT = 0x63
        WRITE_UNPROTECT = 0x73
        READOUT_PROTECT = 0x82
        READOUT_UNPROTECT = 0x92

    class Reply:
        # See ST AN3155
        ACK = 0x79
        NACK = 0x1F
        EXTENDED_ERASE = 0x44

    extended_erase = 0

    def __init__(self):
        self.serial = None

    def open(self, a_port='/dev/tty.usbserial-ftCYPMYJ', a_baud_rate=115200):
        self.serial = serial.Serial(
            port=a_port,
            baudrate=a_baud_rate,
            bytesize=8,             # number of write_data bits
            parity=serial.PARITY_EVEN,
            stopbits=1,
            xonxoff=0,              # don't enable software flow control
            rtscts=0,               # don't enable RTS/CTS flow control
            timeout=5               # set a timeout value, None for waiting forever
        )

    def reset(self):
        self.serial.setDTR(0)
        time.sleep(0.1)
        self.serial.setDTR(1)
        time.sleep(0.5)

    def init_chip(self):
        # Set boot
        self.serial.setRTS(0)
        self.reset()

        # Syncro
        self.serial.write(b'\x7F')
        return self._wait_for_ack("Syncro")

    def release_chip(self):
        self.serial.setRTS(1)
        self.reset()

    def command(self, command):
        command_byte = bytes([command])
        control_byte = bytes([command ^ 0xFF])

        self.serial.write(command_byte)
        self.serial.write(control_byte)

        return self._wait_for_ack(hex(command))

    def get(self):
        if not self.command(self.Command.GET):
            raise CmdException("Get (0x00) failed")
        debug(10, "*** Get interface")
        length = self.serial.read()[0]
        version = self.serial.read()[0]
        debug(10, "    Bootloader version: " + hex(version))
        data = self.serial.read(length)
        if self.Reply.EXTENDED_ERASE in data:
            self.extended_erase = 1
        debug(10, "    Available commands: " + ", ".join(data))
        self._wait_for_ack("0x00 end")
        return version

    def get_version(self):
        if not self.command(self.Command.GET_VERSION):
            raise CmdException("GetVersion (0x01) failed")

        debug(10, "*** GetVersion interface")
        version = self.serial.read()[0]
        self.serial.read(2)
        self._wait_for_ack("0x01 end")
        debug(10, "    Bootloader version: " + hex(version))
        return version

    def get_id(self):
        if not self.command(self.Command.GET_ID):
            raise CmdException("GetID (0x02) failed")

        debug(10, "*** GetID interface")
        length = self.serial.read()[0]
        id_data = self.serial.read(length + 1)
        self._wait_for_ack("0x02 end")
        _device_id = reduce(lambda x, y: x*0x100+y, id_data)
        return _device_id

    def read_memory(self, address, length):
        assert(length <= 256)
        if not self.command(self.Command.READ_MEMORY):
            raise CmdException("ReadMemory (0x11) failed")

        debug(10, "*** ReadMemory interface")
        self.serial.write(self._encode_address(address))
        self._wait_for_ack("0x11 address failed")
        n = (length - 1) & 0xFF
        checksum = n ^ 0xFF
        self.serial.write(bytes([n, checksum]))
        self._wait_for_ack("0x11 length failed")
        return self.serial.read(length)

    def go(self, address):
        if not self.command(self.Command.GO):
            raise CmdException("Go (0x21) failed")

        debug(10, "*** Go interface")
        self.serial.write(self._encode_address(address))
        self._wait_for_ack("0x21 go failed")

    def write_memory(self, address, data):
        assert(len(data) <= 256)
        if not self.command(self.Command.WRITE_MEMORY):
            raise CmdException("Write memory (0x31) failed")

        debug(10, "*** Write memory interface")
        self.serial.write(self._encode_address(address))
        self._wait_for_ack("0x31 address failed")
        length = (len(data)-1) & 0xFF
        debug(10, "    %s bytes to write" % [length + 1])
        self.serial.write(bytes([length]))
        checksum = 0xFF
        for c in data:
            checksum = checksum ^ c
            self.serial.write(bytes([c]))
        self.serial.write(bytes([checksum]))
        self._wait_for_ack("0x31 programming failed")
        debug(10, "    Write memory done")

    def erase_memory(self, sectors=None):
        if self.extended_erase:
            return interface.extended_erase_memory()

        if not self.command(self.Command.ERASE):
            raise CmdException("Erase memory (0x43) failed")

        debug(10, "*** Erase memory interface")

        if sectors:
            self._page_erase(sectors)
        else:
            self._global_erase()
        self._wait_for_ack("0x43 erase failed")
        debug(10, "    Erase memory done")

    def extended_erase_memory(self):
        if not self.command(self.Command.EXTENDED_ERASE):
            raise CmdException("Extended Erase memory (0x44) failed")

        debug(10, "*** Extended Erase memory interface")
        # Global mass erase and checksum byte
        self.serial.write(b'\xFF')
        self.serial.write(b'\xFF')
        self.serial.write(b'\x00')
        tmp = self.serial.timeout
        self.serial.timeout = 30
        print("Extended erase (0x44), this can take ten seconds or more")
        self._wait_for_ack("0x44 erasing failed")
        self.serial.timeout = tmp
        debug(10, "    Extended Erase memory done")

    def write_protect(self, sectors):
        if not self.command(self.Command.WRITE_PROTECT):
            raise CmdException("Write Protect memory (0x63) failed")

        debug(10, "*** Write protect interface")
        self.serial.write(bytes([((len(sectors) - 1) & 0xFF)]))
        checksum = 0xFF
        for c in sectors:
            checksum = checksum ^ c
            self.serial.write(bytes([c]))
        self.serial.write(bytes([checksum]))
        self._wait_for_ack("0x63 write protect failed")
        debug(10, "    Write protect done")

    def write_unprotect(self):
        if not self.command(self.Command.WRITE_UNPROTECT):
            raise CmdException("Write Unprotect (0x73) failed")

        debug(10, "*** Write Unprotect interface")
        self._wait_for_ack("0x73 write unprotect failed")
        self._wait_for_ack("0x73 write unprotect 2 failed")
        debug(10, "    Write Unprotect done")

    def readout_protect(self):
        if not self.command(self.Command.READOUT_PROTECT):
            raise CmdException("Readout protect (0x82) failed")

        debug(10, "*** Readout protect interface")
        self._wait_for_ack("0x82 readout protect failed")
        self._wait_for_ack("0x82 readout protect 2 failed")
        debug(10, "    Read protect done")

    def readout_unprotect(self):
        if not self.command(self.Command.READOUT_UNPROTECT):
            raise CmdException("Readout unprotect (0x92) failed")

        debug(10, "*** Readout Unprotect interface")
        self._wait_for_ack("0x92 readout unprotect failed")
        self._wait_for_ack("0x92 readout unprotect 2 failed")
        debug(10, "    Read Unprotect done")

    def read_memory_data(self, address, length):
        data = bytearray()
        while length > 256:
            debug(5, "Read %(len)d bytes at 0x%(address)X" % {'address': address, 'len': 256})
            data = data + self.read_memory(address, 256)
            address = address + 256
            length = length - 256
        else:
            debug(5, "Read %(len)d bytes at 0x%(address)X" % {'address': address, 'len': 256})
        data = data + self.read_memory(address, length)
        return data

    def write_memory_data(self, address, data):
        length = len(data)
        offs = 0
        while length > 256:
            debug(5, "Write %(len)d bytes at 0x%(address)X" % {'address': address, 'len': 256})
            self.write_memory(address, data[offs:offs + 256])
            offs = offs + 256
            address = address + 256
            length = length - 256
        else:
            debug(5, "Write %(len)d bytes at 0x%(address)X" % {'address': address, 'len': 256})
        self.write_memory(address, data[offs:offs + length] + (b'\xff' * (256 - length)))

    def _global_erase(self):
        # global erase: n=255, see ST AN3155
        self.serial.write(b'\xff')
        self.serial.write(b'\x00')

    def _page_erase(self, pages):
        # page erase, see ST AN3155
        nr_of_pages = (len(pages) - 1) & 0xFF
        self.serial.write(bytes([nr_of_pages]))
        checksum = nr_of_pages
        for page_number in pages:
            self.serial.write(bytes([page_number]))
            checksum = checksum ^ page_number
        self.serial.write(bytes([checksum]))

    def _wait_for_ack(self, info=""):
        try:
            ack = self.serial.read()[0]
        except TypeError:
            raise CmdException("Can't read port or timeout")

        if ack == self.Reply.NACK:
            raise CmdException("NACK " + info)

        if ack != self.Reply.ACK:
            raise CmdException("Unknown response. " + info + ": " + hex(ack))

        return 1

    @staticmethod
    def _encode_address(address):
        byte3 = (address >> 0) & 0xFF
        byte2 = (address >> 8) & 0xFF
        byte1 = (address >> 16) & 0xFF
        byte0 = (address >> 24) & 0xFF
        checksum = byte0 ^ byte1 ^ byte2 ^ byte3
        return bytes([byte0, byte1, byte2, byte3, checksum])


def usage():
    help_text = """Usage: %s [-hqVewvr] -p port [-l length] [-b baud] [-a address] [-g address] [file.bin]
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

    ./stm32loader.py -e -w -v example/main.bin
    """
    help_text = help_text % sys.argv[0]
    print(help_text)


if __name__ == "__main__":
    
    # default configuration values
    configuration = {
        # note: enter your serial port here if you don't want to specify it on the command line
        'port': None,
        'baud': 115200,
        'address': 0x08000000,
        'erase': 0,
        'write': 0,
        'verify': 0,
        'read': 0,
        'go_address': -1,
    }

    try:
        # parse command-line arguments using getopt
        opts, args = getopt.getopt(sys.argv[1:], "hqVewvrp:b:a:l:g:")
    except getopt.GetoptError as err:
        # print help information and exit:
        # this print something like "option -a not recognized"
        print(str(err))
        usage()
        sys.exit(2)

    QUIET = 5

    for o, a in opts:
        if o == '-V':
            QUIET = 10
        elif o == '-q':
            QUIET = 0
        elif o == '-h':
            usage()
            sys.exit(0)
        elif o == '-e':
            configuration['erase'] = 1
        elif o == '-w':
            configuration['write'] = 1
        elif o == '-v':
            configuration['verify'] = 1
        elif o == '-r':
            configuration['read'] = 1
        elif o == '-p':
            configuration['port'] = a
        elif o == '-b':
            configuration['baud'] = eval(a)
        elif o == '-a':
            configuration['address'] = eval(a)
        elif o == '-g':
            configuration['go_address'] = eval(a)
        elif o == '-l':
            configuration['length'] = eval(a)
        else:
            assert False, "unhandled option"

    if not configuration['port']:
        print("Please specify a serial port.")
        usage()
        sys.exit(2)


    interface = CommandInterface()
    interface.open(configuration['port'], configuration['baud'])
    debug(10, "Open port %(port)s, baud %(baud)d" % {'port': configuration['port'], 'baud': configuration['baud']})
    try:
        try:
            interface.init_chip()
        except Exception:
            print("Can't init. Ensure that BOOT0 is enabled and reset device")

        boot_version = interface.get()
        debug(0, "Bootloader version %X" % boot_version)
        device_id = interface.get_id()
        debug(0, "Chip id: 0x%x (%s)" % (device_id, CHIP_IDS.get(device_id, "Unknown")))

        binary_data = None
        data_file = args[0] if args else None

        if configuration['write'] or configuration['verify']:
            binary_data = open(data_file, 'rb').read()

        if configuration['erase']:
            interface.erase_memory()

        if configuration['write']:
            interface.write_memory_data(configuration['address'], binary_data)

        if configuration['verify']:
            read_data = interface.read_memory_data(configuration['address'], len(binary_data))
            if binary_data == read_data:
                print("Verification OK")
            else:
                print("Verification FAILED")
                print(str(len(binary_data)) + ' vs ' + str(len(read_data)))
                for i in range(0, len(binary_data)):
                    if binary_data[i] != read_data[i]:
                        print(hex(i) + ': ' + hex(binary_data[i]) + ' vs ' + hex(read_data[i]))

        if not configuration['write'] and configuration['read']:
            read_data = interface.read_memory_data(configuration['address'], configuration['length'])
            open(data_file, 'wb').write(read_data)

        if configuration['go_address'] != -1:
            interface.go(configuration['go_address'])

    finally:
        interface.release_chip()
