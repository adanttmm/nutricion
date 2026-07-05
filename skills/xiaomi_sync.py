"""
xiaomi_sync.py — Xiaomi Mi Home body composition sync.

Scale: yunmai.scales.ms104 (basic model "báscula") in Mi Home US region.
Data is stored in Mi Home cloud (api.io.mi.com), NOT in Mi Fitness (hlth.io.mi.com).

Auth strategy (automatic, no device notification):
  1. Read Firefox cookies from ~/.../cookies.sqlite  (Firefox already a trusted device)
  2. GET  serviceLogin?sid=xiaomiio (clean session) → _sign, qs, callback
  3. POST serviceLoginAuth2 WITH Firefox cookies  → ssecurity, nonce, location (no notification!)
  4. GET  location + clientSign → serviceToken cookie
  5. Mi Home API calls to us.api.io.mi.com use micloud's RC4 signing (ssecurity in POST body)

If Firefox cookies are unavailable or stale, fall back to email/password with one-time
device approval (interactive ENTER prompt, NOT polling — polling with the same sign never works).

Mi Home API signing (different from hlth.io.mi.com):
  - signed_nonce = base64(SHA256(decode(ssecurity) + decode(nonce)))
  - rc4_hash__ = base64(SHA1("POST&/path&k=v&signed_nonce"))
  - Each param RC4-encrypted with signed_nonce as key
  - signature = base64(SHA1("POST&/path&encrypted_k=encrypted_v&signed_nonce"))
  - POST body includes: encrypted params + signature + ssecurity (plaintext) + _nonce
"""

import base64
import glob
import hashlib
import json
import random
import shutil
import sqlite3
import struct
import tempfile
import time
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path

import requests

# ── Constants ──────────────────────────────────────────────────────────────────

_AUTH_BASE = "https://account.xiaomi.com"
_SID_IOT = "xiaomiio"           # Mi Home IoT (device list + scale data)
_LOCALE = "en_US"

_FF_UA = "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"
_MOBILE_UA = (
    "Android-7.1.1-1.0.0-ONEPLUS A3010-136-ABCDEFGHIJKLM APP/xiaomi.smarthome APPV/62830"
)

# Scale model substring for device discovery
_SCALE_MODELS = {"scale", "weight", "body", "yunmai", "mi_body"}

# Mi Home API region → host
_IOT_REGION_HOST = {
    "cn": "api.io.mi.com",
    "us": "us.api.io.mi.com",
    "eu": "de.api.io.mi.com",
    "sg": "sg.api.io.mi.com",
    "ru": "ru.api.io.mi.com",
    "i2": "i2.api.io.mi.com",
}


# ── Firefox cookie reader ──────────────────────────────────────────────────────

def _read_firefox_xiaomi_cookies() -> dict:
    """Extract Xiaomi-domain cookies from the most recently modified Firefox profile."""
    home = Path.home()
    patterns = [
        str(home / ".mozilla/firefox/*.default-release/cookies.sqlite"),
        str(home / ".mozilla/firefox/*.default/cookies.sqlite"),
        str(home / ".mozilla/firefox/*/cookies.sqlite"),
        str(home / "snap/firefox/common/.mozilla/firefox/*.default-release/cookies.sqlite"),
        str(home / "snap/firefox/common/.mozilla/firefox/*.default/cookies.sqlite"),
        str(home / "snap/firefox/common/.mozilla/firefox/*/cookies.sqlite"),
    ]
    found = []
    for pat in patterns:
        found.extend(glob.glob(pat))
    if not found:
        return {}

    cookies_db = max(found, key=lambda p: Path(p).stat().st_mtime)
    tmp = tempfile.mktemp(suffix=".sqlite")
    try:
        shutil.copy2(cookies_db, tmp)
        for ext in ("-wal", "-shm"):
            src = cookies_db + ext
            if Path(src).exists():
                shutil.copy2(src, tmp + ext)
        conn = sqlite3.connect(f"file:{tmp}?mode=ro&immutable=1", uri=True)
        rows = conn.execute(
            "SELECT name, value FROM moz_cookies WHERE host LIKE '%xiaomi.com'"
        ).fetchall()
        conn.close()
        return {r[0]: r[1] for r in rows}
    except Exception as e:
        print(f"  [firefox] Cookie read failed: {e}")
        return {}
    finally:
        for f in [tmp, tmp + "-wal", tmp + "-shm"]:
            try:
                Path(f).unlink(missing_ok=True)
            except Exception:
                pass


