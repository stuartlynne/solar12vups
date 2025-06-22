# Renogy BT-1 Notes

The Renogy BT-1 is a BLE device that bridges Renogy Solar Charge Controllers to allow
applications to use the MODBUS protocol to access the data from the controller.

The BT-1 plugs into an RJ12 port on the Renogy Solar Charge Controller and provides to
allow MODBUS over Serial over BLE.


## Issues

The BT-1 has a number of issues that make it difficult to use with the Bleak library
especially in Linux.

### Connection Issues
The BT-1 will hold the connection open until the host disconnects.

The Linux BLUEZ stack will not automatically disconnect when the application exits.

This means that the application must explicitly disconnect from the BT-1 before exiting.

This can be partially mitigated by using:

```
bluetoothctl devices | egrep BT-TH # to get the MAC address
bluetoothctl disconnect <BT-TH MAC> # use the MAC address to disconnect
```

This can be scripted and run at the beginning of the application to ensure that 
all BT-1 devices are disconnected before the application starts.


### Other Connection Issues

Even with a clean disconnect the BT-1 will sometimes fail to disconnect.

There is no way to detect this failure in the Bleak library and no mitigation.

The device needs to be manually replugged to reset it.

### First Connection Issues

The BT-1 never properly connects to the Renogy SCC with MODBUS on its first
BLE Connection after being plugged in (or replugged).

Watching for data and forcing a disconnect and reconnect will typically
allow the connection to succeed.



