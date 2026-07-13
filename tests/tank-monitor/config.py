"""Tank-monitor test config — signatures, thresholds, device IDs.

Everything here is grounded in the firmware/hardware docs and source (cited). Override the
image path with the TANK_IMAGE env var. Nothing here talks to the source repos.
"""
import os


def _load_env(path):
    """Load KEY=VALUE lines from a gitignored .env (secrets/station.env) into os.environ as DEFAULTS,
    so per-device identity + LoRaWAN keys stay OUT of this committed file. No dependency (no dotenv);
    a real env var still wins over the file."""
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except Exception:
        pass


_load_env(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "secrets", "station.env"))

# --- Image & device ---------------------------------------------------------
# Tank-monitor MERGED hex (MCUboot + app) + FACTORY_DATA hex. The vendor programmer
# flashes BOTH (merged then factory) plus a settings block + APPROTECT clear — see
# vendor/vx_programmer/devices/jlink/IOBoard.py and docs. Override paths via env.
# Default = the v2.0.4 DEV release drop the engineer provided (matches what the live
# device 104D1526064B6130 runs). "dev" factory keeps it on the dev fleet/tenant.
_V204_DIR = r"C:\claude\ioboard\tank-monitor-fw-vx-0057-release-v-2.0.4-h-d4ca9f20-2026-06-05-18-40-UTC-0300"
TANK_IMAGE = os.environ.get(
    "TANK_IMAGE", os.path.join(_V204_DIR, "tank-monitor-fw-vx-0057-merged-v-2.0.4-h-d4ca9f20.hex"))
FACTORY_DATA_IMAGE = os.environ.get(
    "FACTORY_DATA_IMAGE",
    os.path.join(_V204_DIR, "tank-monitor-fw-vx-0057-factory_data-dev-v2.0.4-h-d4ca9f20.hex"))

# --- Vendor WITH-TESTBENCH firmware (self-test build) -----------------------
# From Viaanix/vx-testbench-releases (release ioboard-1.0.0), cloned to refs/. This build emits the
# bracketed hardware self-test (***IO BOARD TEST STARTED/ENDED***, DI/AN/RS/power lines) that the
# v2.0.x RELEASE hex lacks. The station's Hardware-Test stage (A) flashes THIS, then reprograms the
# normal release (stage B). RTU build; same VX-0057 hardware -> self-test runs regardless of variant.
# refs/ lives at the workspace root (c:\claude\ioboard\refs), one level ABOVE io-board-testing.
_IOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))        # io-board-testing
_WS = os.path.abspath(os.path.join(_IOT, ".."))                                     # workspace (c:\claude\ioboard)
_TB_REL = os.path.join("refs", "vx-testbench-releases", "_ioboard-1.0.0", "extracted", "rtu-test")
_TB_CANDIDATES = [os.environ.get("TESTBENCH_DIR"),
                  os.path.join(_WS, _TB_REL), os.path.join(_IOT, _TB_REL)]
_TB_DIR = next((d for d in _TB_CANDIDATES if d and os.path.isdir(d)), os.path.join(_WS, _TB_REL))
TESTBENCH_MERGED = os.environ.get("TESTBENCH_MERGED", os.path.join(_TB_DIR, "merged.hex"))
TESTBENCH_FACTORY = os.environ.get(
    "TESTBENCH_FACTORY", os.path.join(_TB_DIR, "rtu-fw-vx-0057-factory_data-dev-v2.0.1-h-03cefeb7.hex"))
# Hardware self-test is identity-agnostic, so mirror the vendor rtu-test/dummy-id.xlsx: flash the
# testbench fw with this DUMMY VDUI/keys (the real per-unit VDUI is burned in Stage B). Not provisioned
# on any LNS, so LoRa can't OTAA-join with it (Rx timeout -> graded "comm OK", same as the vendor).
TESTBENCH_DUMMY_VDUI = os.environ.get("TESTBENCH_DUMMY_VDUI", "FFFF0000FFFF0000")
TESTBENCH_DUMMY_APP_EUI = os.environ.get("TESTBENCH_DUMMY_APP_EUI", "FFFF0000FFFF0000")
TESTBENCH_DUMMY_APP_KEY = os.environ.get("TESTBENCH_DUMMY_APP_KEY", "FFFF0000FFFF0000FFFF0000FFFF0000")

