#!/usr/bin/env python3
"""Linux gs_usb inventory, silent loopback, and bounded RobStride identity queries."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import signal
import struct
import sys
import time

EFF = 0x80000000
RTR = 0x40000000
ERR = 0x20000000
NONE_ECHO = 0xFFFFFFFF
QUERY_IDS = (1, 2, 3, 4, 127)


def identity_response(frame):
    """Recognize a type-0 identity reply, excluding USB echo and error/RTR frames."""
    if frame.echo_id != NONE_ECHO or frame.can_id & (ERR | RTR):
        return None
    raw = frame.can_id & 0x1FFFFFFF
    motor_id = (raw >> 8) & 0xFFFF
    payload = bytes(frame.data[:frame.can_dlc])
    if (frame.can_id & EFF and raw >> 24 == 0 and 1 <= motor_id <= 254
            and frame.can_dlc == 8 and len(payload) == 8 and payload != bytes(8)):
        return {"motor_id": motor_id, "uid": payload.hex().upper(),
                "arbitration_id": f"{raw:08X}"}
    return None


def mode(dev, start, flags=0):
    dev.gs_usb.ctrl_transfer(0x41, 2, 0, 0, struct.pack("<II", start, flags), timeout=500)


def drain(dev, timeout_error):
    deadline = time.monotonic() + 0.2
    while time.monotonic() < deadline:
        try:
            dev.gs_usb.read(0x81, 20, timeout=10)
        except timeout_error:
            break


@contextmanager
def channel(dev, flags, item, timeout_error, dispose):
    """Never stop or detach a kernel-owned adapter; always stop after our setup."""
    configured = False
    try:
        if dev.gs_usb.is_kernel_driver_active(0):
            raise RuntimeError("Kernel driver owns adapter; refusing to detach")
        if flags and dev.device_capability.feature & flags != flags:
            raise RuntimeError("Silent loopback unsupported")
        dev.gs_usb.default_timeout = 500
        configured = True
        dev.gs_usb.ctrl_transfer(0x41, 0, 1, 0, struct.pack("<I", 0xBEEF), timeout=500)
        mode(dev, 0)
        drain(dev, timeout_error)
        if not dev.set_bitrate(1000000):
            raise RuntimeError("Unsupported CAN clock/bitrate")
        mode(dev, 1, flags)
        dev.device_flags = flags
        yield
    finally:
        if configured:
            try:
                mode(dev, 0)
                item["adapter_stopped"] = True
            except Exception as exc:
                item["stop_error"] = str(exc)
        dispose(dev.gs_usb)
        if configured and not item.get("adapter_stopped"):
            raise RuntimeError("Cannot confirm adapter stopped; abort remaining channels")


def receive(dev, frame_class, timeout_error):
    try:
        data = dev.gs_usb.read(0x81, 20, timeout=40)
    except timeout_error:
        return None
    if len(data) != 20:
        raise RuntimeError(f"Unexpected USB frame size: {len(data)}")
    frame = frame_class()
    frame_class.unpack_into(frame, data, False)
    return frame


def loopback(dev, item, frame_class, timeout_error):
    sent = frame_class(can_id=EFF | 0xFF7E, data=b"GSUSBv01")
    item["loopback_received"] = False
    dev.send(sent)
    deadline = time.monotonic() + 0.6
    while time.monotonic() < deadline:
        got = receive(dev, frame_class, timeout_error)
        if (got is not None and got.echo_id == NONE_ECHO and got.can_id == sent.can_id
                and got.can_dlc == 8 and bytes(got.data) == b"GSUSBv01"):
            item["loopback_received"] = True
            return


def identity(dev, item, frame_class, timeout_error):
    item.update(queries=[], responses=[], errors=[], completed=False)
    for target in QUERY_IDS:
        arb = 0xFF00 | target
        sent = frame_class(can_id=EFF | arb, data=bytes(8))
        query = {"motor_id": target, "arbitration_id": f"{arb:08X}",
                 "usb_tx_echo_received": False}
        item["queries"].append(query)
        dev.send(sent)
        deadline = time.monotonic() + 0.4
        while time.monotonic() < deadline:
            got = receive(dev, frame_class, timeout_error)
            if got is None:
                continue
            if got.echo_id != NONE_ECHO:
                if got.can_id == sent.can_id:
                    query["usb_tx_echo_received"] = True
                continue
            if got.can_id & ERR:
                if len(item["errors"]) < 16:
                    item["errors"].append({"can_id": f"{got.can_id:08X}",
                                           "data": bytes(got.data).hex()})
                continue
            response = identity_response(got)
            if response and response not in item["responses"]:
                item["responses"].append(response)
        if item["errors"] or not query["usb_tx_echo_received"]:
            item["stop_reason"] = "CAN error or missing USB echo; no more queries queued"
            break
    else:
        item["completed"] = True


def inventory(dev, item):
    if dev.gs_usb.is_kernel_driver_active(0):
        raise RuntimeError("Kernel driver owns adapter; use SocketCAN inspection")
    dev.gs_usb.default_timeout = 500
    info, cap = dev.device_info, dev.device_capability
    item.update(product=dev.gs_usb.product, fw_version=info.fw_version,
                hw_version=info.hw_version, icount=info.icount,
                feature=cap.feature, fclk_can=cap.fclk_can)


def exit_status(result):
    ports = result["ports"]
    if result.get("error") or not ports or any(p.get("error") or p.get("stop_error") for p in ports):
        return 1
    if result["mode"] == "identity":
        if any(p.get("errors") for p in ports):
            return 1
        return 0 if any(p.get("responses") for p in ports) else 2
    if result["mode"] == "loopback":
        return 0 if all(p.get("loopback_received") and p.get("adapter_stopped") for p in ports) else 1
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("inventory", "loopback", "identity"))
    parser.add_argument("--serial", help="Select one USB serial; otherwise inspect all 1d50:606f devices")
    parser.add_argument("--output", default="results/usb-can-result.json")
    args = parser.parse_args()
    if sys.platform != "linux":
        parser.error("Hardware operations require Linux; --help works on any platform")
    import fcntl
    import usb.core
    import usb.util
    from gs_usb.gs_usb import GsUsb
    from gs_usb.gs_usb_frame import GsUsbFrame

    def interrupted(number, frame):
        raise KeyboardInterrupt(f"signal {number}")

    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, interrupted)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    result = {"timestamp_utc": datetime.now(timezone.utc).isoformat(), "mode": args.mode,
              "transport": "userspace gs_usb/libusb", "bitrate": 1000000, "ports": []}
    if args.mode == "identity":
        result.update(query_ids=list(QUERY_IDS), motor_commands="type0 identity only",
                      motor_parameter_or_actuation_writes=0)

    def save():
        output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    # Same lock as the original board tools. Other applications must be stopped separately.
    with open("/run/lock/brainstem-usb-can-probe.lock", "a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            devices = [d for d in GsUsb.scan()
                       if (d.gs_usb.idVendor, d.gs_usb.idProduct) == (0x1D50, 0x606F)]
            devices.sort(key=lambda d: d.serial_number)
            if args.serial:
                devices = [d for d in devices if d.serial_number == args.serial]
            if not devices:
                raise RuntimeError("No matching USB adapter found")
            for dev in devices:
                item = {"serial": dev.serial_number, "usb_bus": dev.bus, "usb_address": dev.address}
                result["ports"].append(item)
                try:
                    if args.mode == "inventory":
                        try:
                            inventory(dev, item)
                        finally:
                            usb.util.dispose_resources(dev.gs_usb)
                    else:
                        with channel(dev, 3 if args.mode == "loopback" else 0, item,
                                     usb.core.USBTimeoutError, usb.util.dispose_resources):
                            action = loopback if args.mode == "loopback" else identity
                            action(dev, item, GsUsbFrame, usb.core.USBTimeoutError)
                except Exception as exc:
                    item["error"] = str(exc)
                    if item.get("stop_error"):
                        break
                finally:
                    save()
        except (Exception, KeyboardInterrupt) as exc:
            result["error"] = str(exc)
        finally:
            result["exit_status"] = exit_status(result)
            save()
    print(json.dumps(result, indent=2))
    return result["exit_status"]


if __name__ == "__main__":
    sys.exit(main())
