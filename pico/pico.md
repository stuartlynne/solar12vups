# Pico Serial Connection to Renogy Wanderer 10A

The Renogy uses TTL 5V serial for its communication. The Raspberry Pi Pico uses 3.3V logic levels. 
To safely connect the two, we need to use a voltage divider to step down the 5V signals from the Renogy to 3.3V for the Pico.


        PICO PHYSICAL PINS (Top Left Edge)
        ┌──────────────────────────────────────────────────┐
        │  ● Pin 1 (GPIO 0 / TX) ───────────────────────────────► RJ12 Pin 2 (RX)           
        │                                                  │
        │  ● Pin 3 (GND) ◄────────────┬────────────────────────── RJ12 Pin 3 (GND)
        │                             │                    │
        │                             └─[ 3.9kΩ Resistor ] │  (Pulls 5V down to safe 3.6V)
        │                                                │ │
        │  ● Pin 2 (GPIO 1 / RX) ◄────┬──────────────────┘────────[ 1.5kΩ Resistor ] ◄─ RJ12 Pin 1 (TX, 5V) 
        │                             │                    │
        │  ● Pin 4 (GPIO 2 / NC ) ◄─────────┴─[ 1.5kΩ Resistor ] ◄─ RJ12 Pin 1 (TX, 5V)                   
        │                                                  │  (Anchor Tag: Bridge Pin 2 to Pin 4)
        └──────────────────────────────────────────────────┘



N.b. The RS232 Hat is not needed or suitable for this connection, as the Renogy uses TTL serial, not RS232 voltage levels. The above wiring allows direct communication between the Pico and the Renogy without additional level shifting hardware.



## Notes

1. Pinout and Voltage LevelsThe RJ12 communication port on the Renogy Wanderer
does not use standard RS-232 voltage levels (+/-12V), nor does it use standard
TTL (5V/3.3V).It uses RS-232 signaling protocols but at 0V to 5V (TTL-like)
levels, or true proprietary configurations depending on the exact hardware
revision.Crucial Step: Ensure your Pico RS-232 Hat can tolerate or decode the
specific signaling from the Wanderer's RJ12 port without frying the Pico's 3.3V
GPIO pins. Many timing engineers bypass the RS-232 chip entirely and use a
simple level shifter directly into the Pico's UART pins.

2. Powering the PicoThe RJ12 port on the Wanderer outputs a live 12V DC power pin
directly from the battery bank. You can use a tiny buck converter to step this
12V down to 5V to power your Raspberry Pi Pico. This means your remote
data-bridge is completely self-powered by the ERYY batteries, requiring no
extra wall warts or wiring inside the remote box.


## 📐 How to Wire the Option A Workaround

By using these resistors, you form a voltage divider that clips the Wanderer's 5V signal down to a safe 3.33V, 
protecting the Pico's sensitive GPIO input without needing the Waveshare transceiver chip.text

Wanderer RJ12 Pin 1 White (TX 5V) ───────[ 1.5kΩ Resistor ]──────────────► Pico GPIO RX Pin 1 (3.3V Safe)
                                                          │
                                                    [ 4.2kΩ Resistor ]
                                                          │
Wanderer RJ12 Pin 3 Red   (GND) ◄──────────────────────────────────────► Pico System GND Pin 3

Wanderer RJ12 Pin 2 Black (RX): ◄────────────────────────────────────── Pico GPIO TX pin 2 

Wanderer Pins 5 & 6 (12V VCC): Ensure these are cleanly trimmed, capped, or insulated so they cannot touch the components.






