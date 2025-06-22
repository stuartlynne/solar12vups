# Linux Bleak Issues


### Bleak Scanner

On Linux (query Windows?) the Bleak Scanner can only be used once per process.

This causes a problem once you have found a device and need to connect to it. 
That process requires a new Bleak Scanner to be created to get the services
of the connected device.

To allow for continued scanning, the Bleak Scanner must be paused in the 
scanning task to allow the Bleak Connection to proceed.

Once the Bleak Connection is complete the Bleak Scanner task can be restarted.


