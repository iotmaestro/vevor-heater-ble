# vevor-heater-ble

## Communication protocol

The BLE communication protocol for the heater is rather convoluted. Instead of requesting an authentication passkey, the heater 
expects the client to write the passkey to a predefined characteristic to authenticate itself. The heater then responds with 
a single notification providing the values. Any other attempts to retrieve the value of the characreristic will result in an empty
response.

### 
The service and the characteristic are identified by the following UUIDs respectively: `0000ffe0-0000-1000-8000-00805f9b34fb` and `0000ffe1-0000-1000-8000-00805f9b34fb`.
The latter is also used to subscribe to the response notifications. 

### Request format

| Offset | Value     | Description                                           |
| -------| ------    | ------------------------------------------------------|
| 0      | 0xAA      | Magic version constant                                |
| 1      | 0x55      | Magic version constant                                |
| 2      | 0x0C      | Two most significant decimal password digits (**12**) |
| 3      | 0x22      | Two least significant decimal password digits (**34**)|
| 4      | 0x01-0x04 | Command to run (see below for more details)           |
| 5      | depends   | Value to send alongside the command.                  |
| 6      | 0x00      | ??? (padding, always zero)                            |
| 7      | any       | Checksum, sum of values at offset 2-6 modulo 256      |

#### Request commands

| Value | Accepted Data Values                                         | Description                                                                       |
| ------| -------------------------------------------------------------| ----------------------------------------------------------------------------------|
| 1     | 0                                                            | Ping, readonly device status request                                              |
| 2     | 1, 2                                                         | Operational mode. 1 - manual power level, 2 - automatic temperature-based control |
| 3     | 0, 1                                                         | Turn the heater off / on                                                          |
| 4     | `[1, 10]` for op. mode 1, `[8, 36]` for op. mode 2           | The desired temperature / power level                                             |

### Response format

All values are unsigned, little endian encoded integers, unless specified otherwise.

| Offset | Length     | Values                                                    | Description                                                                                                               |
| -------| -----------| -------                                                   | -----------------------------------------------                                                                           |
| 0      | 1          | 0xAA                                                      | Magic version constant                                                                                                    |
| 1      | 1          | 0x55                                                      | Magic version constant                                                                                                    |
| 2      | 1          | 0x01-0x04                                                 | Command this message is a response to (see above for details)                                                             |
| 3      | 1          | 0x00, 0x01                                                | Heater power status (on / off)                                                                                            |
| 4      | 1          | 0x00-0x0A                                                 | Error code (range taken from printed manual)                                                                              |
| 5      | 1          | 0x00-0x04                                                 | Running state <ul><li>Warmup</li><li>Self test running</li><li>Ignition</li><li>Heating</li><li>Shutting down</li></ul>   |
| 6      | 2          | any                                                       | Altitude                                                                                                                  |
| 8      | 1          | 0x01, 0x02                                                | Operational mode                                                                                                          |
| 9      | 1          | `[1, 10]` for op. mode 1, `[8, 36]` for op. mode 2        | Target temperature / power level                                                                                          |
| 10     | 1          | `[0, 9]`, only for for op. mode 2                         | Current power level. Offset by one when compared to the power level operation mode.                                       |
| 11     | 2          | any, typ. `[90, 180]`                                     | Voltage of the power supply, in decivolts (0.1 V)                                                                         | 
| 13     | 2          | any                                                       | Temperature of the heating element, in degrees Celsius.                                                                   |
| 15     | 2          | any                                                       | Temperature of the room, in degrees Celsius.                                                                              |
| 17     | 1          | 0x01-0x0A                                                 | Display error code (should correspond with the error code on the heater display)                                          |
| 18     | 1          | 0x00 	                                                    | ??? (padding, always zero)                                                                                                |
| 19     | 1          | any                                                       | Checksum, sum of values at offsets `[3;(last-1)]` modulo 256                                                              |
