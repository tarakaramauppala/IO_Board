#!/usr/bin/env python3
"""GW-Instek GPD-3303S bench PSU driver for the station dashboard.

SAFETY (from HANDOFF section 2 / the 24 V incident): output-enable is GLOBAL on this PSU (OUT1 powers
BOTH channels). The board is on CH2 and is 12 V ONLY (24 V damages it). So safe_power_on() sets the
connected channel to the ceiling, VERIFIES BOTH channels are <= ceiling, and only then enables output.
Voltage is software-clamped to the ceiling. Never raises to the caller - returns (ok, message).

SCPI-ish command set for the GPD-x303S series: VSET<ch>:<v>, ISET<ch>:<a>, OUT1/OUT0, VOUT<ch>?.
"""
import time

try:
    import serial
except ImportError:
    serial = None


class PSU:
    def __init__(self, port, baud=9600, channel=2, ceiling_v=12.0, current_a=1.5, timeout=1.0):
        self.port = port
        self.baud = baud
        self.ch = int(channel)
        self.ceiling = float(ceiling_v)
        self.current = float(current_a)
        self.timeout = timeout
        self._s = None

    # --- low level (raise on comms error; callers wrap) ---------------------
    def _open(self):
        if serial is None:
            raise RuntimeError("pyserial not installed (pip install pyserial)")
        if not self.port:
            raise RuntimeError("PSU port not configured (set PSU_PORT, e.g. COM4)")
        if self._s is None:
            self._s = serial.Serial(self.port, self.baud, timeout=self.timeout)
        return self._s

    def _cmd(self, s):
        p = self._open()
        p.write((s + "\n").encode())
        time.sleep(0.05)

    def _query(self, s):
        p = self._open()
        p.reset_input_buffer()
        p.write((s + "\n").encode())
        time.sleep(0.1)
        return p.readline().decode(errors="ignore").strip()

    def vset(self, ch, v):
        self._cmd("VSET%d:%.2f" % (ch, min(v, self.ceiling)))   # clamp

    def iset(self, ch, a):
        self._cmd("ISET%d:%.2f" % (ch, a))

    def vout(self, ch):
        try:
            return float(self._query("VOUT%d?" % ch).rstrip("Vv"))
        except Exception:
            return None

    def read_current(self, ch=None):
        """Board current (A) from the PSU's own readout (IOUT<ch>?). None on error. Lets the
        Hardware-Test current check work without an external meter in series."""
        ch = self.ch if ch is None else ch
        try:
            return float(self._query("IOUT%d?" % ch).rstrip("Aa"))
        except Exception:
            return None

    def output(self, on):
        self._cmd("OUT1" if on else "OUT0")

    # --- safe high level (never raise) --------------------------------------
    def safe_power_on(self):
        """Set the connected channel to the ceiling, verify BOTH channels <= ceiling, then enable
        the (global) output. Refuses if either channel reads above the ceiling."""
        try:
            self.vset(self.ch, self.ceiling)
            self.iset(self.ch, self.current)
            time.sleep(0.2)
            for ch in (1, 2):
                v = self.vout(ch)
                if v is not None and v > self.ceiling + 0.5:
                    return (False, "REFUSED: CH%d reads %.2fV > ceiling %.1fV (output-enable is GLOBAL "
                                   "- set both channels <=%.1fV first)." % (ch, v, self.ceiling, self.ceiling))
            self.output(True)
            return (True, "output ON; CH%d set %.1fV / %.2fA (both channels verified <=%.1fV)"
                          % (self.ch, self.ceiling, self.current, self.ceiling))
        except Exception as e:
            return (False, "PSU error: %s" % e)

    def power_off(self):
        try:
            self.output(False)
            return (True, "output OFF")
        except Exception as e:
            return (False, "PSU error: %s" % e)

    def status(self):
        """(ok, {ch1, ch2, output_hint}). Read-only; best-effort."""
        try:
            return (True, {"ch1_v": self.vout(1), "ch2_v": self.vout(2)})
        except Exception as e:
            return (False, {"error": str(e)})

    def close(self):
        try:
            if self._s:
                self._s.close()
        except Exception:
            pass
        self._s = None