# ── Mi Home IoT crypto (micloud-compatible) ────────────────────────────────────

def _signed_nonce(ssecurity_b64: str, nonce_b64: str) -> str:
    """signed_nonce = base64(SHA256(decode(ssecurity) + decode(nonce)))."""
    combined = base64.b64decode(ssecurity_b64) + base64.b64decode(nonce_b64)
    return base64.b64encode(hashlib.sha256(combined).digest()).decode()


def _gen_nonce() -> str:
    """Generate nonce: base64(random_8_bytes_signed + int_minutes)."""
    rand_i = random.getrandbits(64) - 2 ** 63
    rand_b = rand_i.to_bytes(8, "big", signed=True)
    minutes = int(time.time() * 1000 / 60000)
    min_b = minutes.to_bytes(((minutes.bit_length() + 7) // 8), "big")
    return base64.b64encode(rand_b + min_b).decode()


def _iot_sign(url: str, method: str, signed_nonce: str, params: dict) -> str:
    """SHA1 signature for Mi Home IoT API.

    path = url.split("com")[1].replace("/app/", "/", 1)
    sign_string = "METHOD&path&k1=v1&k2=v2&signed_nonce"

    Note: replace only the FIRST /app/ — paths like /app/v2/record/app/history
    have a second /app/ that must be preserved.
    """
    path = url.split("com")[1].replace("/app/", "/", 1)
    parts = [method.upper(), path]
    for k in sorted(params):
        parts.append(f"{k}={params[k]}")
    parts.append(signed_nonce)
    return base64.b64encode(hashlib.sha1("&".join(parts).encode()).digest()).decode()


def _rc4_encrypt(signed_nonce_b64: str, payload: str) -> str:
    """RC4-drop[1024] encrypt payload with signed_nonce as key."""
    from Crypto.Cipher import ARC4
    rc4 = ARC4.new(base64.b64decode(signed_nonce_b64))
    rc4.encrypt(bytes(1024))
    return base64.b64encode(rc4.encrypt(payload.encode())).decode()


def _rc4_decrypt(signed_nonce_b64: str, payload_b64: str) -> bytes:
    """RC4-drop[1024] decrypt base64 payload."""
    from Crypto.Cipher import ARC4
    rc4 = ARC4.new(base64.b64decode(signed_nonce_b64))
    rc4.encrypt(bytes(1024))
    return rc4.encrypt(base64.b64decode(payload_b64))


def _build_iot_request(url: str, ssecurity: str, params: dict) -> dict:
    """Build RC4-encrypted POST body for Mi Home API call."""
    nonce = _gen_nonce()
    sn = _signed_nonce(ssecurity, nonce)

    p = {"data": json.dumps(params, separators=(",", ":"))}
    p["rc4_hash__"] = _iot_sign(url, "POST", sn, p)
    for k in list(p):
        p[k] = _rc4_encrypt(sn, p[k])
    p["signature"] = _iot_sign(url, "POST", sn, p)
    p["ssecurity"] = ssecurity
    p["_nonce"] = nonce
    return p, nonce, sn


def _parse_iot_response(response_text: str, nonce: str, sn: str, ssecurity: str) -> dict:
    """Decrypt Mi Home API response."""
    decrypt_key = _signed_nonce(ssecurity, nonce)
    raw = _rc4_decrypt(decrypt_key, response_text)
    return json.loads(raw)


# ── Xiaomi auth helpers ────────────────────────────────────────────────────────

def _parse_json(text: str) -> dict:
    return json.loads(text.lstrip("&&&START&&&").lstrip())


def _get_service_token(ssecurity: str, nonce: int, location: str) -> str:
    """Step 3: compute clientSign and follow location URL to get serviceToken."""
    nonce_str = str(nonce)
    client_sign = base64.b64encode(
        hashlib.sha1(f"nonce={nonce_str}&{ssecurity}".encode()).digest()
    ).decode()
    url = location + "&clientSign=" + urllib.parse.quote(client_sign)
    r = requests.get(url, allow_redirects=True, timeout=15)
    svc = None
    for c in r.cookies:
        if c.name == "serviceToken":
            svc = c.value
            break
    if not svc and r.history:
        for resp in r.history:
            for c in resp.cookies:
                if c.name == "serviceToken":
                    svc = c.value
                    break
    if not svc:
        raise ValueError("serviceToken not found in response after clientSign step")
    return svc


# ── Main client ────────────────────────────────────────────────────────────────

class XiaomiSyncClient:
    """Sync body composition data from Xiaomi Mi Home cloud (yunmai.scales.ms104).

    Auth uses Firefox cookies to suppress the device notification, then falls
    back to email/password with a one-time interactive approval if needed.
    """

    def __init__(self, email: str, password: str, region: str = "us",
                 token_cache: str = "data/xiaomi_cache/token.json",
                 device_id: str | None = None):
        self.email = email
        self.password = password
        self.region = region
        self.token_path = Path(token_cache)

        self.ssecurity: str | None = None
        self.service_token: str | None = None
        self.user_id: str | None = None
        self.c_user_id: str | None = None

        # Legacy compat
        self.app_token: str | None = None

    # ── Public API ─────────────────────────────────────────────────────────────

    def login(self, force: bool = False):
        if not force and self._load_cached_token():
            return
        if self._login_via_firefox():
            self._save_token()
            return
        self._login_via_password()
        self._save_token()

    def get_weight_records(self, days_back: int = 180) -> list[dict]:
        """Fetch body composition records from Mi Home cloud."""
        end_ts = int(time.time())
        start_ts = end_ts - days_back * 86400

        # Discover scale DID from device list
        scale_did = self._discover_scale_did()
        if not scale_did:
            print("  [weight] No scale device found in Mi Home account. Sync the scale via the app first.")
            return []

        host = _IOT_REGION_HOST.get(self.region, _IOT_REGION_HOST["us"])
        url = f"https://{host}/app/user/get_user_device_data"

        post_body, nonce, sn = _build_iot_request(url, self.ssecurity, {
            "did": scale_did,
            "uid": int(self.user_id),
            "time_start": start_ts,
            "time_end": end_ts,
            "limit": 200,
        })

        import datetime as dt
        import tzlocal
        tz_str = dt.datetime.now(tzlocal.get_localzone()).strftime("%z")
        tz_fmt = f"GMT{tz_str[:-2]}:{tz_str[-2:]}"

        r = requests.post(
            url, data=post_body,
            headers={
                "Accept-Encoding": "identity",
                "x-xiaomi-protocal-flag-cli": "PROTOCAL-HTTP2",
                "content-type": "application/x-www-form-urlencoded",
                "MIOT-ENCRYPT-ALGORITHM": "ENCRYPT-RC4",
            },
            cookies={
                "userId": self.user_id,
                "yetAnotherServiceToken": self.service_token,
                "serviceToken": self.service_token,
                "locale": _LOCALE,
                "timezone": tz_fmt,
                "is_daylight": str(time.daylight),
                "dst_offset": str(time.localtime().tm_isdst * 60 * 60 * 1000),
                "channel": "MI_APP_STORE",
            },
            timeout=30,
        )
        r.raise_for_status()
        result = _parse_iot_response(r.text, nonce, sn, self.ssecurity)

        if result.get("code") != 0:
            print(f"  [weight] API error: {result.get('message', result)}")
            return []

        records = result.get("result") or []
        if not records:
            print(f"  [weight] No records found for the last {days_back} days.")
            print("  [weight] Tip: step on the scale and open Mi Home app to sync, then re-run.")
            return []

        cutoff = datetime.now() - timedelta(days=days_back)
        results = [n for r in records if (n := self._normalize(r, cutoff))]
        return sorted(results, key=lambda x: x["date"] or "", reverse=True)

    def _discover_scale_did(self) -> str | None:
        """Call device_list to find the scale's DID."""
        host = _IOT_REGION_HOST.get(self.region, _IOT_REGION_HOST["us"])
        url = f"https://{host}/app/home/device_list"
        post_body, nonce, sn = _build_iot_request(url, self.ssecurity, {
            "getVirtualModel": True,
            "getHuamiDevices": 1,
            "get_split_device": False,
            "support_smart_home": True,
        })

        import datetime as dt
        import tzlocal
        tz_str = dt.datetime.now(tzlocal.get_localzone()).strftime("%z")
        tz_fmt = f"GMT{tz_str[:-2]}:{tz_str[-2:]}"

        r = requests.post(
            url, data=post_body,
            headers={
                "Accept-Encoding": "identity",
                "x-xiaomi-protocal-flag-cli": "PROTOCAL-HTTP2",
                "content-type": "application/x-www-form-urlencoded",
                "MIOT-ENCRYPT-ALGORITHM": "ENCRYPT-RC4",
            },
            cookies={
                "userId": self.user_id,
                "yetAnotherServiceToken": self.service_token,
                "serviceToken": self.service_token,
                "locale": _LOCALE,
                "timezone": tz_fmt,
                "is_daylight": str(time.daylight),
                "dst_offset": str(time.localtime().tm_isdst * 60 * 60 * 1000),
                "channel": "MI_APP_STORE",
            },
            timeout=15,
        )
        r.raise_for_status()
        result = _parse_iot_response(r.text, nonce, sn, self.ssecurity)
        devices = (result.get("result") or {}).get("list") or []
        for dev in devices:
            model = dev.get("model", "").lower()
            if any(kw in model for kw in _SCALE_MODELS):
                did = dev.get("did", "")
                name = dev.get("name", "?")
                print(f"  [scale] Found: {name} ({model}) did={did}")
                return did
        return None

    # ── Auth: Firefox session (suppresses device notification) ─────────────────

    def _login_via_firefox(self) -> bool:
        """Use Firefox's trusted browser session to obtain ssecurity without triggering
        a device notification. Works because the browser's deviceId is already approved."""
        ff_cookies = _read_firefox_xiaomi_cookies()
        if not ff_cookies:
            print("  [auth] Firefox cookies not found, using email/password.")
            return False

        required = {"passToken", "userId", "deviceId"}
        missing = required - set(ff_cookies)
        if missing:
            print(f"  [auth] Firefox cookies missing {missing}, using email/password.")
            return False

        print(f"  [auth] Firefox session found (deviceId={ff_cookies.get('deviceId','?')[:20]}...)")

        try:
            r1 = requests.get(
                f"{_AUTH_BASE}/pass/serviceLogin",
                params={"_json": "true", "sid": _SID_IOT, "_locale": _LOCALE},
                headers={"User-Agent": _FF_UA, "Accept-Language": "en-US,en;q=0.5"},
                timeout=15,
            )
            data1 = _parse_json(r1.text)
        except Exception as e:
            print(f"  [auth] serviceLogin failed: {e}")
            return False

        sign = data1.get("_sign", "")
        qs = data1.get("qs", "")
        callback = data1.get("callback", "")
        if not sign:
            print(f"  [auth] No _sign from serviceLogin: {list(data1.keys())}")
            return False

        # POST with Firefox cookies — browser's deviceId is trusted → no notification
        sess = requests.Session()
        for name, value in ff_cookies.items():
            for domain in [".xiaomi.com", "account.xiaomi.com"]:
                sess.cookies.set(name, value, domain=domain, path="/")

        pwd_hash = hashlib.md5(self.password.encode()).hexdigest().upper()
        try:
            r2 = sess.post(
                f"{_AUTH_BASE}/pass/serviceLoginAuth2",
                data={"qs": qs, "callback": callback, "_json": "true", "_sign": sign,
                      "user": self.email, "hash": pwd_hash, "sid": _SID_IOT, "_locale": _LOCALE},
                headers={"User-Agent": _FF_UA, "Content-Type": "application/x-www-form-urlencoded"},
                timeout=15,
            )
            data2 = _parse_json(r2.text)
        except Exception as e:
            print(f"  [auth] serviceLoginAuth2 failed: {e}")
            return False

        if data2.get("notificationUrl") and not data2.get("ssecurity"):
            print(f"  [auth] Unexpected device notification even with Firefox cookies.")
            return False

        if data2.get("code") != 0 or not data2.get("ssecurity"):
            print(f"  [auth] Firefox auth failed: code={data2.get('code')}")
            return False

        self._store_auth(data2)
        print(f"  [auth] Firefox auth successful.")
        return True

    # ── Auth: email/password fallback ─────────────────────────────────────────

    def _login_via_password(self):
        """Email/password auth. If a device notification appears, shows the URL and
        waits for ENTER, then re-fetches a fresh sign (stale signs don't work for retry)."""
        sign, qs, callback = self._step1_get_sign()
        self._step2_authenticate(sign, qs, callback)

    def _step1_get_sign(self) -> tuple[str, str, str]:
        r = requests.get(
            f"{_AUTH_BASE}/pass/serviceLogin",
            params={"_json": "true", "sid": _SID_IOT, "_locale": _LOCALE},
            headers={"User-Agent": _MOBILE_UA, "Accept-Language": "en-US,en;q=0.5"},
            timeout=15,
        )
        r.raise_for_status()
        data = _parse_json(r.text)
        sign = data.get("_sign", "")
        if not sign:
            raise ValueError(f"No _sign from serviceLogin: {list(data.keys())}")
        return sign, data.get("qs", ""), data.get("callback", "")

    def _step2_authenticate(self, sign: str, qs: str, callback: str):
        pwd_hash = hashlib.md5(self.password.encode()).hexdigest().upper()
        headers = {
            "User-Agent": _MOBILE_UA,
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept-Language": "en-US,en;q=0.5",
        }

        def _post(s, q, cb):
            return _parse_json(requests.post(
                f"{_AUTH_BASE}/pass/serviceLoginAuth2",
                data={"qs": q, "callback": cb, "_json": "true", "_sign": s,
                      "user": self.email, "hash": pwd_hash, "sid": _SID_IOT, "_locale": _LOCALE},
                headers=headers, timeout=15,
            ).text)

        data = _post(sign, qs, callback)

        # Device notification: sign is single-use; must get a fresh one after approval
        if "notificationUrl" in data and not data.get("ssecurity"):
            notif_url = data.get("notificationUrl", "")
            print("\n" + "═" * 68)
            print("  Xiaomi requiere verificar este dispositivo (solo la primera vez).")
            print()
            print("  1. Abre esta URL en Firefox (con sesión Xiaomi activa):")
            print(f"\n     {notif_url}\n")
            print("  2. Haz clic en APROBAR en la página que abre.")
            print("  3. Regresa aquí y presiona ENTER.")
            print("═" * 68)
            input("\n  [Presiona ENTER cuando hayas aprobado]: ")

            for attempt in range(1, 4):
                try:
                    sign2, qs2, cb2 = self._step1_get_sign()
                    data = _post(sign2, qs2, cb2)
                    if data.get("ssecurity") and data.get("location"):
                        print("  Dispositivo aprobado.")
                        break
                    print(f"  [{attempt}] ssecurity aún no disponible (code={data.get('code')}), reintentando...")
                    time.sleep(3)
                except Exception as e:
                    print(f"  [{attempt}] Error: {e}")
                    time.sleep(3)
            else:
                raise SystemExit(
                    "\n  Dispositivo no aprobado aún. Vuelve a correr el script después de aprobar.\n"
                    "  Una vez aprobado, el token se cachea 30 días y no se pedirá de nuevo."
                )

        code = data.get("code")
        if code != 0:
            raise ValueError(
                f"Xiaomi auth failed (code={code}): {data.get('description') or data.get('desc') or code}"
            )
        if not data.get("ssecurity") or not data.get("location"):
            raise ValueError(
                f"Missing ssecurity/location. Keys: {list(data.keys())}"
            )
        self._store_auth(data)

    # ── Token helpers ──────────────────────────────────────────────────────────

    def _store_auth(self, data: dict):
        self.ssecurity = data["ssecurity"]
        self._nonce = data.get("nonce", 0)
        self.user_id = str(data.get("userId", ""))
        self.c_user_id = data.get("cUserId", "")
        self._location = data.get("location", "")
        # Compute service token
        if self._location:
            self.service_token = _get_service_token(self.ssecurity, self._nonce, self._location)

    def _save_token(self):
        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        self.token_path.write_text(json.dumps({
            "ssecurity": self.ssecurity,
            "service_token": self.service_token,
            "user_id": self.user_id,
            "c_user_id": self.c_user_id,
            "region": self.region,
            "saved_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }, indent=2))

    def _load_cached_token(self) -> bool:
        if not self.token_path.exists():
            return False
        try:
            cached = json.loads(self.token_path.read_text())
            if not (cached.get("ssecurity") and cached.get("service_token") and cached.get("user_id")):
                return False
            saved = time.mktime(time.strptime(cached["saved_at"], "%Y-%m-%dT%H:%M:%S"))
            if time.time() - saved > 30 * 86400:
                return False
            self.ssecurity = cached["ssecurity"]
            self.service_token = cached["service_token"]
            self.user_id = cached["user_id"]
            self.c_user_id = cached.get("c_user_id", "")
            self.region = cached.get("region", self.region)
            return True
        except Exception:
            return False

    # ── Data normalization ──────────────────────────────────────────────────────

    def _normalize(self, rec: dict, cutoff: datetime) -> dict | None:
        ts = rec.get("time") or rec.get("timestamp") or rec.get("create_time") or 0
        if ts > 1e10:
            ts /= 1000
        dt = datetime.fromtimestamp(ts) if ts else None
        if not dt or dt < cutoff:
            return None

        def _f(*keys, scale=1.0):
            for k in keys:
                v = rec.get(k)
                if v not in (None, 0, ""):
                    try:
                        return round(float(v) * scale, 2)
                    except (ValueError, TypeError):
                        pass
            return None

        weight = _f("weight", scale=0.01) or _f("weight_kg") or _f("bodyWeight", scale=0.01)
        if not weight:
            return None

        return {
            "date": dt.strftime("%Y-%m-%d"),
            "weight_kg": weight,
            "bmi": _f("bmi", scale=0.01) or _f("bmi_val"),
            "body_fat_pct": _f("fat", scale=0.01) or _f("body_fat") or _f("bodyFat", scale=0.01),
            "fat_mass_kg": _f("fat_weight", scale=0.01) or _f("fat_mass"),
            "muscle_mass_kg": _f("muscle", scale=0.01) or _f("muscle_mass") or _f("muscleMass", scale=0.01),
            "bone_mass_kg": _f("bone", scale=0.01) or _f("bone_mass") or _f("boneMass", scale=0.01),
            "water_pct": _f("water", scale=0.01) or _f("body_water") or _f("bodyWater", scale=0.01),
            "protein_pct": _f("protein", scale=0.01) or _f("proteinRate", scale=0.01),
            "bmr": _f("bmr") or _f("basicMetabolism"),
            "visceral_fat": _f("visceral_fat") or _f("visceralFat"),
            "metabolic_age": _f("metabolic_age") or _f("bodyAge"),
            "lean_mass_kg": _f("lean_mass") or _f("leanBodyMass", scale=0.01),
            "subcutaneous_fat_pct": _f("subcutaneous_fat") or _f("subcutaneousFat", scale=0.01),
            "skeletal_muscle_pct": _f("skeletal_muscle") or _f("skeletalMuscle", scale=0.01),
            "impedance": _f("impedance") or _f("resistance"),
            "source": "xiaomi",
        }
