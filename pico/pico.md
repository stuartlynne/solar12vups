# Pico Serial Connection to Renogy Wanderer 10A

## Introduction

An RS232 hat is used to connect a Raspberry Pi Pico to the Renogy Wanderer 10A charge controller. 
The RS232 hat provides the necessary voltage level shifting and signal conditioning for reliable serial communication between the Pico and the charge controller.

## Pinout
The Renogy Wanderer 10A uses an RJ12 connector for RS232 serial. 
Pinout:


|RJ12 Pin | RS232 Signal | Notes / Destination|
|Pin 1 | TX (Transmit) | Transmits data out of the charge controller. |
|Pin 2 | RX (Receive) | Receives incoming commands. |
|Pin 3 | GND (Ground) | Logic ground reference for serial communication. |
|Pin 4 | GND (Ground) | Secondary logic ground. |
|Pin 5 | VCC (+12V to +15V) | Power supply pin for the Renogy BT-1 Bluetooth Module. |
|Pin 6 | VCC (+12V to +15V) | Secondary power supply pin. |



## RJ12 Breakout Board to USB Hat UART 2

+ ## RJ12 Breakout Board to USB Hat UART 2

 ``` 
~         RJ12 Pinout                   USB Hat UART Pinout Channel 1 
          (Top View)                    (Top View)
        ┌─────────────┐
~       │ Pin 6 │ NC  │                  
~       │       │     │                 
~       │ Pin 5 │ NC  │                
~       │       │     │               
~       │ Pin 4 │ NC  │              
~       │       │     │                  ┌─────────────┐
~       │ Pin 3 │ Gnd │ ◄──────────────► │ GND │ Pin 3 │                                                                                                                                     
~       │       │     │                  │     │       │                                                                                                                                      
~       │ Pin 2 │ RX  │ ◄──────┐ ┌─────► │ RX -│ Pin 2 │                                                                                                                                     
~       │       │     │         ╳        │     │       │                                                                                                                     
~       │ Pin 1 │ TX  │ ───────┘ └─────► │ TX -│ Pin 1 │
        └─────────────┘                  └─────────────┘
```


