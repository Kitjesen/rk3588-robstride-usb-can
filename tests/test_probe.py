"""Offline protocol and adapter lifecycle tests; no USB libraries or hardware required."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import struct
import unittest

spec = importlib.util.spec_from_file_location(
    "probe", Path(__file__).parents[1] / "scripts" / "usb_can_probe.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class Timeout(Exception):
    pass


class FakeUSB:
    def __init__(self, owned=False, fail_stop=False):
        self.owned = owned
        self.fail_stop = fail_stop
        self.calls = []
        self.started = False

    def is_kernel_driver_active(self, interface):
        return self.owned

    def ctrl_transfer(self, kind, request, value, index, payload, timeout):
        self.calls.append((request, payload))
        if request == 2:
            start, flags = struct.unpack("<II", payload)
            if start:
                self.started = True
            elif self.started and self.fail_stop:
                raise OSError("simulated stop failure")

    def read(self, *args, **kwargs):
        raise Timeout()


class FakeDevice:
    def __init__(self, **kwargs):
        self.gs_usb = FakeUSB(**kwargs)
        self.device_capability = SimpleNamespace(feature=243)

    def set_bitrate(self, bitrate):
        return bitrate == 1000000


class ProtocolTests(unittest.TestCase):
    def frame(self, **kwargs):
        values = dict(echo_id=probe.NONE_ECHO, can_id=probe.EFF | 0x02FE,
                      can_dlc=8, data=b"12345678")
        values.update(kwargs)
        return SimpleNamespace(**values)

    def test_identity_source_and_uid(self):
        self.assertEqual(probe.identity_response(self.frame()), {
            "motor_id": 2, "uid": "3132333435363738", "arbitration_id": "000002FE"})

    def test_echo_error_rtr_and_standard_are_not_responses(self):
        for change in (dict(echo_id=0), dict(can_id=probe.EFF | probe.ERR | 0x02FE),
                       dict(can_id=probe.EFF | probe.RTR | 0x02FE), dict(can_id=0x02FE)):
            with self.subTest(change=change):
                self.assertIsNone(probe.identity_response(self.frame(**change)))

    def test_invalid_type_id_length_and_uid(self):
        for change in (dict(data=bytes(8)), dict(can_dlc=7), dict(data=b"abc"),
                       dict(can_id=probe.EFF | 0x010002FE), dict(can_id=probe.EFF | 0x00FE),
                       dict(can_id=probe.EFF | 0xFFFE)):
            with self.subTest(change=change):
                self.assertIsNone(probe.identity_response(self.frame(**change)))


class LifecycleTests(unittest.TestCase):
    def test_kernel_owned_has_no_control_writes(self):
        dev, item, disposed = FakeDevice(owned=True), {}, []
        with self.assertRaisesRegex(RuntimeError, "Kernel driver"):
            with probe.channel(dev, 3, item, Timeout, disposed.append):
                self.fail("Must not acquire channel")
        self.assertEqual(dev.gs_usb.calls, [])
        self.assertNotIn("adapter_stopped", item)
        self.assertEqual(disposed, [dev.gs_usb])

    def test_stops_on_normal_exception_and_interrupt(self):
        for exc in (None, ValueError("test failure"), KeyboardInterrupt()):
            with self.subTest(exc=type(exc).__name__):
                dev, item, disposed = FakeDevice(), {}, []
                try:
                    with probe.channel(dev, 3, item, Timeout, disposed.append):
                        if exc:
                            raise exc
                except (ValueError, KeyboardInterrupt):
                    pass
                self.assertTrue(item["adapter_stopped"])
                self.assertEqual(dev.gs_usb.calls[-1], (2, struct.pack("<II", 0, 0)))
                self.assertEqual(disposed, [dev.gs_usb])

    def test_stop_failure_is_reported(self):
        dev, item, disposed = FakeDevice(fail_stop=True), {}, []
        with self.assertRaisesRegex(RuntimeError, "Cannot confirm adapter stopped"):
            with probe.channel(dev, 0, item, Timeout, disposed.append):
                pass
        self.assertIn("stop_error", item)
        self.assertEqual(disposed, [dev.gs_usb])

    def test_unsupported_loopback_does_not_write(self):
        dev, item = FakeDevice(), {}
        dev.device_capability.feature = 0
        with self.assertRaisesRegex(RuntimeError, "unsupported"):
            with probe.channel(dev, 3, item, Timeout, lambda d: None):
                pass
        self.assertEqual(dev.gs_usb.calls, [])


class ResultTests(unittest.TestCase):
    def test_empty_scan_fails(self):
        self.assertEqual(probe.exit_status({"mode": "inventory", "ports": []}), 1)

    def test_identity_exit_codes(self):
        result = {"mode": "identity", "ports": [{"responses": [], "errors": []}]}
        self.assertEqual(probe.exit_status(result), 2)
        result["ports"][0]["responses"].append({"motor_id": 2})
        self.assertEqual(probe.exit_status(result), 0)
        result["ports"][0]["errors"].append({"can_id": "20000024"})
        self.assertEqual(probe.exit_status(result), 1)

    def test_partial_loopback_fails(self):
        result = {"mode": "loopback", "ports": [
            {"loopback_received": True, "adapter_stopped": True},
            {"loopback_received": False, "adapter_stopped": True}]}
        self.assertEqual(probe.exit_status(result), 1)


if __name__ == "__main__":
    unittest.main()
