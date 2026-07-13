#!/usr/bin/env python3
"""GW-Instek GDM-8251A bench multimeter driver for the station's Hardware-Test stage.

Mirrors the vendor testbench's meterSetMode({mode:'dc_current', range:5}) + read: the measurement mode
is set per test over SCPI, then the primary display value is read. Defensive - never raises to the
caller; returns None / (ok, msg). Enabled only when METER_PORT is set (else the station falls back to
the PSU's own current readout, then SKIP).

GDM-8251A remote (USB/RS-232, default 9600 8N1): CONF:CURR:DC / CONF:VOLT:DC to pick the mode, VAL1? to
read the primary value. Commands are overridable if a given unit's firmware differs.
"""
import time

try:
    import serial
except ImportError:
    serial = None

_MODE_CMD = {
    "dc_current": "CONF:CURR:DC",
    "ac_current": "CONF:CURR:AC",
    "dc_volt": "CONF:VOLT:DC",
    "ac_volt": "CONF:VOLT:AC",
    "resistance": "CONF:RES",
}


class Meter:
    def __init__(self, port, baud=9600, timeout=2.0, read_cmd="VAL1?"):
        self.port = port
        self.baud = baud
        self.timeout = timeout
        self.read_cmd = read_cmd
        self._s = None
        self._mode = None

    def _open(self):
        if serial is None:
            raise RuntimeError("pyserial not installed (pip install pyserial)")
        if not self.port:
            raise RuntimeError("METER_PORT not configured")
        if self._s is None:
            self._s = serial.Serial(self.port, self.baud, timeout=self.timeout)
            time.sleep(0.3)                       # let the adapter/meter settle after opening
            try:
                self._s.dtr = True
                self._s.rts = True
            except Exception:
                pass
            try:                                  # put the meter in remote; the first cmd is often swallowed
                self._s.write(b"SYST:REM\n")
                time.sleep(0.2)
                self._s.reset_input_buffer()
            except Exception:
                pass
        return self._s

    def _reconnect(self):
        try:
            if self._s:
                self._s.close()
        except Exception:
            pass
        self._s = None
        self._mode = None

    def _cmd(self, s):
        p = self._open()
        p.write((s + "\n").encode())
        time.sleep(0.1)

    def _query(self, s, tries=3):
        """Send a query, read the reply; retry - GW-Instek units frequently swallow the first command
        after a fresh open or after dropping out of remote, returning empty."""
        p = self._open()
        for _ in range(tries):
            p.reset_input_buffer()
            p.write((s + "\n").encode())
            time.sleep(0.25)
            r = p.readline().decode(errors="ignore").strip()
            if r:
                return r
            time.sleep(0.15)
        return ""

    def set_mode(self, mode):
        """Set the meter measurement mode per the current test (dc_current, dc_volt, ...)."""
        cmd = _MODE_CMD.get(mode)
        if not cmd:
            return (False, "unknown meter mode %r" % mode)
        try:
            self._cmd(cmd)
            self._mode = mode
            time.sleep(0.3)   # let the meter settle into the new range
            return (True, "mode %s" % mode)
        except Exception as e:
            return (False, "meter error: %s" % e)

    def read(self):
        """Read the primary display value as a float, or None on error / non-numeric. Reconnects once if
        the meter has gone silent (wedged adapter / dropped remote)."""
        for attempt in (1, 2):
            try:
                raw = self._query(self.read_cmd)   # e.g. "+1.234E-01", "0.20E-4", "0.098"
                if raw:
                    return float(raw.rstrip("AaVvOo ").strip())
            except Exception:
                pass
            if attempt == 1:
                self._reconnect()                  # silent/garbled -> rebuild the port and retry once
        return None

    def read_dc_current(self):
        """Convenience: set DC-current mode and read amps. None on error."""
        ok, _ = self.set_mode("dc_current")
        if not ok:
            return None
        return self.read()

    def read_dc_volt(self):
        """Convenience: set DC-volts mode and read volts (e.g. the siren/light 12 V output). None on error."""
        ok, _ = self.set_mode("dc_volt")
        if not ok:
            return None
        time.sleep(0.2)                        # let the reading stabilize after the range change
        return self.read()

    def close(self):
        try:
            if self._s:
                self._s.close()
        except Exception:
            pass
        self._s = None
