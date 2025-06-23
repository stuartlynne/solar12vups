# Power State


## Overview

The BT1 charge controller provides the following power data:

- PS/PV
    - Volts
    - Amps
- Battery
    - Volts
- Load
    - Volts
    - Amps

We can infer the power going into or out of the battery by comparing the power from the PS/PV to the power going to the load.

## Power State

The Power State is determined by where the power originates and where it is directed.


| Load | Ps/PV   | Battery     | Power State     |
| ---- | ------- | ----------- | --------------- |
| Off  | Off     | Idle        | Idle            |
| On   | Off     | Discharging | Discharging     |
| Off  | On      | Charging    | Charging        |
| On   | > Load  | Charging    | Charging_Load   |
| On   | < Load  | Discharging | Split_Load      |
| ---- | ------- | ----------- | --------------- |


