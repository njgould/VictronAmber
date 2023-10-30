#!/usr/bin/env python

"""
Used https://github.com/victronenergy/velib_python/blob/master/dbusdummyservice.py as basis for this service.
Reading information from Amber via http REST API and puts the info on dbus.
"""

import contextlib
try:
    import gobject
except ImportError:
    from gi.repository import GLib as gobject
import dbus
import json
import logging
import platform
import socket
import sys
import time
import os
import requests  # for http GET

try:
    import thread  # for daemon = True
except ImportError:
    import _thread as thread  # for daemon = True  / Python 3.x

# use an established Victron service to maintain compatiblity
sys.path.insert(1, os.path.join('/opt/victronenergy/dbus-systemcalc-py', 'ext', 'velib_python'))
from vedbus import VeDbusService, VeDbusItemImport

log = logging.getLogger("DbusVictronAmber")
path_UpdateIndex = "/UpdateIndex"


class DbusAmberService:
    def role_changed(self, path, val):
        if val not in self.allowed_roles:
            return False
        old, inst = self.get_role_instance()
        self.settings["instance"] = f"{val}:{inst}"
        return True

    def get_role_instance(self):
        val = self.settings["instance"].split(":")
        return val[0], int(val[1])



    def __init__(self, servicename, deviceinstance, ip=None):
        self.settings = {"instance": "grid:%d" % deviceinstance}

        self._firmware = "0.1"
        self._testdata = None
        self._latency = None

        # self._ip = ip or self.detect_dbus() or self.detect()
        # self._url = f"http://{self._ip}/solar_api/v1/GetMeterRealtimeData.cgi?Scope=Device&DeviceId=0&DataCollection=MeterRealtimeData"

        # data = self._get_amber_data()

        log.debug("%s /DeviceInstance = %d" % (servicename, deviceinstance))

        self._dbusservice = VeDbusService(servicename)
        # Create the management objects, as specified in the ccgx dbus-api document
        self._dbusservice.add_path("/Mgmt/ProcessName", __file__)
        self._dbusservice.add_path(
            "/Mgmt/ProcessVersion",
            f"Running on Python {platform.python_version()}",
        )
        self._dbusservice.add_path("/Mgmt/Connection", 'Amber API Connection')

        # Create the mandatory objects
        self._dbusservice.add_path('/DeviceInstance', deviceinstance)
        self._dbusservice.add_path('/ProductId', 0)
        self._dbusservice.add_path('/ProductName', 'Amber Pricing')
        self._dbusservice.add_path('/FirmwareVersion', 0)
        self._dbusservice.add_path('/HardwareVersion', 0)
        self._dbusservice.add_path('/Connected', 1)

        # self.allowed_roles = ["grid"]
        # self.default_role = "grid"
        # self.role = self.default_role
        # self._dbusservice.add_path("/AllowedRoles", self.allowed_roles)
        # self._dbusservice.add_path(
        #     "/Role", self.role, writeable=True, onchangecallback=self.role_changed
        # )

        _c = lambda p, v: (str(round(v, 2) or '') + "C/kWh")

        _kwh = lambda p, v: (str(round(v, 2) or '') + "kWh")
        _a = lambda p, v: (str(round(v, 1) or '') + "A")
        _w = lambda p, v: (str(round(v, 1) or '') + "W")
        _v = lambda p, v: (str(round(v, 1) or '') + "V")
        _ms = lambda p, v: (str(v or '') + "ms")
        _hz = lambda p, v: (str(v or '') + "Hz")
        _x = lambda p, v: (str(v or ''))

        self._paths = {
            "/FeedIn": {"initial": 0, "textformat": _c},
            "/AmberURL": {"initial": 'Not yet Set', "textformat": _x},
            "/AmberToken": {"initial": 'Not yet Set', "textformat": _x},
            "/AmberSiteID": {"initial": 'Not yet Set', "textformat": _x},
            "/Latency": {"initial": 0, "textformat": _ms},
            path_UpdateIndex: {"initial": 0, "textformat": _x},
        }

        for path, settings in self._paths.items():
            self._dbusservice.add_path(
                path,
                settings["initial"],
                gettextcallback=settings["textformat"],
                writeable=True,
                onchangecallback=self._handlechangedvalue,
            )

        self._retries = 0
        self._failures = 0
        self._latency = None
        gobject.timeout_add(1000, self._safe_update)

    def _handlechangedvalue(self, path, value):
        log.debug(f"someone else updated {path} to {value}")
        return True  # accept the change

    def _safe_update(self):
        try:
            self._update()
            self._retries = 0
        except Exception as e:
            log.error(f"Error running update {e}")
            self._retries += 1
            self._failures += 1
            if self._retries > 10:
                log.error("Number of retries exceeded.")
                sys.exit(1)
        return True

    def _get_amber_data(self):
        now = time.time()

        if self._dbusservice["/AmberURL"] == 'Not yet Set':
            return 0
        else:

            # response = requests.get(url=self._url, timeout=10).json()


            latency = time.time() - now
            if self._latency:
                self._latency = (9 * self._latency + latency) / 10
            else:
                self._latency = latency

            # return response["Body"]["Data"]
            return 20

    def _update(self):
        amber_data = self._get_amber_data()
   
        self._dbusservice["/Current/FeedIn"] = amber_data

        log.info(
            "Current Feed In Price: %s, Latency: %.1fms"
            % (amber_data, self._latency * 1000)
        )
        # increment UpdateIndex - to show that new data is available
        index = self._dbusservice[path_UpdateIndex] + 1  # increment index
        if index > 255:  # maximum value of the index
            index = 0  # overflow from 255 to 0
        self._dbusservice[path_UpdateIndex] = index
        return amber_data


def main():
    # logging.basicConfig(level=logging.INFO)

    root = logging.getLogger()
    # Log Level logging.INFO to get more details
    root.setLevel(logging.ERROR)

    handler = logging.StreamHandler(sys.stdout)
    # Log Level logging.INFO to get more details
    handler.setLevel(logging.ERROR)
    formatter = logging.Formatter(
        "%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s"
    )
    handler.setFormatter(formatter)
    root.addHandler(handler)

    log.info("Amber Startup")

    import argparse

    parser = argparse.ArgumentParser()
    # parser.add_argument(
    #     "--ip",
    #     help='IP Address of Smart Meter, leave empty to autodetect, specify "test" to use canned data',
    # )
    args = parser.parse_args()
    # if args.ip:
    #     log.info(f"User supplied IP: {args.ip}")
    # else:
    #     log.info("Auto detecting IP")

    with contextlib.suppress(NameError):
        thread.daemon = True  # allow the program to quit

    from dbus.mainloop.glib import DBusGMainLoop

    # Have a mainloop, so we can send/receive asynchronous calls to and from dbus
    DBusGMainLoop(set_as_default=True)

    pvac_output = DbusAmberService(
        servicename="com.victronenergy.amber", deviceinstance=1
    )

    logging.info(
        "Connected to dbus, and switching over to gobject.MainLoop() (= event based)"
    )
    mainloop = gobject.MainLoop()
    mainloop.run()


if __name__ == "__main__":
    main()
