Using a Raspberry Pi as a Bluetooth® speaker with PipeWire
=====================================================

Do you have an old pair of PC speakers, or an old Hi-Fi, that you would like to convert into a pair of Bluetooth® speakers to play music from your phone? A Raspberry Pi can be easily used as an audio bridge between a Bluetooth® device and an analog speaker system, to make this possible. In this quick guide, I will show you how to set up the software on a Pi, using PipeWire, to achieve this.

In my demonstration setup, I am using a Raspberry Pi 3, which embeds a Bluetooth® chipset, and I am connecting an analog speaker to the 3.5mm jack. For the software, I am using RaspberryPi OS Lite with a recent PipeWire version installed from the Debian backports repositories, as the version included by default in RaspberryPi OS is too old to support this use case.

PipeWire is able to output sound to the internal audio chipset without any special configuration. It provides Bluetooth® A2DP support with optional codecs (SBC-XQ, LDAC, aptX, aptX HD, aptX-LL, FastStream) out of the box. At the same time, WirePlumber automatically creates the connection between the A2DP source and the audio chipset when a remote device, like a phone or a laptop, connects. This makes the configuration very easy, as PipeWire will work out of the box. We will only need to set up BlueZ to make the system headless.

Let's see how this is done.

First, install [RaspberryPi OS Lite (64-bit)](https://www.raspberrypi.com/software/operating-systems/) to your SD card (assuming `/dev/sdb` is the SD card device on your PC/laptop):
```
$  xzcat 2022-09-22-raspios-bullseye-arm64-lite.img.xz | sudo dd of=/dev/sdb bs=1M status=progress
```

Connect the Raspberry Pi to a display & keyboard, boot it from this SD card, and complete the OS configuration. Select `Console Autologin` using the `raspi-config` utility.

After the OS configuration is complete, install PipeWire and WirePlumber from the backport repository:
```
$ echo "deb http://deb.debian.org/debian bullseye-backports main contrib non-free" | sudo tee /etc/apt/sources.list.d/bullseye-backports.list
$ sudo apt update
$ sudo apt -t bullseye-backports install pipewire wireplumber libspa-0.2-bluetooth
```

The RaspberryPi OS *Lite* version automatically logs in the user created during the setup and this will automatically start *PipeWire* and *WirePlumber*. This is all that's needed for setting up PipeWire.

Next, we will need to set up a BlueZ pairing agent to accept pairings and A2DP connections. The reason we are doing this is because the target system is not going to have a user interface and we don't want to connect to it using ssh and type commands every time we want to pair a new device to it.

As this will require the DBus Python support, let's install this first:
```
$ sudo apt install python3-dbus
```

Then, copy the `speaker-agent.py` python script and its related *systemd* unit file from GitHub [pw_wp_bluetooth_rpi_speaker](https://github.com/fdanis-oss/pw_wp_bluetooth_rpi_speaker) to your user home directory on the Raspberrry Pi.

The `speaker-agent.py` python script, also shown below, will set the Raspberry Pi Bluetooth® adapter as always discoverable and will allow pairing and A2DP connections:
```
#!/usr/bin/python3
# SPDX-License-Identifier: LGPL-2.1-or-later

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
    exit_on_release = True

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
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

    bus = dbus.SystemBus()

    agent = Agent(bus, AGENT_PATH)
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
```

The systemd unit starts the speaker agent on boot as RaspberryPi OS Lite automatically logs in the user:
```
[Unit]
Description=Bluetooth speaker agent

[Service]
ExecStart=python speaker-agent.py

[Install]
WantedBy=default.target
```

This systemd unit will need to be placed in `~/.config/systemd/user/` and enabled manually using:
```
$ systemctl --user enable speaker-agent.service
```

Finally, configure the BlueZ daemon to allow re-pairing without user interaction:
```
$ sudo sed -i 's/#JustWorksRepairing.*/JustWorksRepairing = always/' /etc/bluetooth/main.conf
```

Now, connect the audio output of your Raspberry Pi to a speaker or your Hi-Fi system, reboot, pair, and connect your phone.

Enjoy the sound! ;)

