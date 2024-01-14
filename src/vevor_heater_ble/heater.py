from __future__ import annotations

import asyncio
import dataclasses
import logging
import struct
from enum import Enum

from bleak import BLEDevice, BleakClient, BleakGATTCharacteristic
from bleak_retry_connector import establish_connection

from .const import CHAR_UUID_HEATER_CONTROL


class RequestType(Enum):
    READ_STATUS = 1
    SET_OP_MODE = 2
    TURN_ON_OFF = 3
    SET_HEATING_INTENSITY = 4


class PowerStatus(Enum):
    OFF = 0
    RUNNING = 1
    ERROR = 2


class OperationalStatus(Enum):
    WARMUP = 0
    SELF_TEST_RUNNING = 1
    IGNITION = 2
    HEATING = 3
    SHUTTING_DOWN = 4


class OperationalMode(Enum):
    POWER_LEVEL = 1
    TARGET_TEMPERATURE = 2


class HeaterError(Enum):
    NO_ERROR = 0
    POWER_SUPPLY_UNDERVOLTAGE = 1
    POWER_SUPPLY_OVERVOLTAGE = 2
    IGNITION_COIL_FAILURE = 3
    FUEL_PUMP_FAILURE = 4
    HIGH_TEMPERATURE_ALARM = 5
    FAN_FAILURE = 6
    CABLE_DAMAGE = 7
    COMBUSTION_FAILURE = 8
    SENSOR_FAILURE = 9
    IGNITION_FAILURE = 10


@dataclasses.dataclass
class VevorHeaterStatus(object):
    power_status: PowerStatus = None
    operational_mode: OperationalMode = None
    operational_status: OperationalStatus = None
    elevation: float = None
    target_temperature: int = None
    target_power_level: int = None
    current_power_level: int = None
    input_voltage: float = None
    combustion_temperature: int = None
    room_temperature: int = None
    error: HeaterError = None

    @staticmethod
    def from_ble_status(status_ble: VevorHeaterStatusBle):
        if not status_ble.power_status:
            return VevorHeaterStatus(power_status=PowerStatus.OFF)

        opmode = OperationalMode(status_ble.operational_mode) if status_ble.operational_mode else None
        target_temp_or_level = status_ble.target_temperature_or_level
        if OperationalMode == OperationalMode.TARGET_TEMPERATURE:
            current_power_level = status_ble.current_power_level + 1
        else:
            current_power_level = target_temp_or_level

        return VevorHeaterStatus(
            power_status=PowerStatus(status_ble.power_status),
            operational_mode=opmode,
            operational_status=OperationalStatus(status_ble.operational_status),
            elevation=float(status_ble.elevation),
            target_temperature=target_temp_or_level if opmode == OperationalMode.TARGET_TEMPERATURE else None,
            target_power_level=target_temp_or_level if opmode == OperationalMode.POWER_LEVEL else None,
            current_power_level=current_power_level,
            input_voltage=float(status_ble.input_voltage_decivolts) / 10,
            combustion_temperature=status_ble.combustion_temperature,
            room_temperature=status_ble.room_temperature,
            error=HeaterError(status_ble.display_error) if status_ble.display_error else HeaterError.NO_ERROR,
        )


@dataclasses.dataclass
class VevorHeaterStatusBle(object):
    magic_constant: int = None
    request_type: int = None
    power_status: int = None
    error: int = None
    operational_status: int = None
    elevation: int = None
    operational_mode: int = None
    target_temperature_or_level: int = None
    current_power_level: int = None
    input_voltage_decivolts: int = None
    combustion_temperature: int = None
    room_temperature: int = None
    display_error: int = None
    checksum: int = None

    @staticmethod
    def from_ble_data_array(buffer: bytearray) -> VevorHeaterStatusBle | None:
        unpack_format = "<HBBBBHBBBHHHBxB"
        unpacked = struct.unpack(unpack_format, buffer)
        result = VevorHeaterStatusBle(*unpacked)
        if result._verify():
            return result
        else:
            logging.warning("Unable to parse " + str(unpacked) + " as heater status!")
            return None

    def _verify(self) -> bool:
        self._verification_errors = []

        if self.power_status != 0:
            if self.request_type <= 0 not in range(1, 5):
                self._verification_errors.append("request_type")
            if self.power_status not in (0, 1, 2):
                self._verification_errors.append("power_status")
            if self.error not in range(11):
                self._verification_errors.append("error")
            if self.operational_status not in range(5):
                self._verification_errors.append("operational_status")
            if self.operational_mode not in (0, 1, 2):
                self._verification_errors.append("operational_mode")
            else:
                if self.operational_mode == 1:
                    allowed_target_range = range(1, 11)
                elif self.operational_mode == 2:
                    allowed_target_range = range(8, 37)
                else:
                    allowed_target_range = range(1)
                if self.target_temperature_or_level not in allowed_target_range:
                    self._verification_errors.append("target_temperature_or_level")
            if self.operational_mode == 2 and self.current_power_level not in range(10):
                self._verification_errors.append("current_power_level")
            if self.display_error not in range(11):
                self._verification_errors.append("display_error")

        calculated_checksum = sum((
            self.power_status,
            self.error,
            self.operational_status,
            self.elevation,
            self.operational_mode,
            self.target_temperature_or_level,
            self.current_power_level,
            self.input_voltage_decivolts,
            self.combustion_temperature,
            self.room_temperature,
            self.display_error)) % 256
        if calculated_checksum != self.checksum:
            self._verification_errors.append("checksum")

        if self._verification_errors:
            logging.warning(str(self) + " has verification errors: " + str(self._verification_errors))

        return not bool(self._verification_errors)


