# vevor-heater-ble

## Communication protocol

The BLE communication protocol for the heater is rather convoluted. Instead of requesting an authentication passkey, the heater 
expects the client to write the passkey to a predefined characteristic to authenticate itself. The heater then responds with 
a single notification providing the values. Any other attempts to retrieve the value of the characreristic will result in an empty
response.

## Request format

