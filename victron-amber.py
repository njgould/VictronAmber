#!/usr/bin/env python3

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
from datetime import datetime
import os
import subprocess
import requests  # for http GET
import pymodbus
from pymodbus.client.sync import ModbusTcpClient
from pymodbus.constants import Endian
from pymodbus.payload import BinaryPayloadDecoder
    



try:
    import thread  # for daemon = True
except ImportError:
    import _thread as thread  # for daemon = True  / Python 3.x

# use an established Victron service to maintain compatiblity
sys.path.insert(1, os.path.join('/opt/victronenergy/dbus-systemcalc-py', 'ext', 'velib_python'))
from vedbus import VeDbusService, VeDbusItemImport, VeDbusItemExport
# from dbusmonitor import DbusMonitor


os.environ['TZ'] = 'Australia/Sydney'
time.tzset();


# create a file called amber_secrets.py
# It needs to define AmberToken, AmberSiteID, AmberURL
# Place in /data/keys so it doesn't get rewritten when the package is updated...
sys.path.append('/data/keys')
from amber_secrets import AmberToken, AmberSiteID, AmberURL

amber_headers = {
    'Accept': 'application/json',
    'Authorization': f"Bearer {AmberToken}"
    }


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

        self._modbusclient = ModbusTcpClient('localhost', port='502', unit_id=100)

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
            "/ImportPrice": {"initial": 0, "textformat": _x},
            "/ExportPrice": {"initial": 0, "textformat": _x},
            "/ExportPriceDisplay": {"initial": 0, "textformat": _x},
            "/Strategy": {"initial": 0, "textformat": _x},
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
        self.allow_charge = True

        gobject.timeout_add(15000, self._safe_update)




        # monitorlist = {'com.victronenergy.vebus.ttyUSB0': {
        #         '/Dc/0/MaxChargeCurrent': 'MaxChargeCurrent'}
        #         }

        # self.dbusmonitor = DbusMonitor(monitorlist)
        # self.dbusmonitor.set('MaxChargeCurrent', 20)




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

        response = requests.get(AmberURL, headers = amber_headers, timeout=10)
        amber_data = response.json()
        

        latency = time.time() - now
        if self._latency:
            self._latency = (9 * self._latency + latency) / 10
        else:
            self._latency = latency

        return amber_data

    def update_allow_charging(self, allow_charge = True):
        if not allow_charge == self.allow_charge:
            self.allow_charge = allow_charge
            if self.allow_charge == True:
                subprocess.call("dbus -y com.victronenergy.vebus.ttyUSB0 /Dc/0/MaxChargeCurrent SetValue 140", shell=True)                  
            else:
                subprocess.call("dbus -y com.victronenergy.vebus.ttyUSB0 /Dc/0/MaxChargeCurrent SetValue 0", shell=True) 


    def maximise_charge(self):
        # Set Allowable Charge Current to Max (140amps)
        self.update_allow_charging(allow_charge = True)
        # Set Target Grid Point to Import Max
        self._modbusclient.write_register(2700, -5000, unit=100)
        # Allow Export
        self._modbusclient.write_register(2708, 0, unit=100)  


    def maximise_charge_prevent_export(self):
        # Set Allowable Charge Current to Max (140amps)
        self.update_allow_charging(allow_charge = True)
        # Set Target Grid Point to Import Max
        self._modbusclient.write_register(2700, -25000, unit=100)
        # Dont't Allow Export (shape solar production)
        self._modbusclient.write_register(2708, 1, unit=100)   


    def prevent_export(self):
        # Set Allowable Charge Current to Max (140amps)
        self.update_allow_charging(allow_charge = True)
        # Set Target Grid Point to 0kw
        self._modbusclient.write_register(2700, 0, unit=100)
        # Dont't Allow Export (shape solar production)
        self._modbusclient.write_register(2708, 1, unit=100)


    def maximise_export(self):
        # Set Allowable Charge Current to Max (140amps)
        self.update_allow_charging(allow_charge = True)                
        #Set Target Grid Point to Export Max
        self._modbusclient.write_register(2700, 40536, unit=100)
        # Allow Export
        self._modbusclient.write_register(2708, 0, unit=100)


    def prioritise_export(self):
        # Set Allowable Charge Current to 0 Amps
        self.update_allow_charging(allow_charge = False)
        #Set Target Grid Point to Export 0kw
        self._modbusclient.write_register(2700, 0, unit=100)
        # Allow Export
        self._modbusclient.write_register(2708, 0, unit=100)

    def export_surplus_only(self):
        # Set Allowable Charge Current to Max (140amps)
        self.update_allow_charging(allow_charge = True)            
        #Set Target Grid Point to Export 0kw
        self._modbusclient.write_register(2700, 0, unit=100)
        # Allow Export
        self._modbusclient.write_register(2708, 0, unit=100)    


    def _update(self):
        amber_data = self._get_amber_data()
        local_time_hour = time.localtime()[3]
        import_price = amber_data[0]['perKwh']
        export_price = amber_data[2]['perKwh']
   
        self._dbusservice["/ImportPrice"] = import_price
        self._dbusservice["/ExportPrice"] = export_price
        self._dbusservice["/ExportPriceDisplay"] = export_price * -1
        log.info(f"Import Price: {import_price}")
        log.info(f"Export Price: {export_price}")


        # Get Current SOC (expressed as a %)
        result = self._modbusclient.read_input_registers(843, 1)
        decoder = BinaryPayloadDecoder.fromRegisters(result.registers, byteorder=Endian.Big)
        SOC = decoder.decode_16bit_uint()


        target_soc = 15 # Target Soc at end of tariff change (i.e 8pm)
        soc_discharge_rate = 14 # reduction in soc in 1 hour of max discharge (nominal)
        soc_charge_rate = 10 # increase in soc in 1 hour of max charge (nominal)


        # Positive Export Prices = being charged to Export
        # Negative prices = Paid to export

        # When the feedin tariff goes negative: If the import price is low enough, maximise import, otherwise just minimise export.

        if import_price <= 5:
            info = "Charging with Cheap Power"
            # If import price is < 5, then export price will be < 0, so export should be prevented also
            self.maximise_charge_prevent_export()
        if export_price > 0:
            info = "Preventing Export"
            self.prevent_export()


        
        # When the feed in price is positive
        elif export_price <= -40 and SOC > 70:
            info = "S3 Export is being Maximised"
            self.maximise_export()
        elif export_price <= -50 and SOC > 60:
            info = "S4 Export is being Maximised"
            self.maximise_export()
        elif export_price <= -60 and SOC > 50:
            info = "S5 Export is being Maximised"
            self.maximise_export()
        elif export_price <= -70 and SOC > 40:
            info = "S6 Export is being Maximised"
            self.maximise_export()
        elif export_price <= -80 and SOC > 30:
            info = "S7 Export is being Maximised"
            self.maximise_export()



        # To ensure battery is charged before the 2 way tariff shift
        # elif import_price <= 25 and 14-local_time_hour < (100-SOC)/soc_charge_rate:
        elif import_price <= 25:
            # info = f"Max Charge ({14-local_time_hour}hrs left, {(100-SOC)/soc_charge_rate}hrs req.)"
            info = f"Max Charge"
            self.maximise_charge()
            # self.export_surplus_only()




        # Extra Rules for later in the day when the 2 way tariff is in play...

        # If it's after 2pm (6hrs before the tariff ends)
        elif export_price <= -15 and SOC > (target_soc + 5*soc_discharge_rate) and local_time_hour >= 14:
            info = f"Max Export (limit at {target_soc + 5*soc_discharge_rate}% SOC)"
            self.maximise_export()

        # If it's after 3pm (5hrs before the tariff ends)
        elif export_price <= -15 and SOC > (target_soc + 4*soc_discharge_rate) and local_time_hour >= 15:
            info = f"Max Export (limit at {target_soc + 4*soc_discharge_rate}% SOC)"
            self.maximise_export()

        # If it's after 4pm (4hrs before the tariff ends)
        elif export_price <= -15 and SOC > (target_soc + 3*soc_discharge_rate) and local_time_hour >= 16:
            info = f"Max Export (limit at {target_soc + 3*soc_discharge_rate}% SOC)"
            self.maximise_export()

        # If it's after 5pm (3hrs before the tariff ends)
        elif export_price <= -15 and SOC > (target_soc + 2*soc_discharge_rate) and local_time_hour >= 17:
            info = f"Max Export (limit at {target_soc + 2*soc_discharge_rate}% SOC)"
            self.maximise_export()

        # If it's after 6pm (2hrs before the tariff ends)
        elif export_price <= -15 and SOC > (target_soc + 1*soc_discharge_rate) and local_time_hour >= 18:
            info = f"Max Export (limit at {target_soc + 1*soc_discharge_rate}% SOC)"
            self.maximise_export()

        # If it's after 7pm (1 hrs before the tariff ends)  
        elif export_price <= -15 and SOC > target_soc and local_time_hour >= 19:
            info = f"Max Export (limit at {target_soc}% SOC)"
            self.maximise_export()

        # If it's after 2pm, and if export price is 15c or above, don't charge the batteries... Just export.
        elif export_price <= -15 and SOC > target_soc and local_time_hour >= 14:
            info = "Export is being prioritised"
            self.prioritise_export()


        # Fallback to export surplus only
        else:
            info = "Exporting Surplus Only"
            self.export_surplus_only()



        self._dbusservice["/Strategy"] = info



        log.info("Latency: %.1fms"% (self._latency * 1000))
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
    # root.setLevel(logging.ERROR)
    root.setLevel(logging.INFO)

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
