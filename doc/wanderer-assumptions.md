# Wanderer Telemetry Assumptions

This note documents what the Renogy Wanderer exposes over Modbus, what this app uses directly, and what the app derives or infers.

Primary references:

- [rover_modbus.pdf](./rover_modbus.pdf)
- Renogy BT-1 / RS232 documentation

## Scope

This app monitors Wanderer controllers through either:

- `BT-1` BLE transport
- Pico TCP bridge over the Wanderer RJ12 RS232 port

Those are only transport layers. The controller-side telemetry is the same Modbus data either way.

## Directly Available Controller Data

From the `0x0100` charging-info block and related registers, the controller directly provides:

- Battery SOC
- Battery voltage
- Charging current to battery
- Load voltage
- Load current
- Load power
- Solar/PV input voltage
- Solar/PV charging current
- Solar/PV charging power
- Load state and charging state
- Device info
  - Product model
  - Software version
  - Hardware version
  - Product serial number

### Register Summary

- `0x0100`: battery SOC
- `0x0101`: battery voltage, `raw * 0.1 V`
- `0x0102`: charging current to battery, `raw * 0.01 A`
- `0x0104`: load voltage, `raw * 0.1 V`
- `0x0105`: load current, `raw * 0.01 A`
- `0x0106`: load power, direct `W`
- `0x0107`: solar/PV voltage, `raw * 0.1 V`
- `0x0108`: solar/PV charging current, `raw * 0.01 A`
- `0x0109`: solar/PV charging power, direct `W`
- `0x0120`: load status / charging status

### Important Meaning

- `0x0102` is charging current to battery.
  It is not a general signed "net battery current" channel.
- `0x0107..0x0109` are the controller's solar-input / charging-side values.
  In this app the UI label is `PV/PS` because, in practice, the Wanderer input may be fed by either:
  - an actual solar panel
  - a regulated DC power supply

The controller documentation itself is solar-oriented. The app uses `PV/PS` as a more practical system label.

## Values Used Directly In The App

The following values are treated as directly measured controller telemetry:

- `battery_voltage`
- `battery_current`
- `load_voltage`
- `load_current`
- `pv_voltage`
- `pv_current`
- `battery_percentage`
- `load_status`
- `charging_status`
- `model`
- `software_version`
- `hardware_version`
- `serial_number`

## Watts: Raw Registers vs Computed `V * A`

The controller exposes direct watt registers for:

- `load_power_raw` from `0x0106`
- `pv_power_raw` from `0x0109`

However, in this app we commonly compute power from `V * A`:

- `load_power = load_voltage * load_current`
- `pv_power = pv_voltage * pv_current`
- `battery_power = battery_voltage * battery_current`

### Why We Compute `V * A`

The controller watt fields are useful, but in practice they appear coarse and can be jumpy at low loads.

Computing `V * A` gives:

- better apparent precision in the UI
- smoother visual behavior in gauges and history
- a consistent method across channels

This is especially relevant because the controller voltage resolution is only `0.1V`, and current is also quantized.
So none of these numbers are high-precision measurements. They are still useful, but should be interpreted as controller telemetry rather than lab-grade instrumentation.

## Values We Derive

The app derives these values from the measured channels:

- `battery_power = battery_voltage * battery_current`
- `load_power = load_voltage * load_current`
- `pv_power = pv_voltage * pv_current`

These derived power values are used for:

- the power-flow gauge
- the history graph
- inferred load composition

## Values We Infer

The controller does not directly report how much of the active load is being supplied by:

- battery
- solar/PV input

So the app infers the split.

### `PV/PS -> Battery`

This path is based on direct controller charging-side telemetry and is treated as measured/controller-reported for application purposes.

### `Battery -> Load`

This path is inferred.

The controller reports total load and charging-side values, but it does not provide a dedicated "battery currently supplying load" channel.

So the app estimates battery contribution as the remaining load not explained by the PV/PS side.

That means:

- the trend is useful
- the relative timing is useful
- the exact split is approximate

This is good enough for this application's operational monitoring needs, but it should not be presented as a direct measured quantity from the controller.

## Practical Interpretation

For this app, the following mental model is appropriate:

- Voltage and current channels are real controller telemetry.
- SOC is real controller telemetry.
- Load and PV/PS wattage are reasonable derived values based on controller telemetry, often preferable to the coarse raw watt fields.
- Battery charging power is reasonable to treat as measured/derived from the controller charging channel.
- Battery supplying load is inferred, not directly measured.

## Why This Is Acceptable Here

The operational goal is not laboratory metrology. It is to answer practical field questions such as:

- Is the controller charging?
- Is the battery healthy enough?
- Is the load cycling?
- Is the controller reacting to load changes?
- Is the box running mainly from PV/PS or leaning on the battery?

For those questions, this blend of direct telemetry plus limited inference is appropriate and useful.
