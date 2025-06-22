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

The Power State is determined by where the power is coming from and where it is going to.


| ---                         | PV/PS Off   | PV/PS On |
| Load Off                    | Idle        | Charging |
| Load less than PV/PS Supply | Discharging | Charging |
| Load more than PV/PS Supply | Discharging | Discharging |

| ---- | ------- | ----------- | --------------- |
| Load | Ps/PV   | Battery     | Power State     |
| ---- | ------- | ----------- | --------------- |
| Off  | Off     | Idle        | Idle            |
| On   | Off     | Discharging | Discharging     |
| Off  | On      | Charging    | Charging        |
| On   | > Load  | Charging    | Charging_Load   |
| On   | < Load  | Discharging | Split_Load      |
| ---- | ------- | ----------- | --------------- |