# Device identity + LoRaWAN keys written into the settings block (magic 0xA55A5AA5) at 0x000FC000.
# REAL per-device values live in gitignored secrets/station.env (DEVICE_UUID / DEVICE_APP_EUI /
# DEVICE_APP_KEY / TB_DEVICE_ID) and are loaded by _load_env above. Defaults here are placeholders so
# no credential is committed; copy secrets/station.env.example -> secrets/station.env and fill them in.
DEVICE_UUID = os.environ.get("DEVICE_UUID", "FFFF0000FFFF0000")
DEVICE_APP_EUI = os.environ.get("DEVICE_APP_EUI", "0000000000000000")
DEVICE_APP_KEY = os.environ.get("DEVICE_APP_KEY", "00000000000000000000000000000000")
# ThingsBoard device UUID (cloud-side verification; see tests/cloud-checkin/)
TB_DEVICE_ID = os.environ.get("TB_DEVICE_ID", "")

APP_TYPE = "io_board_app_tank_monitor"  # boot RTT 'Application type ...' for build type 0
                                        # (NOTE: 'Firmware title' is io_tank_monitor; app type is longer)
NRFJPROG_FAMILY = "NRF53"             # nrfjprog -f
JLINK_DEVICE = os.environ.get("JLINK_DEVICE", "nRF5340_xxAA_APP")   # pylink connect()
# MUST pin the DUT probe serial: 3 J-Links are on this bench (EDU 261011253,
# Compact Base 822006519, DK OB-SAM3U 683301942). 822006519 is the tank board
# (selected in the vendor programmer). Grabbing the wrong probe would hit another
# board. Verify read-only before flashing. Blank => pylink default (unsafe here).
JLINK_SERIAL = os.environ.get("JLINK_SERIAL", "822006519")
JLINK_IFACE_SPEED_KHZ = 4000

# --- RTT capture ------------------------------------------------------------
RTT_UP_BUFFER = 0                     # logging.conf: CONFIG_LOG_BACKEND_RTT_BUFFER=0
DEFAULT_BOOT_CAPTURE_S = 20           # window to see the boot + version block
DEFAULT_SELFTEST_CAPTURE_S = 40       # self-test + (full) radio tests can take longer
# Vendor rtu-test RTT control-block address (test.js RTT_ADDRESS). Attaching RTT at this fixed address
# BEFORE the reset avoids auto-detect latency so the self-test's opening lines aren't lost to ring
# overrun. Applies to the TESTBENCH firmware only; production captures still auto-detect (pass None).
TESTBENCH_RTT_CB = int(os.environ.get("TESTBENCH_RTT_CB", "0"), 0) or 0x20021BBC

# --- Boot / identity signatures (vx_app_version.c:90-93, vx_app.c:212) ------
SIG_FW_TITLE = r"Firmware title\s+(.+)"
SIG_FW_VERSION = r"Firmware version\s+(.+)"
SIG_APP_TYPE = r"Application type\s+(\S+)"
SIG_COMPILE_TIME = r"Compile time:\s+(.+)"
SIG_APP_INIT = r"Viaanix APP Init"
BOOT_MAX_S = 15                       # ⟶ confirm (USE-CASES open item)

# --- Self-test signatures (vx_app_testbench.c, tag 'testbench') -------------
SIG_TEST_START = r"\*\*\*IO BOARD TEST STARTED\*\*\*"
SIG_TEST_END = r"\*\*\*IO BOARD TEST ENDED\*\*\*"
SIG_EXT_MEM = r"External Memory:\s+(\w+)"
SIG_MAIN_POWER = r"Main Power 13\.8v or 12v:\s+(\w+)"
SIG_EXT_POWER = r"External Power 12v:\s+(\w+)"
SIG_PSC_AC = r"PSC 60 AC:\s+(\w+)"
SIG_PSC_PWR = r"PSC 60 Power 13\.8V:\s+(\w+)"
SIG_PSC_BATT = r"PSC 60 Battery:\s+(\w+)"
SIG_DI = r"DI(\d+)_(\w+):\s+(\w+)"                 # input#, ON/OFF, result
SIG_AN = r"AN(\d+):\s+(\w+)(?:\s+\((\d+)\s*uA\))?"  # channel#, OK/ERROR, [uA]
SIG_RS232 = r"RS232 ECHO COMMUNICATION:\s+(\w+)"
SIG_RS485 = r"RS485 ECHO COMMUNICATION:\s+(\w+)"
# Testbench radio self-test lines (from vendor test.js component set). LoRaWAN also logs
# "lorawan: Joined network!"; the testbench prints "LoraWAN Join: OK".
SIG_TB_LORA = r"LoraWAN Join:\s+(\w+)"
# Detailed LoRa join outcome (vendor test.js predicate): a Tx timeout means the SX1262 could not
# transmit (chip suspect -> FAIL); an Rx timeout means it transmitted OK but got no join-accept (chip
# healthy, just no gateway/LNS in range -> not a hardware fault); "Joined network!" = full success.
SIG_TB_LORA_JOINED = r"Joined network!"
SIG_TB_LORA_TX_TIMEOUT = r"MlmeConfirm failed\s*:\s*Tx timeout"
SIG_TB_LORA_RX_TIMEOUT = r"MlmeConfirm failed\s*:\s*Rx"
SIG_TB_CELL_SERIAL = r"CELL SERIAL:\s+(\w+)"
SIG_TB_CELL_SIM = r"CELL SIM:\s+(\w+)"