class VevorDevice:
    def __init__(self, name: str = None, address: str = None, status: VevorHeaterStatus = None):
        self.name = name
        self.address = address
        self.status = status
        self.command_lock = asyncio.Lock()

    def __str__(self):
        return f"VevorDevice(name={self.name}, address={self.address}, status={self.status})"

    async def _send_ble_command(self, device: BLEDevice, data: bytearray) -> VevorHeaterStatus | None:
        if device.address != self.address:
            raise ValueError("BLE addresses don't match!")
        async with self.command_lock:
            client = await establish_connection(client_class=BleakClient, device=device, name=device.address)
            try:
                response_received_latch = asyncio.Event()
                response = None

                def notification_handler(_: BleakGATTCharacteristic, response_data: bytearray):
                    status = VevorHeaterStatusBle.from_ble_data_array(response_data)
                    if status is None:
                        logging.warning("Received invalid Vevor BLE response, discarding...")
                    elif status.request_type != data[4]:
                        logging.warning("Received a response for a different request, discarding...")
                    else:
                        nonlocal response
                        response = VevorHeaterStatus.from_ble_status(status)

                    response_received_latch.set()

                await client.start_notify(CHAR_UUID_HEATER_CONTROL, notification_handler)
                await client.write_gatt_char(CHAR_UUID_HEATER_CONTROL, data, response=True)
                await response_received_latch.wait()
                await client.stop_notify(CHAR_UUID_HEATER_CONTROL)
                return response
            finally:
                await client.disconnect()

    async def _set_operational_mode(self, device: BLEDevice, mode: OperationalMode):
        data = bytearray([0xAA, 0x55, 0x0C, 0x22, 0x02, mode.value, 0x00, 0x00])
        checksum = sum(data[2:]) % 256
        data[-1] = checksum
        response = await self._send_ble_command(device, data)
        if response is not None:
            self.status = response

    async def _set_target(self, device: BLEDevice, target: int):
        data = bytearray([0xAA, 0x55, 0x0C, 0x22, 0x04, target, 0x00, 0x00])
        checksum = sum(data[2:]) % 256
        data[-1] = checksum
        response = await self._send_ble_command(device, data)
        if response is not None:
            self.status = response

    async def refresh_status(self, device: BLEDevice):
        response = await self._send_ble_command(device, bytearray([0xAA, 0x55, 0x0C, 0x22, 0x01, 0x00, 0x00, 0x2F]))
        if response is not None:
            self.status = response

    async def turn_on(self, device: BLEDevice):
        response = await self._send_ble_command(device, bytearray([0xAA, 0x55, 0x0C, 0x22, 0x03, 0x01, 0x00, 0x32]))
        if response is not None:
            self.status = response

    async def turn_off(self, device: BLEDevice):
        response = await self._send_ble_command(device, bytearray([0xAA, 0x55, 0x0C, 0x22, 0x03, 0x00, 0x00, 0x31]))
        if response is not None:
            self.status = response

    async def set_target_temperature(self, device: BLEDevice, temperature: int):
        await self._set_operational_mode(device, OperationalMode.TARGET_TEMPERATURE)
        await self._set_target(device, temperature)

    async def set_target_power_level(self, device: BLEDevice, power_level: int):
        await self._set_operational_mode(device, OperationalMode.POWER_LEVEL)
        await self._set_target(device, power_level)
