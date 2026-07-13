"""Minimal ThingsBoard (VX Olympus) REST client for read-only cloud check-in verification.

Endpoints verified against ThingsBoard docs (thingsboard.io/docs/reference/rest-api/,
.../user-guide/telemetry/). Creds load from secrets/station.env via python-dotenv:
  VX_TB_BASE_URL, VX_TB_USERNAME, VX_TB_PASSWORD
Read-only: only GET telemetry/attributes + the auth POST. Never writes to the device/cloud.
"""
from __future__ import annotations
import os
from pathlib import Path

import requests

try:
    from dotenv import load_dotenv
except ImportError:                      # python-dotenv is in the toolbox; degrade gracefully
    load_dotenv = None

SECRETS_ENV = Path(__file__).resolve().parents[2] / "secrets" / "station.env"


class TBError(Exception):
    pass


class ThingsBoard:
    def __init__(self, base=None, username=None, password=None, timeout=15):
        if load_dotenv and SECRETS_ENV.exists():
            load_dotenv(SECRETS_ENV)
        self.base = (base or os.environ.get("VX_TB_BASE_URL", "")).rstrip("/")
        self.username = username or os.environ.get("VX_TB_USERNAME", "")
        self.password = password or os.environ.get("VX_TB_PASSWORD", "")
        self.timeout = timeout
        self._token = None
        self._refresh = None
        self.s = requests.Session()
        if not self.base:
            raise TBError("VX_TB_BASE_URL not set (secrets/station.env)")

    # --- auth ---------------------------------------------------------------
    def login(self):
        if not (self.username and self.password):
            raise TBError("VX_TB_USERNAME / VX_TB_PASSWORD not set in secrets/station.env")
        r = self.s.post(f"{self.base}/api/auth/login",
                        json={"username": self.username, "password": self.password},
                        timeout=self.timeout)
        if r.status_code != 200:
            raise TBError(f"login failed HTTP {r.status_code}: {r.text[:200]}")
        d = r.json()
        self._token, self._refresh = d["token"], d.get("refreshToken")
        return self

    def _headers(self):
        if not self._token:
            self.login()
        return {"X-Authorization": f"Bearer {self._token}"}

    def _get(self, path, params=None):
        for attempt in (1, 2):
            r = self.s.get(f"{self.base}{path}", headers=self._headers(),
                           params=params, timeout=self.timeout)
            if r.status_code == 401 and attempt == 1:   # token expired -> re-login once
                self._token = None
                continue
            if r.status_code != 200:
                raise TBError(f"GET {path} HTTP {r.status_code}: {r.text[:200]}")
            return r.json()

    # --- device lookup ------------------------------------------------------
    def find_device(self, name):
        """Resolve a device by exact name (= VDUI hex). Tries tenant then customer scopes."""
        try:
            return self._get("/api/tenant/devices", {"deviceName": name})
        except TBError:
            pass
        # fallback: paginated search (works for tenant; customer users see their own)
        res = self._get("/api/tenant/deviceInfos",
                        {"pageSize": 100, "page": 0, "textSearch": name})
        for d in res.get("data", []):
            if d.get("name") == name:
                return d
        raise TBError(f"device named {name!r} not found (check name/VDUI and account scope)")

    def device_id(self, name):
        return self.find_device(name)["id"]["id"]

    # --- telemetry / attributes (read-only) --------------------------------
    def latest_timeseries(self, device_id, keys=None):
        p = {"useStrictDataTypes": "true"}
        if keys:
            p["keys"] = ",".join(keys)
        return self._get(f"/api/plugins/telemetry/DEVICE/{device_id}/values/timeseries", p)

    def timeseries_keys(self, device_id):
        return self._get(f"/api/plugins/telemetry/DEVICE/{device_id}/keys/timeseries")

    def attributes(self, device_id, scope=None):
        path = f"/api/plugins/telemetry/DEVICE/{device_id}/values/attributes"
        if scope:
            path += f"/{scope}"
        return self._get(path)

    # --- write (settings only; callers must enforce a device allowlist) -----
    def save_server_attributes(self, device_id, attrs):
        """POST SERVER_SCOPE attributes (e.g. settingsServer / settingsQueued). The ONLY write path;
        used by settings.py which restricts it to the authorized test device."""
        r = self.s.post(f"{self.base}/api/plugins/telemetry/DEVICE/{device_id}/attributes/SERVER_SCOPE",
                        headers=self._headers(), json=attrs, timeout=self.timeout)
        if r.status_code == 401:                     # token expired -> re-login once
            self._token = None
            r = self.s.post(f"{self.base}/api/plugins/telemetry/DEVICE/{device_id}/attributes/SERVER_SCOPE",
                            headers=self._headers(), json=attrs, timeout=self.timeout)
        if r.status_code not in (200, 204):
            raise TBError(f"save_server_attributes HTTP {r.status_code}: {r.text[:200]}")
        return True
