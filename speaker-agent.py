#!/usr/bin/python3
# SPDX-License-Identifier: LGPL-2.1-or-later

import argparse
import dbus
import dbus.service
import dbus.mainloop.glib
from gi.repository import GLib

BUS_NAME = 'org.bluez'
AGENT_INTERFACE = 'org.bluez.Agent1'
AGENT_PATH = "/speaker/agent"

A2DP = '0000110d-0000-1000-8000-00805f9b34fb'
AVRCP = '0000110e-0000-1000-8000-00805f9b34fb'

bus = None


class Rejected(dbus.DBusException):
    _dbus_error_name = "org.bluez.Error.Rejected"


class Agent(dbus.service.Object):

    def __init__(self, bus, path, single_connection):
        self.exit_on_release = True
        self.remote_device = None

        dbus.service.Object.__init__(self, bus, path)

        if single_connection:
            bus.add_signal_receiver(self.signal_handler,
                                    bus_name='org.bluez',
                                    interface_keyword='org.freedesktop.DBus.Properties',
                                    member_keyword='PropertiesChanged',
                                    arg0='org.bluez.Device1',
                                    path_keyword='path'
                                    )

    def signal_handler(self, *args, **kwargs):
        path = kwargs['path']
        connected = None
        for i, arg in enumerate(args):
            if type(arg) == dbus.Dictionary and "Connected" in arg:
                connected = arg["Connected"]

        if connected == None:
            return

        if not self.remote_device and connected == True:
            self.remote_device = path
            print("{} connected".format(path))
        elif path == self.remote_device and connected == False:
            self.remote_device = None
            print("{} disconnected".format(path))

    def set_exit_on_release(self, exit_on_release):
        self.exit_on_release = exit_on_release

    @dbus.service.method(AGENT_INTERFACE,
                         in_signature="", out_signature="")
    def Release(self):
        print("Release")
        if self.exit_on_release:
            mainloop.quit()

    @dbus.service.method(AGENT_INTERFACE,
                         in_signature="os", out_signature="")
    def AuthorizeService(self, device, uuid):
        if self.remote_device and self.remote_device != device:
            print("%s try to connect while %s already connected" % (device, self.remote_device))
            raise Rejected("Connection rejected by user")

        # Always authorize A2DP and AVRCP connection
        if uuid in [A2DP, AVRCP]:
            print("AuthorizeService (%s, %s)" % (device, uuid))
            return
        else:
            print("Service rejected (%s, %s)" % (device, uuid))
        raise Rejected("Connection rejected by user")

    @dbus.service.method(AGENT_INTERFACE,
                         in_signature="", out_signature="")
    def Cancel(self):
        print("Cancel")


def start_speaker_agent():
    # By default Bluetooth adapter is not discoverable and there's
    # a 3 min timeout
    # Set it as always discoverable
    adapter = dbus.Interface(bus.get_object(BUS_NAME, "/org/bluez/hci0"),
                             "org.freedesktop.DBus.Properties")
    adapter.Set("org.bluez.Adapter1", "DiscoverableTimeout", dbus.UInt32(0))
    adapter.Set("org.bluez.Adapter1", "Discoverable", True)

    print("RPi speaker discoverable")

    # As the RPi speaker will not have any interface, create a pairing
    # agent with NoInputNoOutput capability
    obj = bus.get_object(BUS_NAME, "/org/bluez")
    manager = dbus.Interface(obj, "org.bluez.AgentManager1")
    manager.RegisterAgent(AGENT_PATH, "NoInputNoOutput")

    print("Agent registered")

    manager.RequestDefaultAgent(AGENT_PATH)


def nameownerchanged_handler(*args, **kwargs):
    if not args[1]:
        print('org.bluez appeared')
        start_speaker_agent()


if __name__ == '__main__':
    options = argparse.ArgumentParser(description="BlueZ Speaker Agent")
    options.add_argument("--single-connection", action='store_true', help="Allow only one connection at a time")
    args = options.parse_args()

    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

    bus = dbus.SystemBus()

    agent = Agent(bus, AGENT_PATH, args.single_connection)
    agent.set_exit_on_release(False)

    bus.add_signal_receiver(nameownerchanged_handler,
                            signal_name='NameOwnerChanged',
                            dbus_interface='org.freedesktop.DBus',
                            path='/org/freedesktop/DBus',
                            interface_keyword='dbus_interface',
                            arg0='org.bluez')

    dbus_service = bus.get_object('org.freedesktop.DBus',
                                  '/org/freedesktop/DBus')
    dbus_dbus = dbus.Interface(dbus_service, 'org.freedesktop.DBus')
    if (dbus_dbus.NameHasOwner('org.bluez')):
        print('org.bluez already started')
        start_speaker_agent()

    mainloop = GLib.MainLoop()
    mainloop.run()
