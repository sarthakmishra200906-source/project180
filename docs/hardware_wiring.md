# Hardware Wiring

## ESP32 to L298N
- Map motor driver input pins to the ESP32 GPIO pins used in firmware.
- Share ground between ESP32, L298N, sensors, and battery pack.

## Sensors
- Connect the 4 VL53L0X sensors on the I2C bus.
- Assign unique addresses if multiple sensors are used on the same bus.
