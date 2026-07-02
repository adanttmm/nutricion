"""
xiaomi_sync.py — fetches body composition data directly from Mi Fitness cloud API.
No Docker, no SmartScaleConnect — pure Python via requests.

Auth flow: Xiaomi account → serviceLogin → OAuth2 → Mi Fitness app token → weight records.
Token is cached in data/xiaomi_cache/token.json after first login.
"""
import hashlib
import json
import random
import string
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests

_REGION_CONFIG = {
    "cn": {
        "mifit_base": "https://api-mifit-cn.huami.com",
        "oauth_redirect": "https://api-mifit-cn.huami.com/huami.health.loginview.do",
        "dn": "api-mifit-cn.huami.com",
    },
    "us": {
        "mifit_base": "https://api-mifit.zepp.com",
        "oauth_redirect": "https://api-mifit.zepp.com/huami.health.loginview.do",
        "dn": "api-mifit.zepp.com",
    },
    "eu": {
        "mifit_base": "https://api-mifit.zepp.com",
        "oauth_redirect": "https://api-mifit.zepp.com/huami.health.loginview.do",
        "dn": "api-mifit.zepp.com",
    },
    "sg": {
        "mifit_base": "https://api-mifit.zepp.com",
        "oauth_redirect": "https://api-mifit.zepp.com/huami.health.loginview.do",
        "dn": "api-mifit.zepp.com",
    },
}

_AUTH_BASE = "https://account.xiaomi.com"
_CLIENT_ID = "428135909242707968"
_APP_NAME = "com.xiaomi.hm.health"
_APP_VERSION = "6.14.0"
_USER_AGENT = f"APP/{_APP_NAME}/{_APP_VERSION}"