# --- Hardware-test counts / limits (from vendor rtu-test/test.js) ------------
DIGITAL_IN_COUNT = int(os.environ.get("DIGITAL_IN_COUNT", "4"))
ANALOG_IN_COUNT = int(os.environ.get("ANALOG_IN_COUNT", "5"))     # 4x 4-20mA + 1x general 0-10V
CURRENT_LIMIT_A = float(os.environ.get("CURRENT_LIMIT_A", "0.5")) # >0.5A = short (normal 200-300mA)
HW_TEST_CAPTURE_S = float(os.environ.get("HW_TEST_CAPTURE_S", "60"))  # self-test + LoRa-join window

# --- Relay (dig-out) state transitions (vx_app_tank.c:680-688) --------------
# "Channel: %u, state transition: <state> --> <state>"  and "Channel: %u state: <state>"
SIG_RELAY_XITION = r"Channel:\s*(\d+),\s*state transition:\s*(\S+)\s*-->\s*(\S+)"
SIG_RELAY_STATE = r"Channel:\s*(\d+)\s+state:\s*(\S+)"
RELAY_STATE_ON = "APP_IO_ON_RISING_EDGE"     # input rising past ON threshold -> output engaged
RELAY_STATE_OFF = "APP_IO_ON_FALLING_EDGE"   # input falling past OFF threshold -> output released

# --- Tank per-channel sample/band + uplink markers (vx_tank / tank.IO_HDL_OUT_*, vx_app) ----
# Confirmed live on RTT 2026-07-07: "Channel: %u state %u sample %u" (raw uA),
# "Channel: %u profile state: APP_IO_<BAND>", "Siren mode: %u", and DataType log markers
# (DT113 = threshold/tank-level event uplink, DATA_TYPE_61 = check-in). Siren ON/OFF event tag TBD.
SIG_TANK_SAMPLE = r"Channel:\s*(\d+)\s+state\s+(\d+)\s+sample\s+(\d+)"
SIG_TANK_PROFILE = r"Channel:\s*(\d+)\s+profile state:\s*APP_IO_(\w+)"
SIG_SIREN_MODE = r"Siren mode:\s*(\d+)"
SIG_SIREN_EVENT = r"(SIREN_(?:ON|OFF)|[Ss]et siren \w+ to (?:ON|OFF))"
SIG_DT_MARKER = r"\b(DT\d+|DATA_TYPE_\d+)\b"

# --- Firmware DEFAULT thresholds (compile-time, until cloud config; uA) -----
# vx_app_tank.c:41-57.  AI n -> Relay n.  4-20mA -> uA via factor 157.3 (io_handler.c).
DEFAULT_THRESHOLDS_UA = {
    "level": {"HH": 10000, "H": 9000, "L": 8000, "LL": 7000},  # >=HH/>=H ; <=L/<=LL
    "relay": {"on": 5000, "off": 10000},                        # ON<OFF mode by default
    "siren": {"on": 5000, "off": 10000},
}
ANALOG_TOLERANCE_PCT = 2.0     # ⟶ confirm (USE-CASES open item)
ANALOG_TOLERANCE_UA = 100      # ⟶ confirm
MA_CONVERSION_FACTOR = 157.3   # reference only (io_handler.c)

# Tank event names (DT61) — NOT printed on RTT; verified cloud-side (deferred).
TANK_LEVEL_EVENTS = ["TANK_LEVEL_HIGH_HIGH", "TANK_LEVEL_HIGH", "TANK_LEVEL_NORMAL",
                     "TANK_LEVEL_LOW", "TANK_LEVEL_LOW_LOW"]

# --- Waveshare current injector (auto 4-20 mA) ------------------------------
# Blank WAVESHARE_PORT => manual _ask_float fallback (current behaviour). Set to
# the USB-RS485 COM port (e.g. "COM5") to drive AO channels automatically.
WAVESHARE_PORT = os.environ.get("WAVESHARE_PORT", "")
WAVESHARE_BAUD = int(os.environ.get("WAVESHARE_BAUD", "9600"))
WAVESHARE_ADDR = int(os.environ.get("WAVESHARE_ADDR", "1"))
# let DAC + firmware settle before RTT capture
WAVESHARE_SETTLE_S = float(os.environ.get("WAVESHARE_SETTLE_S", "0.6"))
# Tank analog input (AI n) -> Waveshare output channel (AO n). Adjust to wiring.
AI_TO_AO = {1: 1, 2: 2, 3: 3, 4: 4}

