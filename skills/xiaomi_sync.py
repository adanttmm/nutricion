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
# Mimic the exact Mi Fitness Android app — Xiaomi uses the User-Agent + deviceId
# combination to decide whether to trust a login without notification.
_USER_AGENT = (
    f"MiFit/{_APP_VERSION} (Android 13; zh_CN; "
    f"Mi 11; Build/TKQ1.220829.002) okhttp/4.10.0"
)


class XiaomiSyncClient:

    def __init__(self, email: str, password: str, region: str = "cn",
                 token_cache: str = "data/xiaomi_cache/token.json",
                 device_id: str | None = None):
        self.email = email
        self.password = password
        cfg = _REGION_CONFIG.get(region, _REGION_CONFIG["us"])
        self.mifit_base = cfg["mifit_base"]
        self.oauth_redirect = cfg["oauth_redirect"]
        self.dn = cfg["dn"]
        self.token_path = Path(token_cache)
        self._forced_device_id = device_id  # real Android ID from env/arg
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": _USER_AGENT,
            "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
        })
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
        device_id = self._get_or_create_device_id()
        self._clear_pending_auth()

        # 1. Get _sign
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

        # Xiaomi requires device verification for unrecognised devices.
        # _sign is a one-time nonce — it is consumed on the first POST.
        # Polling with the SAME sign always returns result=ok/location=EMPTY.
        # The correct approach: save the device_id, show the notification URL,
        # and tell the user to run the script again after approving.
        # The second run gets a FRESH sign + same device_id → Xiaomi sees the
        # trusted device and skips the notification.
        if "notificationUrl" in auth and "userId" not in auth:
            notif_url = auth["notificationUrl"]
            self._save_pending_auth(sign, device_id, notif_url)
            print("\n" + "═" * 60)
            print("  ⚠️  Xiaomi requiere verificar este dispositivo.")
            print()
            print("  1. Abre ESTA URL en tu navegador (logueado en Xiaomi):")
            print(f"\n     {notif_url}\n")
            print("  2. Haz clic en CONFIRMAR / APROBAR / ALLOW en el aviso")
            print("  3. Vuelve a correr el script — ya no pedirá verificación")
            print("═" * 60)
            raise SystemExit(
                "\n  🔔  Aprueba la verificación y vuelve a correr el script."
            )

        if auth.get("result") != "ok":
            desc = auth.get("description") or auth.get("desc") or ""
            keys = list(auth.keys())
            raise ValueError(
                f"Xiaomi login failed — result: {auth.get('result')!r}, "
                f"description: {desc!r}\n"
                f"Response keys: {keys}\n"
                f"Full response: {json.dumps(auth, ensure_ascii=False)[:800]}"
            )

        user_id_val = _find_user_id(auth)
        self.user_id = str(user_id_val) if user_id_val else ""
        location = auth.get("location", "")

        # 3. Follow redirect to set session cookies
        import urllib.parse as _up
        print(f"  [debug] location={'EMPTY' if not location else location[:120]}")
        print(f"  [debug] session cookies before step 3: {list(self.session.cookies.keys())}")
        if location:
            r3 = self.session.get(location, allow_redirects=True, timeout=15)
            print(f"  [debug] location follow: status={r3.status_code} final_url={r3.url[:120]}")

        print(f"  [debug] session cookies after step 3: {list(self.session.cookies.keys())}")

        # 4+5. Get OAuth2 access token and exchange for Mi Fitness app_token.
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
        access_token_a = _up.parse_qs(_up.urlparse(ra.url).query).get("access", [None])[0]
        if not access_token_a:
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

        # Extract app_token + user_id from whichever shape the response has
        info = token_data.get("token_info") or token_data
        self.app_token = info.get("app_token") or token_data.get("app_token")
        uid = info.get("user_id") or token_data.get("user_id") or _find_user_id(token_data)
        if uid:
            self.user_id = str(uid)

        if not self.app_token:
            raise ValueError(f"Mi Fitness token not found in response: {token_data}")
        if not self.user_id:
            raise ValueError(f"user_id not found. token_info keys: {list(info.keys())}")

    def _exchange_service_token_for_app_token(self, service_token: str, device_id: str,
                                               token_name: str = "serviceToken"):
        """Exchange a Xiaomi browser token (serviceToken or passToken) for a Mi Fitness app_token."""
        import urllib.parse as _up
        token_data = None

        # Strategy 0: use passToken/serviceToken cookie to get a xiaomiio-specific
        # serviceToken via serviceLogin, then exchange with Huami.
        # A valid passToken already proves authentication — Xiaomi issues a
        # service-specific token without triggering the notification flow.
        for cookie_domain in ("account.xiaomi.com", ".xiaomi.com", "xiaomi.com"):
            s = requests.Session()
            s.headers.update({"User-Agent": _USER_AGENT})
            for cname in ("passToken", "serviceToken"):
                s.cookies.set(cname, service_token, domain=cookie_domain, path="/")

            rsl = s.get(
                f"{_AUTH_BASE}/pass/serviceLogin",
                params={"_json": "true", "sid": "xiaomiio"},
                timeout=15,
            )
            sl_data = json.loads(_strip(rsl.text))
            print(f"  [debug strat0/{cookie_domain}] serviceLogin code={sl_data.get('code')} result={sl_data.get('result')!r} location={sl_data.get('location','')[:80] or 'EMPTY'}")

            # If Xiaomi recognised the session it may return serviceToken directly
            svc_tok = sl_data.get("serviceToken") or sl_data.get("ssecurity")
            location = sl_data.get("location", "")
            if location:
                print(f"  [debug strat0/{cookie_domain}] got location! following...")
                r_loc = s.get(location, allow_redirects=True, timeout=15)
                print(f"  [debug strat0/{cookie_domain}] loc status={r_loc.status_code}")
                svc_tok = svc_tok or s.cookies.get("serviceToken")

            if svc_tok:
                print(f"  [debug strat0/{cookie_domain}] got xiaomiio serviceToken (len={len(svc_tok)}, prefix={svc_tok[:20]!r}) — trying Huami")
                # Try both international and CN-specific Huami login endpoints
                huami_endpoints = [
                    "https://account-cn.huami.com/v2/client/login",
                    "https://account.huami.com/v2/client/login",
                ]
                for endpoint in huami_endpoints:
                    for grant in ("xiaomi_login_token", "thirdparty_login"):
                        rb = requests.post(
                            endpoint,
                            data={"app_name": _APP_NAME, "app_version": _APP_VERSION,
                                  "country_code": "CN", "device_id": device_id,
                                  "device_model": "phone", "grant_type": grant,
                                  "third_name": "xiaomi-hm-mifit",
                                  "login_token": svc_tok, "dn": self.dn},
                            timeout=15,
                        )
                        print(f"  [debug strat0 huami/{grant} {endpoint.split('/')[2]}] status={rb.status_code} resp={rb.text[:300]}")
                        try:
                            td = rb.json()
                            if td.get("token_info") or td.get("app_token"):
                                token_data = td
                                break
                        except Exception:
                            pass
                    if token_data:
                        break
                if token_data:
                    break

            # Also try HuaMi oauth2 with the cookie-authenticated session
            _HUAMI_REDIRECT = "https://s3-us-west-2.amazonaws.com/hm-registration/successsignin.html"
            ra = s.get(
                f"{_AUTH_BASE}/oauth2/authorize",
                params={"client_id": "HuaMi", "redirect_uri": _HUAMI_REDIRECT,
                        "response_type": "code", "state": "REDIRECTION"},
                allow_redirects=True, timeout=15,
            )
            access_token = _up.parse_qs(_up.urlparse(ra.url).query).get("access", [None])[0]
            print(f"  [debug strat0/{cookie_domain} oauth2] status={ra.status_code} access={'found' if access_token else 'NOT FOUND'} url={ra.url[:100]}")
            if access_token:
                rb = requests.post(
                    "https://account.huami.com/v2/client/login",
                    data={"app_name": _APP_NAME, "app_version": _APP_VERSION,
                          "country_code": "CN", "device_id": device_id, "device_model": "phone",
                          "grant_type": "access_token", "third_name": "xiaomi-hm-mifit",
                          "login_token": access_token, "dn": self.dn},
                    timeout=15,
                )
                print(f"  [debug strat0/{cookie_domain} huami] status={rb.status_code} resp={rb.text[:300]}")
                try:
                    td = rb.json()
                    if td.get("token_info") or td.get("app_token"):
                        token_data = td
                        break
                except Exception:
                    pass

        if not token_data:
            raise ValueError(
                "Token exchange failed — all strategies returned nothing.\n"
                "Pega la salida completa de este comando para diagnosticar."
            )
        info = token_data.get("token_info") or token_data
        self.app_token = info.get("app_token") or token_data.get("app_token")
        uid = info.get("user_id") or token_data.get("user_id") or _find_user_id(token_data)
        if uid:
            self.user_id = str(uid)
        if not self.app_token:
            raise ValueError(f"Mi Fitness token not found after exchange: {token_data}")

    def _exchange_with_all_cookies(self, cookies: dict, device_id: str):
        """Use the full browser cookie jar to obtain a Mi Fitness app_token.

        Tries three paths in order:
          A. oauth2/authorize → Huami access_token exchange  (cleanest)
          B. serviceLogin STS → Huami serviceToken exchange  (various grant types)
          C. loginview.do with STS token as authorization_code  (legacy path)
        """
        import urllib.parse as _up

        _HUAMI_REDIRECT = "https://s3-us-west-2.amazonaws.com/hm-registration/successsignin.html"
        _FULL_DN = (
            "account-cn.huami.com,api-user-cn.huami.com,"
            "api-watch-cn.huami.com,api-mifit-cn.huami.com"
        )

        s = requests.Session()
        s.headers.update({
            "User-Agent": _USER_AGENT,
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        })
        for name, value in cookies.items():
            s.cookies.set(name, value, domain="account.xiaomi.com", path="/")
            s.cookies.set(name, value, domain=".xiaomi.com", path="/")
        print(f"  [cookies loaded] names: {sorted(cookies.keys())}")

        def _try_huami(token: str, grant: str, dn: str, label: str):
            for ep in ("https://account-cn.huami.com/v2/client/login",
                       "https://account.huami.com/v2/client/login"):
                r = requests.post(ep, data={
                    "app_name": _APP_NAME, "app_version": _APP_VERSION,
                    "country_code": "CN", "device_id": device_id, "device_model": "phone",
                    "grant_type": grant, "third_name": "xiaomi-hm-mifit",
                    "login_token": token, "dn": dn,
                }, timeout=15)
                host = ep.split("/")[2]
                print(f"  [huami/{label}/{grant}/{host}] {r.status_code} {r.text[:200]}")
                try:
                    td = r.json()
                    info = td.get("token_info") or td
                    at = info.get("app_token") or td.get("app_token")
                    uid = info.get("user_id") or td.get("user_id") or _find_user_id(td)
                    if at:
                        self.app_token = at
                        if uid:
                            self.user_id = str(uid)
                        return True
                except Exception:
                    pass
            return False

        # ── PATH A: oauth2/authorize → code → loginview.do ───────────────────
        # Try several redirect URIs — the registered one must match exactly.
        # Mobile apps use a custom scheme (mifit://oauth) rather than https.
        _REDIRECT_CANDIDATES = [
            self.oauth_redirect,                                         # https loginview.do
            "mifit://oauth",                                             # Android deep link
            "com.xiaomi.hm.health://oauth",                             # package scheme
            "https://s3-us-west-2.amazonaws.com/hm-registration/successsignin.html",
        ]
        code = None
        used_redirect = None
        for redirect_uri in _REDIRECT_CANDIDATES:
            ra = s.get(
                f"{_AUTH_BASE}/oauth2/authorize",
                params={"client_id": _CLIENT_ID, "redirect_uri": redirect_uri,
                        "response_type": "code", "scope": "1"},
                allow_redirects=False, timeout=15,
            )
            loc_hdr = ra.headers.get("Location", "")
            print(f"  [path-A {redirect_uri[:40]}] status={ra.status_code} Location={loc_hdr[:100] or ra.text[:80]}")
            code = _extract_oauth_code(ra)
            if code:
                used_redirect = redirect_uri
                break
            # If redirect happened, follow it
            if ra.status_code in (301, 302, 303) and loc_hdr:
                ra2 = s.get(loc_hdr, allow_redirects=True, timeout=15)
                code = _extract_oauth_code(ra2)
                if code:
                    used_redirect = redirect_uri
                    break

        print(f"  [path-A] code={'found redirect='+used_redirect if code else 'NOT FOUND on any redirect URI'}")
        if code:
            r5 = s.get(
                f"{self.mifit_base}/huami.health.loginview.do",
                params={"code": code, "grant_type": "request_token",
                        "third_name": "xiaomi-hm-mifit", "app_name": _APP_NAME,
                        "app_version": _APP_VERSION, "country_code": "CN",
                        "device_id": device_id, "device_model": "phone", "dn": _FULL_DN},
                timeout=15,
            )
            print(f"  [path-A loginview.do] {r5.status_code} {r5.text[:300]}")
            try:
                td = r5.json()
                info = td.get("token_info") or td
                at = info.get("app_token") or td.get("app_token")
                uid = info.get("user_id") or td.get("user_id") or _find_user_id(td)
                if at:
                    self.app_token = at
                    if uid:
                        self.user_id = str(uid)
                    return
            except Exception:
                pass

        # ── PATH B: serviceLogin STS → Huami ─────────────────────────────────
        rsl = s.get(
            f"{_AUTH_BASE}/pass/serviceLogin",
            params={"_json": "true", "sid": "xiaomiio"},
            timeout=15,
        )
        sl = json.loads(_strip(rsl.text))
        location = sl.get("location", "")
        print(f"  [path-B STS] code={sl.get('code')} location={'ok' if location else 'EMPTY'}")

        svc_tok = None
        if location and sl.get("code") == 0:
            r_loc = s.get(location, allow_redirects=True, timeout=15)
            print(f"  [path-B STS] follow status={r_loc.status_code} body={r_loc.text[:80]}")
            for c in s.cookies:
                if c.name == "serviceToken":
                    svc_tok = c.value
                    break
            print(f"  [path-B STS] serviceToken={'len=' + str(len(svc_tok)) if svc_tok else 'NOT FOUND'}")

        if svc_tok:
            for grant in ("xiaomi_login_token", "thirdparty_login", "xiaomi_login"):
                for dn in (_FULL_DN, self.dn):
                    if _try_huami(svc_tok, grant, dn, "pathB"):
                        return

            # ── PATH C: loginview.do with STS token as authorization_code ─────
            params = {
                "lang": "zh_CN", "country_code": "CN",
                "app_version": _APP_VERSION, "app_name": _APP_NAME,
                "login_platform": "huami_xiaomi", "phone_type": "android",
                "device_id": device_id, "dn": _FULL_DN,
                "redirect_uri": _HUAMI_REDIRECT,
                "authorization_code": svc_tok,
            }
            r5 = requests.get(
                f"{self.mifit_base}/huami.health.loginview.do", params=params, timeout=15)
            print(f"  [path-C loginview.do] {r5.status_code} {r5.text[:300]}")
            try:
                td = r5.json()
                info = td.get("token_info") or td
                at = info.get("app_token") or td.get("app_token")
                uid = info.get("user_id") or td.get("user_id") or _find_user_id(td)
                if at:
                    self.app_token = at
                    if uid:
                        self.user_id = str(uid)
                    return
            except Exception:
                pass

        # ── PATH D: passToken as POST body → real serviceLoginAuth2 result ──────
        # passToken posted as a body param (not cookie) re-authenticates without
        # needing the password hash, and avoids the device-notification flow
        # because Xiaomi treats it as a session renewal, not a new device login.
        pass_token = cookies.get("passToken") or cookies.get("serviceToken")
        if pass_token:
            # Fresh sign — required per request
            r_sign = requests.get(
                f"{_AUTH_BASE}/pass/serviceLogin",
                params={"_json": "true", "sid": "xiaomiio"}, timeout=15,
            )
            sign_d = json.loads(_strip(r_sign.text)).get("_sign", "")
            print(f"  [path-D] got sign={'ok' if sign_d else 'EMPTY'}")

            r_auth = requests.post(
                f"{_AUTH_BASE}/pass/serviceLoginAuth2",
                data={
                    "_json": "true", "_sign": sign_d,
                    "sid": "xiaomiio", "user": self.email,
                    "deviceId": device_id, "passToken": pass_token,
                },
                allow_redirects=False, timeout=15,
            )
            auth_d = json.loads(_strip(r_auth.text))
            loc_d = auth_d.get("location", "")
            print(f"  [path-D] result={auth_d.get('result')!r} code={auth_d.get('code')} "
                  f"notif={'YES' if 'notificationUrl' in auth_d else 'no'} "
                  f"location={'ok' if loc_d else 'EMPTY'}")
            print(f"  [path-D] full response: {json.dumps(auth_d, ensure_ascii=False)[:400]}")

            if auth_d.get("result") == "ok" and loc_d:
                # Follow location → sets serviceToken + ssecurity in session
                r_loc = requests.Session()
                r_loc_resp = r_loc.get(loc_d, allow_redirects=True, timeout=15)
                print(f"  [path-D] location follow status={r_loc_resp.status_code}")
                svc_d = None
                for c in r_loc.cookies:
                    if c.name == "serviceToken":
                        svc_d = c.value
                        break
                ssecurity_d = auth_d.get("ssecurity", "")
                print(f"  [path-D] serviceToken={'len='+str(len(svc_d)) if svc_d else 'NOT FOUND'} ssecurity={'ok' if ssecurity_d else 'missing'}")

                if svc_d:
                    for grant in ("xiaomi_login_token", "thirdparty_login"):
                        for dn in (_FULL_DN, self.dn):
                            if _try_huami(svc_d, grant, dn, "pathD"):
                                return

        raise ValueError(
            "No se pudo obtener app_token con las cookies del navegador.\n"
            "Pega la salida de debug completa para diagnosticar.\n"
            "Si las cookies tienen más de unas horas, exporta unas nuevas."
        )

    # ── Token cache ────────────────────────────────────────────────────────────

    def _save_pending_auth(self, sign: str, device_id: str, notification_url: str = ""):
        """Record that a notification was sent so the next run can skip re-notifying.

        We only store the device_id — the sign is a one-time nonce and is useless
        after the first POST.  The next run gets a fresh sign with the same device_id,
        and Xiaomi skips the notification because the device is already approved.
        """
        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        existing = {}
        if self.token_path.exists():
            try:
                existing = json.loads(self.token_path.read_text())
            except Exception:
                pass
        existing["pending_auth"] = {
            "device_id": device_id,
            "notification_url": notification_url,
            "saved_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        # Persist device_id at top level too so _get_or_create_device_id reuses it
        existing["device_id"] = device_id
        self.token_path.write_text(json.dumps(existing, indent=2))

    def _load_pending_auth(self) -> dict | None:
        """Return True if a notification was previously sent (within 30 min)."""
        if not self.token_path.exists():
            return None
        try:
            cached = json.loads(self.token_path.read_text())
            p = cached.get("pending_auth")
            if not p:
                return None
            saved_at = time.mktime(time.strptime(p["saved_at"], "%Y-%m-%dT%H:%M:%S"))
            if time.time() - saved_at > 1800:
                self._clear_pending_auth()
                return None
            return p
        except Exception:
            return None

    def _clear_pending_auth(self):
        if not self.token_path.exists():
            return
        try:
            cached = json.loads(self.token_path.read_text())
            cached.pop("pending_auth", None)
            self.token_path.write_text(json.dumps(cached, indent=2))
        except Exception:
            pass

    def _get_or_create_device_id(self) -> str:
        """Return the device_id to use for auth.

        Priority:
        1. XIAOMI_DEVICE_ID env var / constructor arg (real Android ID from the phone)
        2. Previously persisted ID in the token cache
        3. Generated random ID (last resort — likely triggers notification every time)
        """
        if self._forced_device_id:
            self._persist_device_id(self._forced_device_id)
            return self._forced_device_id

        if self.token_path.exists():
            try:
                cached = json.loads(self.token_path.read_text())
                if cached.get("device_id"):
                    return cached["device_id"]
            except Exception:
                pass

        # Generate as lowercase hex to match Android's android_id format
        new_id = "".join(random.choices("0123456789abcdef", k=16))
        self._persist_device_id(new_id)
        return new_id

    def _persist_device_id(self, device_id: str):
        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            existing = json.loads(self.token_path.read_text()) if self.token_path.exists() else {}
        except Exception:
            existing = {}
        existing["device_id"] = device_id
        self.token_path.write_text(json.dumps(existing, indent=2))

    def _load_cached_token(self) -> bool:
        if not self.token_path.exists():
            return False
        try:
            cached = json.loads(self.token_path.read_text())
            if cached.get("app_token") and cached.get("user_id"):
                self.app_token = cached["app_token"]
                self.user_id = cached["user_id"]
                self.session.headers.update({"apptoken": self.app_token})
                return True
        except Exception:
            pass
        return False

    def _save_token(self):
        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        existing = {}
        if self.token_path.exists():
            try:
                existing = json.loads(self.token_path.read_text())
            except Exception:
                pass
        existing.update({"app_token": self.app_token, "user_id": self.user_id})
        self.token_path.write_text(json.dumps(existing, indent=2))

    def _validate_token(self) -> bool:
        try:
            r = self.session.get(
                f"{self.mifit_base}/users/{self.user_id}/weightRecords",
                params={"limit": 1, "toTime": int(time.time() * 1000)},
                headers={"apptoken": self.app_token},
                timeout=10,
            )
            return r.status_code == 200
        except Exception:
            return False

    # ── Data normalization ─────────────────────────────────────────────────────

    def _normalize(self, rec: dict, cutoff: datetime) -> dict | None:
        ts = rec.get("timestamp") or rec.get("time") or rec.get("date")
        if not ts:
            return None
        if isinstance(ts, (int, float)):
            if ts > 1e10:
                ts = ts / 1000
            dt = datetime.fromtimestamp(ts)
        else:
            try:
                dt = datetime.fromisoformat(str(ts)[:10])
            except Exception:
                return None
        if dt < cutoff:
            return None

        def _scale(val, divisor=100):
            return round(val / divisor, 1) if val else None

        weight_raw = rec.get("weight") or rec.get("weight_kg")
        weight_kg = None
        if weight_raw:
            weight_kg = _scale(weight_raw) if weight_raw > 500 else weight_raw

        return {
            "date": dt.strftime("%Y-%m-%d"),
            "weight_kg": weight_kg,
            "bmi": _scale(rec.get("bmi")),
            "body_fat_pct": _scale(rec.get("fatRate") or rec.get("body_fat_pct")),
            "fat_mass_kg": _scale(rec.get("fat") or rec.get("fat_mass_kg")),
            "muscle_mass_kg": _scale(rec.get("muscle") or rec.get("muscleMass") or rec.get("muscle_mass_kg")),
            "bone_mass_kg": _scale(rec.get("bone") or rec.get("boneMass") or rec.get("bone_mass_kg")),
            "water_pct": _scale(rec.get("water") or rec.get("waterRate") or rec.get("water_pct")),
            "protein_pct": _scale(rec.get("protein") or rec.get("proteinRate") or rec.get("protein_pct")),
            "bmr": rec.get("bmr") or rec.get("basalMetabolism"),
            "visceral_fat": rec.get("visceralFat") or rec.get("visceral_fat"),
            "metabolic_age": rec.get("metabolicAge") or rec.get("metabolic_age"),
            "lean_mass_kg": _scale(rec.get("leanBodyMass") or rec.get("lean_mass_kg")),
            "skeletal_muscle_pct": _scale(rec.get("skeletalMuscleRate") or rec.get("skeletal_muscle_pct")),
            "impedance": rec.get("impedance"),
        }


# ── Helpers ────────────────────────────────────────────────────────────────────

def _md5(s: str) -> str:
    return hashlib.md5(s.encode()).hexdigest().upper()


def _strip(text: str) -> str:
    for prefix in ("&&&START&&&", ")]}'\n"):
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


def _find_user_id(auth: dict):
    for key in ("userId", "user_id", "uid", "id"):
        val = auth.get(key)
        if val:
            return val
    ti = auth.get("token_info") or {}
    for key in ("userId", "user_id", "uid"):
        val = ti.get(key)
        if val:
            return val
    return None
