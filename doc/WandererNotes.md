# Renogy Wanderer 10A Solar Charge Controller Notes


## Overview

This outlines how to use the Renogy Wanderer 10A Solar Charge Controller as a 12VUPS with either Solar or AC power.

Our use case is three RFID Reader boxes that are used for timing bike races. One box runs off the start line power but we use this as a backup
in case the power fails (e.g. generator out of gas.) The other two are located where there is no power and have sufficient battery capacity to run for the
expected duration of the event. The load for these in operation is 30W. 

- Primary Reader - 1x8Ah LiFePO4 battery, backup only, has Cradlepoint IBR600C LTE modem for remote monitoring and alerts and local network
- Secondary Reader - 3x8Ah LiFePO4 batteries in parallel, TP-Link Micro WiFi to connect to local network
- Early Reader - 2x15Ah LiFePO4 batteries in parallel, TP-Link EAP211 (pair) to connect to local network, up to 800m line of sight

These are packaged into Dewalt Tough Boxes complete with antenas etc. The primary requirement is that they are easily setup, easily stored and moved, have
remote monitoring and can be charged by 100W 20V power supplies. Also that they can be used with a power supply or solar panel.

## Powering the Controller

The controller can be powered by either Solar or AC power. 

For charging batteries or for AC power, using a 65W or 100W 16-24Vdc power supply is used. Because of characteristics of the controller, many
power supplies will not work as it may attempt to draw more current than the supply can provide causing the supply to shut down. 

To avoid this a DC-DC Regulator is used to limit the current draw to 5A. This allows the controller to operate properly without shutting down the power supply. 

This is wired inline between the Wanderer PV terminals and the power supply. The power supply is connected to the input of the DC-DC regulator and 
the output of the regulator is connected to the load terminals of the controller.

If using a solar panel it should NOT be connected via the DC-DC regulator.

E.g. $30 on Amazon:

[https://www.amazon.ca/dp/B07KWX33X5](DC-DC Buck Converter, DROK Voltage Reducer DC 8-35V to DC 1.5-24V 5A Power Supply Step Down Regulator Module 24V 12V 5V Volt Transformer Stabilizer)



## Batteries

We use 8Ah-15Ah LifePo4 batteries connected in parallel. 3x8A or 2x15A will run a 30W load for 8-12 hours. 

## Load

The load is connected to the controller's load terminals which provides 12Vdc power.

N.b. The Wanderer 10A controller is sensitive to a high inrush current when the load is enabled. E.g. using a 12V-24V buck converter may cause an E04 (short circuit) error.

Generally if the actual load is connected a few seconds AFTER the load is enabled, the controller will operate normally. This can be achieved by using a cheap 12V Timer Relay Module to delay the load connection by a few seconds after the load is enabled.

This is wired inline between the Wanderer load terminals and the load. The load is connected to the normally open (NO) contacts of the relay, and the relay coil is powered by the load terminals of the controller. When the load terminals are enabled, the relay will energize after a short delay, allowing the load to be connected without causing an inrush current that triggers the error.

E.g. $16.99 for 5 modules on Amazon:

[https://www.amazon.ca/product-reviews/B08HV76ZQK/] (NE555 Delay Timer Relay 12V DC 0-10 Seconds Adjustable Delay Timer Switch Module)


## Monitoring

The Wanderer has an RJ12 port the provides RS232 serial data access to MODBUS registers containing operational data.

Renogy sells the BT-1 Bluetooth module that plugs into the RJ12 port and allows monitoring via a smartphone app. However, this is not ideal for remote monitoring.

A custom solution can be implemented using a microcontroller (e.g., Arduino, Raspberry Pi) with an RS232 to TTL converter to read the MODBUS data from the RJ12 port. This data can then be transmitted wirelessly (e.g., via Wi-Fi or Bluetooth) to a remote monitoring system or cloud service for real-time monitoring and alerts.

For example:

- Raspberry pico 2 W
- Waveshare RS232 Hat
- RJ12 adapter with breakout to screw terminals for connecting to the Wanderer RJ12 port
- RJ12 extension cable to allow the monitoring device to be located away from the controller and plugged into the controller's RJ12 port
- USB A - Micro USB cable to power the monitoring device from the Wanderer USB port

In our application that monitors the Wanderers in our boxes, we support both. The app has a TCP server that listens for incoming TCP connections. A micropython script 
runs on the pico that connects to WiFi and then connects to the app's TCP server. Once connected it simply acts as an RS232 to TCP bridge,
forwarding and return MODBUS data between the Wanderer and the app.



