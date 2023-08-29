# -*- coding: utf-8 -*-
"""
Example showing how to communicate with BLE-enabled Vevor heater.

Based on the bleak notifications sample by hbldh <henrik.blidh@gmail.com>

"""

import argparse
import asyncio
import bitstring
import logging

from bleak import BleakClient, BleakScanner
from bleak.backends.characteristic import BleakGATTCharacteristic

logger = logging.getLogger(__name__)
characteristic_uuid = "0000ffe1-0000-1000-8000-00805f9b34fb"

def parse_notification_response(data: bytearray):
    # This is simplistic w/o any data validation, just a PoC
    datastream = bitstring.ConstBitStream(data, pos=16)
    print(datastream)
    result = {}
    result["respose_to"] = datastream.read('uint8')
    result["powered_on"] = datastream.read('uint8')
    result["error_code"] = datastream.read('uint8')
    result["running_state"] = datastream.read('uint8')
    result["altitude"] = datastream.read('uintle16')
    result["operation_mode"] = datastream.read('uint8')
    result["target_power_level_or_temp"] = datastream.read('uint8')
    result["current_power_level"] = datastream.read('uint8')
    # etc
    return result


def notification_handler(characteristic: BleakGATTCharacteristic, data: bytearray):
    """Simple notification handler which prints the data received."""
    logger.info("%s: %r", characteristic.description, parse_notification_response(data))


async def main(args: argparse.Namespace):
    logger.info("starting scan...")

    if args.address:
        device = await BleakScanner.find_device_by_address(
            args.address, cb=dict(use_bdaddr=args.macos_use_bdaddr)
        )
        if device is None:
            logger.error("could not find device with address '%s'", args.address)
            return
    else:
        device = await BleakScanner.find_device_by_name(
            args.name, cb=dict(use_bdaddr=args.macos_use_bdaddr)
        )
        if device is None:
            logger.error("could not find device with name '%s'", args.name)
            return

    logger.info("connecting to device...")

    async with BleakClient(device) as client:
        logger.info("Connected")

        await client.start_notify(characteristic_uuid, notification_handler)
        # Query heater status
        await client.write_gatt_char(characteristic_uuid, bytearray([0xAA, 0x55, 0x0C, 0x22, 0x01, 0x00, 0x00, 0x2F]), response=True)
        await asyncio.sleep(1)
        # Turn heater on
        await client.write_gatt_char(characteristic_uuid, bytearray([0xAA, 0x55, 0x0C, 0x22, 0x03, 0x01, 0x00, 0x32]), response=True)
        for _ in range(10):
            await asyncio.sleep(5.0)
            # Query heater status a few times
            await client.write_gatt_char(characteristic_uuid, bytearray([0xAA, 0x55, 0x0C, 0x22, 0x01, 0x00, 0x00, 0x2F]), response=True)
        await asyncio.sleep(1)
        # Turn heater off
        await client.write_gatt_char(characteristic_uuid, bytearray([0xAA, 0x55, 0x0C, 0x22, 0x03, 0x00, 0x00, 0x31]), response=True)
        await client.stop_notify(characteristic_uuid)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    device_group = parser.add_mutually_exclusive_group(required=True)

    device_group.add_argument(
        "--name",
        metavar="<name>",
        help="the name of the bluetooth device to connect to",
    )
    device_group.add_argument(
        "--address",
        metavar="<address>",
        help="the address of the bluetooth device to connect to",
    )

    parser.add_argument(
        "--macos-use-bdaddr",
        action="store_true",
        help="when true use Bluetooth address instead of UUID on macOS",
    )

    parser.add_argument(
        "-d",
        "--debug",
        action="store_true",
        help="sets the log level to debug",
    )

    args = parser.parse_args()

    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)-15s %(name)-8s %(levelname)s: %(message)s",
    )

    asyncio.run(main(args))