# --- DEVICE-CONFIGURED thresholds (from ThingsBoard, 2026-07-07) -------------
# The live device 104D1526064B6130 runs cloud-pushed thresholds, NOT the firmware
# compile defaults above. Confirmed via TB (tankLevelThresholdsCh1*, all channels
# equal). S3/S4 sweeps MUST target THESE bands (12-18 mA), not 7-10 mA. Read live
# with tests/cloud-checkin before a run in case settings changed.
CONFIGURED_THRESHOLDS_UA = {
    "level": {"HH": 18000, "H": 16000, "L": 14000, "LL": 12000},  # >=HH/>=H ; <=L/<=LL
    "relay": {"on": 17000, "off": 13000},   # sh_outputThresholds* from TB 2026-07-07; read live to confirm
}
# S3/S4 sweep currents (mA) derived from the CONFIGURED bands (bracket each boundary).
S3_BANDS_CONFIGURED = [("rise->NORMAL", 15.0), ("rise->HIGH (>=16mA)", 16.5),
                       ("rise->HIGH_HIGH (>=18mA)", 18.5), ("fall->NORMAL", 15.0),
                       ("fall->LOW (<=14mA)", 13.5), ("fall->LOW_LOW (<=12mA)", 11.5)]
# S4 relay sweep (mA) bracketing the CONFIGURED relay thresholds (off ~13, on ~17 mA).
S4_STEPS_CONFIGURED = [("below (start)", 11.5), ("cross OFF thr (~13mA)", 13.5),
                       ("between (hold)", 15.5), ("cross ON thr (~17mA)", 17.5)]

# Current injector physical range (mA). Riiai/Waveshare do fixed 0-20 mA hardware; a
# 4-20 mA loop's valid band is 4-20. thresholds.py flags sweep points outside this as
# unreachable (>=20 = at ceiling; <4 = out-of-range-low, cloud#536).
INJECTOR_MIN_MA = float(os.environ.get("INJECTOR_MIN_MA", "0"))
INJECTOR_MAX_MA = float(os.environ.get("INJECTOR_MAX_MA", "20"))
LOOP_VALID_MIN_MA = 4.0
# The actual signal source the operator injects with. A 4-20 mA simulator CANNOT go below 4 mA, so
# functional-test steps targeting < SOURCE_MIN_MA are SKIPped (e.g. a LOW_LOW threshold of 2 mA is
# unreachable). Set SOURCE_MIN_MA=0 if using a 0-20 mA source.
SOURCE_MIN_MA = float(os.environ.get("SOURCE_MIN_MA", "4"))
SOURCE_MAX_MA = float(os.environ.get("SOURCE_MAX_MA", "20"))

# --- Bench instruments (station.py): PSU + current meter --------------------
# GW-Instek GPD-3303S PSU on COM4, board on CH2 (see HANDOFF). Output-enable is GLOBAL.
PSU_PORT = os.environ.get("PSU_PORT", "")            # e.g. COM4; blank => manual power
PSU_CHANNEL = int(os.environ.get("PSU_CHANNEL", "2"))
# GW-Instek GDM-8251A current meter. Blank METER_PORT => current read falls back to PSU IOUT<ch>?,
# then SKIP. Meter needs USB + GW-Instek driver + remote interface enabled to enumerate as a COM port.
METER_PORT = os.environ.get("METER_PORT", "")
METER_BAUD = int(os.environ.get("METER_BAUD", "115200"))   # GDM-8251A on this bench is set to 115200 (IDN-confirmed)

# --- ThingsBoard telemetry keys (cloud-side S2/S3/S4/S5 verification) --------
# The device reports full IO state to TB, so scopes can be verified cloud-side.
TB_KEYS = {
    "analog": [f"analogInput{n}current" for n in (1, 2, 3, 4)],   # uA
    "relay": [f"digitalOutput{n}" for n in (1, 2, 3, 4)],          # 0/1
    "digital_in": [f"digitalInput{n}" for n in (1, 2, 3, 4)],
    "power": ["mainPower", "powerSupplyPower", "powerSupplyAc", "powerSupplyBattery", "extBattDc"],
    "applogic": "io_board_app_tank_monitor_appLogic",             # e.g. ['HEARTBEAT'] / TANK_LEVEL_*
    "payload": "payloadHex",
}
