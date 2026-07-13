"""Waveshare Modbus RTU Analog Output 8CH (current, 0-20 mA) driver.

Injects a 4-20 mA loop current into the tank-monitor analog inputs so the S3/S4
threshold sweeps run without a human turning a knob.

Register map (Waveshare "Development Protocol V2", current-output SKU 26419):
  channel value  0x0000..0x0007  AO1..AO8  holding reg, FC03/06/16, value = current in uA
  UART param     0x2000          hi=parity  lo=baud-code
  device addr    0x4000
  version (ro)   0x8000
NO range/mode-select register and NO 0-20/4-20 selector exist: hardware is fixed
0-20 mA. 4-20 mA is emulated by commanding 4000..20000 uA. Output values are
VOLATILE (lost on power cycle). Requires pymodbus>=3.0.
"""
from __future__ import annotations

REG_AO_BASE = 0x0000        # AO1..AO8 = 0x0000..0x0007
REG_UART    = 0x2000
REG_ADDR    = 0x4000
REG_VERSION = 0x8000
UA_MIN, UA_MAX = 0, 20000   # 0..20 mA full scale
BAUD_CODE = {4800: 0, 9600: 1, 19200: 2, 38400: 3, 57600: 4,
             115200: 5, 128000: 6, 256000: 7}


class WaveshareAO:
    def __init__(self):
        self._client = None
        self._addr = 1

    # --- lifecycle ---------------------------------------------------------
    def open(self, port: str, baud: int = 9600, addr: int = 1, timeout: float = 1.0):
        from pymodbus.client import ModbusSerialClient
        self._addr = addr
        self._client = ModbusSerialClient(
            port=port, baudrate=baud, bytesize=8, parity="N", stopbits=1,
            timeout=timeout)
        if not self._client.connect():
            raise RuntimeError(f"Waveshare: cannot open serial port {port!r} @ {baud} 8N1")
        return self

    def close(self):
        if self._client is not None:
            try:
                self.all_off()
            except Exception:
                pass
            self._client.close()
            self._client = None

    # --- pymodbus 3.x slave/device_id compat + error check -----------------
    # pymodbus 3.7+ makes `count` keyword-only on reads, so callers pass it via **kw.
    def _call(self, fn, *args, **kw):
        try:
            return fn(*args, slave=self._addr, **kw)
        except TypeError:
            return fn(*args, device_id=self._addr, **kw)

    @staticmethod
    def _check(rsp, what):
        if rsp is None or (hasattr(rsp, "isError") and rsp.isError()):
            raise RuntimeError(f"Waveshare Modbus error on {what}: {rsp!r}")

    # --- public API --------------------------------------------------------
    def set_current_ma(self, channel: int, ma: float) -> int:
        """Command AO<channel> (1..8) to `ma` mA (0..20). Returns commanded uA. FC06."""
        if not 1 <= channel <= 8:
            raise ValueError(f"channel {channel} out of range 1..8")
        ua = int(round(ma * 1000))
        if not UA_MIN <= ua <= UA_MAX:
            raise ValueError(f"{ma} mA -> {ua} uA out of 0..20000 (device is fixed 0-20 mA)")
        r = self._call(self._client.write_register, REG_AO_BASE + (channel - 1), ua)
        self._check(r, f"set AO{channel}={ua}uA")
        return ua

    def read_current_ua(self, channel: int) -> int:
        """Read back the commanded uA on AO<channel>. FC03."""
        r = self._call(self._client.read_holding_registers, REG_AO_BASE + (channel - 1), count=1)
        self._check(r, f"read AO{channel}")
        return r.registers[0]

    def set_range_mode(self, mode: str = "0-20mA") -> str:
        """No range register exists on this SKU: 0-20 mA is fixed hardware.
        Accepts '0-20mA' (native) or '4-20mA' (emulated by commanding 4000..20000 uA).
        Raises for any other mode so a caller's wrong assumption fails loudly."""
        if mode not in ("0-20mA", "4-20mA"):
            raise ValueError(
                f"unsupported mode {mode!r}: Output 8CH is fixed 0-20 mA current; "
                "4-20 mA is emulated in software (command 4000..20000 uA). "
                "0-10 V requires the '(B)' hardware SKU.")
        return mode

    def all_off(self):
        """Set all 8 channels to 0 uA in one FC16 frame (safe/idle state)."""
        r = self._call(self._client.write_registers, REG_AO_BASE, [0] * 8)
        self._check(r, "all_off")

    def version(self) -> int:
        """Read 0x8000; 100 == V1.00."""
        r = self._call(self._client.read_holding_registers, REG_VERSION, count=1)
        self._check(r, "version")
        return r.registers[0]