class XiaomiSyncClient:

    def __init__(self, email: str, password: str, region: str = "cn",
                 token_cache: str = "data/xiaomi_cache/token.json"):
        self.email = email
        self.password = password
        cfg = _REGION_CONFIG.get(region, _REGION_CONFIG["us"])
        self.mifit_base = cfg["mifit_base"]
        self.oauth_redirect = cfg["oauth_redirect"]
        self.dn = cfg["dn"]
        self.token_path = Path(token_cache)
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": _USER_AGENT})
        self.app_token: str | None = None
        self.user_id: str | None = None

    # ── Public API ─────────────────────────────────────────────────────────────

    def login(self, force: bool = False):
        """Authenticate. Uses cached token if valid; re-auths only when needed."""
        if not force and self._load_cached_token():
            return
        self._full_login()
        self._save_token()

    def get_weight_records(self, days_back: int = 180) -> list[dict]:
        """Return normalized body composition records (newest first)."""
        to_ms = int(time.time() * 1000)
        url = f"{self.mifit_base}/users/{self.user_id}/weightRecords"
        r = self.session.get(
            url,
            params={"limit": 200, "toTime": to_ms},
            headers={"apptoken": self.app_token},
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()

        raw_list = (
            data.get("weightRecords") or
            data.get("data", {}).get("weightRecords") or
            (data if isinstance(data, list) else [])
        )

        cutoff = datetime.now() - timedelta(days=days_back)
        results = []
        for rec in raw_list:
            norm = self._normalize(rec, cutoff)
            if norm:
                results.append(norm)

        return sorted(results, key=lambda x: x["date"], reverse=True)

    def get_family_members(self) -> list[dict]:
        """List scale user profiles (for multi-user scales)."""
        r = self.session.get(
            f"{self.mifit_base}/huami.health.scale.familymember.get.json",
            headers={"apptoken": self.app_token},
            timeout=15,
        )
        r.raise_for_status()
        return r.json().get("members", [])

    # ── Auth internals ─────────────────────────────────────────────────────────

    def _full_login(self):
        # Use a persistent device_id so Xiaomi recognises the same device across runs.
        # Once approved via notification, every subsequent run with the same device_id
        # is trusted and skips the notification entirely.
        device_id = self._get_or_create_device_id()

        # 1. Get _sign from serviceLogin
        r = self.session.get(
            f"{_AUTH_BASE}/pass/serviceLogin",
            params={"_json": "true", "sid": "xiaomiio"},
            timeout=15,
        )
        sign_data = json.loads(_strip(r.text))
        sign = sign_data.get("_sign", "")

        # 2. Submit credentials
        r = self.session.post(
            f"{_AUTH_BASE}/pass/serviceLoginAuth2",
            data={
                "_json": "true",
                "hash": _md5(self.password),
                "sid": "xiaomiio",
                "user": self.email,
                "_sign": sign,
                "deviceId": device_id,
            },
            allow_redirects=False,
            timeout=15,
        )
        auth = json.loads(_strip(r.text))

        # Xiaomi detected a new device — requires one-time identity verification
        if "notificationUrl" in auth and "userId" not in auth:
            notif_url = auth["notificationUrl"]
            print("\n" + "═" * 60)
            print("  ⚠️  Xiaomi requiere verificar este dispositivo.")
            print(f"  ID de dispositivo: {device_id}  (guardado — no cambia en próximas ejecuciones)")
            print()
            print("  Pasos EXACTOS:")
            print("  1. Asegúrate de estar logueado en account.xiaomi.com en tu navegador")
            print("  2. Abre ESTA URL en ese navegador:")
            print(f"\n     {notif_url}\n")
            print("  3. La página mostrará una solicitud de aprobación — haz clic en")
            print("     CONFIRMAR / APROBAR / ALLOW (el botón verde/azul de confirmación)")
            print("  4. Espera ver 'Éxito' o una pantalla de confirmación")
            print("  5. Regresa aquí y presiona ENTER")
            print()
            print("  ℹ️  Tras aprobar, vuelve a ejecutar el script — la segunda ejecución")
            print("     usará el mismo ID de dispositivo ya aprobado y no pedirá esto de nuevo.")
            print("═" * 60)
            input()

            # Retry with the SAME session + SAME sign so Xiaomi links it to the approved
            # context. Avoid fresh session/sign strategies — they create a new device that
            # hasn't been approved yet.
            print("  Reintentando con el mismo dispositivo aprobado...")
            time.sleep(8)
            r = self.session.post(
                f"{_AUTH_BASE}/pass/serviceLoginAuth2",
                data={
                    "_json": "true",
                    "hash": _md5(self.password),
                    "sid": "xiaomiio",
                    "user": self.email,
                    "_sign": sign,
                    "deviceId": device_id,
                },
                allow_redirects=False,
                timeout=15,
            )
            auth = json.loads(_strip(r.text))
            print(f"  [debug retry] keys: {list(auth.keys())}, result: {auth.get('result')!r}")
            print(f"  [debug retry] location={auth.get('location','')[:100] or 'EMPTY'}")
            if "notificationUrl" in auth and "userId" not in auth:
                print()
                print("  ⚠️  Xiaomi sigue pidiendo verificación en el mismo intento.")
                print("  El dispositivo fue aprobado para la próxima ejecución.")
                print("  Vuelve a correr el script ahora — NO se pedirá la verificación de nuevo.")
                raise SystemExit(0)

        if auth.get("result") != "ok":
            desc = auth.get("description") or auth.get("desc") or ""
            keys = list(auth.keys())
            raise ValueError(
                f"Xiaomi login failed — result: {auth.get('result')!r}, "
                f"description: {desc!r}\n"
                f"Response keys: {keys}\n"
                f"Full response: {json.dumps(auth, ensure_ascii=False)[:800]}"
            )

        # userId is present on the direct-login path but absent on the notification path.
        # On the notification path we get 'location' + 'code' instead; user_id comes
        # from the Mi Fitness token exchange in step 5 below.
        user_id_val = _find_user_id(auth)
        self.user_id = str(user_id_val) if user_id_val else ""
        location = auth.get("location", "")

        # 3. Follow redirect to set session cookies (only present on the direct-login path)
        import urllib.parse as _up
        print(f"  [debug] location={'EMPTY' if not location else location[:120]}")
        print(f"  [debug] session cookies before step 3: {list(self.session.cookies.keys())}")
        if location:
            r3 = self.session.get(location, allow_redirects=True, timeout=15)
            print(f"  [debug] location follow: status={r3.status_code} final_url={r3.url[:120]}")

        print(f"  [debug] session cookies after step 3: {list(self.session.cookies.keys())}")

        # 4+5. Get OAuth2 access token and exchange for Mi Fitness app_token.
        #
        # Strategy A (HuaMi client — works on notification path):
        #   oauth2/authorize with client_id=HuaMi → redirect to S3 fallback URL containing
        #   ?access=TOKEN → POST account.huami.com/v2/client/login
        #
        # Strategy B (original Mi Fitness client — fallback):
        #   oauth2/authorize with client_id=428135909242707968 → redirect to loginview.do
        #   → GET loginview.do with grant_type=request_token
        token_data = None
        _HUAMI_REDIRECT = "https://s3-us-west-2.amazonaws.com/hm-registration/successsignin.html"
        _HUAMI_CLIENT = "HuaMi"

        # --- Strategy A ---
        ra = self.session.get(
            f"{_AUTH_BASE}/oauth2/authorize",
            params={
                "client_id": _HUAMI_CLIENT,
                "redirect_uri": _HUAMI_REDIRECT,
                "response_type": "code",
                "state": "REDIRECTION",
            },
            allow_redirects=True,
            timeout=15,
        )
        print(f"  [debug stratA] status={ra.status_code} final_url={ra.url[:200]}")
        # The final redirect URL contains ?access=TOKEN
        access_token_a = _up.parse_qs(_up.urlparse(ra.url).query).get("access", [None])[0]
        if not access_token_a:
            # Maybe in a JSON body
            try:
                access_token_a = ra.json().get("access") or ra.json().get("access_token")
            except Exception:
                pass
        print(f"  [debug stratA] access_token={'found' if access_token_a else 'NOT FOUND'}")
        if not access_token_a and ra.history:
            for h in ra.history:
                loc = h.headers.get("Location", "")
                access_token_a = _up.parse_qs(_up.urlparse(loc).query).get("access", [None])[0]
                if access_token_a:
                    print(f"  [debug stratA] found in redirect history")
                    break
        if access_token_a:
            rb = requests.post(
                "https://account.huami.com/v2/client/login",
                data={
                    "app_name": _APP_NAME,
                    "app_version": _APP_VERSION,
                    "country_code": "CN",
                    "device_id": device_id,
                    "device_model": "phone",
                    "grant_type": "access_token",
                    "third_name": "xiaomi-hm-mifit",
                    "login_token": access_token_a,
                    "dn": self.dn,
                },
                timeout=15,
            )
            print(f"  [debug stratA login] status={rb.status_code} resp={rb.text[:300]}")
            token_data = rb.json()

        # --- Strategy B (fallback) ---
        if not token_data or (not token_data.get("token_info") and not token_data.get("app_token")):
            print("  [debug] strategy A failed, trying strategy B (original loginview.do)")
            r4 = self.session.get(
                f"{_AUTH_BASE}/oauth2/authorize",
                params={
                    "_json": "true",
                    "client_id": _CLIENT_ID,
                    "pt": "1",
                    "redirect_uri": self.oauth_redirect,
                    "response_type": "code",
                },
                allow_redirects=False,
                timeout=15,
            )
            print(f"  [debug stratB oauth2] status={r4.status_code} Location={r4.headers.get('Location','')[:200]}")
            if r4.status_code == 200:
                print(f"  [debug stratB oauth2] body={r4.text[:300]}")
            code = _extract_oauth_code(r4)
            if not code:
                r4b = self.session.get(
                    f"{_AUTH_BASE}/oauth2/authorize",
                    params={
                        "_json": "true",
                        "client_id": _CLIENT_ID,
                        "pt": "1",
                        "redirect_uri": self.oauth_redirect,
                        "response_type": "code",
                    },
                    allow_redirects=True,
                    timeout=15,
                )
                code = _extract_oauth_code(r4b)
                print(f"  [debug stratB oauth2 follow] code={'found' if code else 'NOT FOUND'} resp={r4b.text[:200]}")
            if code:
                r5 = self.session.get(
                    f"{self.mifit_base}/huami.health.loginview.do",
                    params={
                        "code": code,
                        "grant_type": "request_token",
                        "third_name": "xiaomi-hm-mifit",
                        "app_name": _APP_NAME,
                        "app_version": _APP_VERSION,
                        "country_code": "CN",
                        "device_id": device_id,
                        "device_model": "phone",
                        "dn": self.dn,
                    },
                    timeout=15,
                )
                print(f"  [debug stratB loginview] status={r5.status_code} resp={r5.text[:300]}")
                token_data = r5.json()

        if not token_data:
            raise ValueError("Both token exchange strategies failed. Check debug lines above.")
        if not self.app_token:
            raise ValueError(f"Mi Fitness token not found in response: {token_data}")
        if not self.user_id:
            raise ValueError(f"user_id not found. token_info keys: {list(info.keys())}")

    # ── Token cache ────────────────────────────────────────────────────────────

    def _get_or_create_device_id(self) -> str:
        """Return the persistent device_id stored in the token cache, creating one if absent."""
        if self.token_path.exists():
            try:
                cached = json.loads(self.token_path.read_text())
                if cached.get("device_id"):
                    return cached["device_id"]
            except Exception:
                pass
        new_id = "".join(random.choices(string.ascii_uppercase + string.digits, k=16))
        # Persist immediately so it survives even if login fails later
        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            existing = json.loads(self.token_path.read_text()) if self.token_path.exists() else {}
        except Exception:
            existing = {}
        existing["device_id"] = new_id
        self.token_path.write_text(json.dumps(existing, indent=2))
        return new_id

    def _load_cached_token(self) -> bool:
        if not self.token_path.exists():
            return False
        try:
            cached = json.loads(self.token_path.read_text())
            self.app_token = cached["app_token"]
            self.user_id = cached["user_id"]
            return self._ping()
        except Exception:
            return False

    def _save_token(self):
        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        # Preserve device_id and any other fields already in the cache
        existing = {}
        if self.token_path.exists():
            try:
                existing = json.loads(self.token_path.read_text())
            except Exception:
                pass
        existing.update({"app_token": self.app_token, "user_id": self.user_id})
        self.token_path.write_text(json.dumps(existing, indent=2))

    def _ping(self) -> bool:
        try:
            r = self.session.get(
                f"{self.mifit_base}/users/{self.user_id}/weightRecords",
                params={"limit": 1},
                headers={"apptoken": self.app_token},
                timeout=10,
            )
            return r.status_code == 200
        except Exception:
            return False

    # ── Record normalization ───────────────────────────────────────────────────

    @staticmethod
    def _normalize(raw: dict, cutoff: datetime) -> dict | None:
        ts = raw.get("timestamp") or raw.get("time") or raw.get("date") or raw.get("Date")
        if not ts:
            return None
        try:
            if isinstance(ts, str) and not ts.isdigit():
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            else:
                t = float(ts)
                dt = datetime.fromtimestamp(t / 1000 if t > 1e10 else t)
        except Exception:
            return None

        if dt < cutoff:
            return None

        weight = raw.get("weight") or raw.get("Weight") or raw.get("weight_kg") or 0
        w = float(weight)
        if w <= 0:
            return None
        if w > 500:
            w /= 1000  # grams → kg

        out = {"date": dt.strftime("%Y-%m-%d"), "weight_kg": round(w, 2)}

        field_map = {
            "bmi": "bmi",
            "fat": "body_fat_pct", "bodyfat": "body_fat_pct",
            "body_fat": "body_fat_pct", "bodyFat": "body_fat_pct",
            "muscle": "muscle_mass_kg", "muscleMass": "muscle_mass_kg",
            "bone": "bone_mass_kg", "boneMass": "bone_mass_kg",
            "water": "water_pct", "bodyWater": "water_pct",
            "protein": "protein_pct",
            "visceralFat": "visceral_fat", "visceral_fat": "visceral_fat",
            "bmr": "bmr", "basalMetabolism": "bmr",
            "metabolicAge": "metabolic_age",
        }
        for raw_key, canon in field_map.items():
            val = raw.get(raw_key)
            if val is not None:
                try:
                    fval = float(val)
                    if fval != 0:
                        out[canon] = fval
                except (TypeError, ValueError):
                    pass

        if "fat_mass_kg" not in out and "body_fat_pct" in out:
            out["fat_mass_kg"] = round(w * out["body_fat_pct"] / 100, 2)
        if "lean_mass_kg" not in out and "fat_mass_kg" in out:
            out["lean_mass_kg"] = round(w - out["fat_mass_kg"], 2)

        return out


# ── Helpers ────────────────────────────────────────────────────────────────────

def _find_user_id(auth: dict):
    """Extract userId from various response shapes Xiaomi has used over API versions."""
    for key in ("userId", "user_id", "uid", "UserID"):
        if auth.get(key):
            return auth[key]
    # Nested under passInfo or similar
    for sub in ("passInfo", "data", "info"):
        obj = auth.get(sub)
        if isinstance(obj, dict):
            for key in ("userId", "user_id", "uid"):
                if obj.get(key):
                    return obj[key]
    return None


def _md5(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest().upper()


def _strip(text: str) -> str:
    for prefix in ("&&&START&&&", "_json_nonce="):
        if text.startswith(prefix):
            return text[len(prefix):]
    return text


def _extract_oauth_code(response: requests.Response) -> str | None:
    for resp in response.history + [response]:
        loc = resp.headers.get("Location", "")
        if "code=" in loc:
            return loc.split("code=")[1].split("&")[0]
    try:
        data = json.loads(_strip(response.text))
        for key in ("code", "access_token"):
            val = data.get(key)
            if val and isinstance(val, str) and len(val) > 4:
                return val
    except Exception:
        pass
    return None
