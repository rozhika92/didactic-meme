"""
Meta Business Suite API Client
Reverse-engineered from com.facebook.pages.app and com.facebook.katana
University research project — educational use only
"""

import hashlib
import hmac
import struct
import time
import base64
import json
import uuid
import random
from curl_cffi import requests as curl_requests


# App identities extracted from APK decompilation
IDENTITIES = {
    "katana": {
        "api_key": "350685531728",
        "api_secret": "62f8ce9f74b12f84c123cc23437a4a32",
        "app_version": "555.0.0.49.59",
        "build_num": "470015326",
        "fban": "FB4A",
        "package": "com.facebook.katana",
        "ua_suffix_tags": "FBLR/0;FBBK/1;",
    },
    "pages_manager": {
        "api_key": "121876164619130",
        "api_secret": "1ab2c5c902faedd339c14b2d58e929dc",
        "app_version": "546.0.0.56.106",
        "build_num": "917854681",
        "fban": "PagesManager",
        "package": "com.facebook.pages.app",
        "ua_suffix_tags": "FB_FW/1;",
    },
}

DEFAULT_IDENTITY = "katana"

AUTH_URL = "https://b-api.facebook.com/method/auth.login"
GRAPH_URL = "https://b-graph.facebook.com"


def build_user_agent(
    identity_name: str = DEFAULT_IDENTITY,
    device: str = "Pixel 6",
    android_version: str = "13.0",
    build_tag: str = "TQ3A.230901.001",
) -> str:
    """Build User-Agent string matching the APK's UA builder."""
    ident = IDENTITIES[identity_name]
    if identity_name == "katana":
        # Katana tag order: FBAN, FBAV, FBBV, FBDM, FBLC, FBCR, FBMF, FBBD, FBPN, FBDV, FBSV, FBLR, FBBK, FBCA
        tags = (
            f"FBAN/{ident['fban']};"
            f"FBAV/{ident['app_version']};"
            f"FBBV/{ident['build_num']};"
            f"FBDM/{{density=2.75,width=1080,height=2400}};"
            f"FBLC/en_US;"
            f"FBCR/;"
            f"FBMF/Google;"
            f"FBBD/google;"
            f"FBPN/{ident['package']};"
            f"FBDV/{device};"
            f"FBSV/{android_version};"
            f"{ident['ua_suffix_tags']}"
            f"FBCA/arm64-v8a:armeabi-v7a;"
        )
    else:
        # Pages Manager tag order: FBAN, FBAV, FBPN, FBLC, FBBV, FBCR, FBMF, FBBD, FBDV, FBSV, FBCA, FBDM, FB_FW
        tags = (
            f"FBAN/{ident['fban']};"
            f"FBAV/{ident['app_version']};"
            f"FBPN/{ident['package']};"
            f"FBLC/en_US;"
            f"FBBV/{ident['build_num']};"
            f"FBCR/;"
            f"FBMF/Google;"
            f"FBBD/google;"
            f"FBDV/{device};"
            f"FBSV/{android_version};"
            f"FBCA/arm64-v8a:armeabi-v7a;"
            f"FBDM={{density=2.75,width=1080,height=2400}};"
            f"{ident['ua_suffix_tags']}"
        )
    return (
        f"Dalvik/2.1.0 (Linux; U; Android {android_version}; "
        f"{device} Build/{build_tag}) [{tags}]"
    )


class MetaBusinessAPI:
    """Client mimicking Meta Business Suite / Facebook Android app API calls."""

    def __init__(self, proxy: str = None, identity: str = DEFAULT_IDENTITY):
        self.identity = identity
        self.ident = IDENTITIES[identity]
        self.session = curl_requests.Session(impersonate="chrome131_android")
        # Build identity-specific headers
        ua = build_user_agent(identity)
        self.session.headers.update({
            "User-Agent": ua,
            "Content-Type": "application/x-www-form-urlencoded",
            "X-FB-HTTP-Engine": "Liger",
            "X-FB-Client-IP": "True",
            "X-FB-Server-Cluster": "True",
            "X-FB-Connection-Type": "WIFI",
            "X-FB-Connection-Quality": random.choice(["EXCELLENT", "EXCELLENT", "EXCELLENT", "GOOD"]),
            "X-FB-Connection-Bandwidth": str(random.randint(20000000, 40000000)),
            "X-FB-Device-Group": "7991",
            "X-FB-SIM-HNI": "310260",
            "X-FB-Net-HNI": "310260",
            "X-FB-Request-Analytics-Tags": "unknown",
            "X-FB-Friendly-Name": "authenticate",
            "X-Tigon-Is-Retry": "False",
            "Authorization": "OAuth null",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "en_US",
        })
        # Default device fingerprint
        self.device_id = str(uuid.uuid4())
        self.adid = str(uuid.uuid4())
        self.family_device_id = str(uuid.uuid4())
        if proxy:
            self.session.proxies = {"http": proxy, "https": proxy}

    def _request_with_retry(self, method, url, max_retries=3, **kwargs):
        last_error = None
        for attempt in range(max_retries):
            try:
                if method == "GET":
                    return self.session.get(url, **kwargs)
                else:
                    return self.session.post(url, **kwargs)
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    time.sleep(1 * (attempt + 1))
        raise last_error

    def new_device_fingerprint(self, seed: str = None):
        """Generate device IDs. If seed is given, IDs are deterministic (stable per-account)."""
        if seed:
            def _seeded(s):
                h = hashlib.md5(s.encode()).hexdigest()
                return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"
            self.device_id = _seeded(seed + "_dev")
            self.adid = _seeded(seed + "_adid")
            self.family_device_id = _seeded(seed + "_fam")
        else:
            self.device_id = str(uuid.uuid4())
            self.adid = str(uuid.uuid4())
            self.family_device_id = str(uuid.uuid4())

    def _compute_sig(self, params: dict) -> str:
        """MD5 signature: sort params, concat key=value, append secret, hash."""
        sig_str = "".join(f"{k}={v}" for k, v in sorted(params.items())) + self.ident["api_secret"]
        return hashlib.md5(sig_str.encode()).hexdigest()

    @staticmethod
    def _generate_totp(secret_base32: str, digits: int = 6, interval: int = 30) -> str:
        """Generate TOTP code from Base32 secret (RFC 6238)."""
        secret = secret_base32.upper().replace(" ", "")
        padding = 8 - len(secret) % 8
        if padding != 8:
            secret += "=" * padding
        key = base64.b32decode(secret)
        counter = struct.pack(">Q", int(time.time()) // interval)
        mac = hmac.new(key, counter, hashlib.sha1).digest()
        offset = mac[-1] & 0x0F
        code = struct.unpack(">I", mac[offset:offset + 4])[0] & 0x7FFFFFFF
        return str(code % (10 ** digits)).zfill(digits)

    @staticmethod
    def _compute_jazoest(uid: str) -> str:
        """Compute jazoest token (sum of byte values, prefixed with '2')."""
        return f"2{sum(ord(c) for c in uid)}"

    def _build_login_params(self, uid: str, password: str) -> dict:
        """Build login params matching decompiled AuthenticateMethod."""
        params = {
            "adid": self.adid,
            "email": uid,
            "password": password,
            "credentials_type": "device_based_login_password",
            "source": "login",
            "error_detail_type": "button_with_disabled",
            "format": "json",
            "method": "auth.login",
            "v": "1.0",
            "locale": "en_US",
            "client_country_code": "US",
            "access_token": f"{self.ident['api_key']}|{self.ident['api_secret']}",
            "api_key": self.ident["api_key"],
            "generate_machine_id": "1",
            "generate_session_cookies": "1",
            "generate_analytics_claim": "1",
            "device_id": self.device_id,
            "advertiser_id": self.adid,
            "family_device_id": self.family_device_id,
            "secure_family_device_id": "",
            "fb_api_req_friendly_name": "authenticate",
            "meta_inf_fbmeta": "NO_FILE",
            "community_id": "",
            "cpl": "true",
            "try_num": "1",
            "currently_logged_in_userid": "0",
            "enroll_misauth": "false",
            "return_ssl_resources": "0",
            "device_name": "Pixel 6",
            "device_model_name": "Pixel 6",
            "sim_serials": "[]",
            "encrypted_msisdn": "",
            "jazoest": self._compute_jazoest(uid),
        }
        if self.identity == "katana":
            params["fb_api_caller_class"] = "com.facebook.account.login.protocol.Fb4aAuthHandler"
        else:
            params["fb_api_caller_class"] = "AuthOperations$PasswordAuthOperation"
        return params

    def login(self, uid: str, password: str, totp_secret: str) -> dict:
        """
        Full login flow with automatic 2FA handling.

        Returns dict with keys:
          status: "ok" | "checkpoint" | "disabled" | "wrong_pass" | "error"
          access_token, uid, session_cookies, machine_id, secret (when ok)
          error_msg (when not ok)
        """
        params = self._build_login_params(uid, password)
        params["sig"] = self._compute_sig(params)

        try:
            r = self._request_with_retry("POST", AUTH_URL, data=params, timeout=20)
            result = r.json()
        except Exception as e:
            return {"status": "error", "error_msg": str(e)}

        if "access_token" in result:
            return {
                "status": "ok",
                "access_token": result["access_token"],
                "uid": result.get("uid"),
                "session_cookies": result.get("session_cookies", []),
                "machine_id": result.get("machine_id"),
                "secret": result.get("secret"),
            }

        error_code = result.get("error_code")
        if error_code == 1:
            return {"status": "disabled", "error_msg": "Account disabled or banned"}
        if error_code == 401:
            return {"status": "wrong_pass", "error_msg": "Invalid credentials"}
        if error_code == 368:
            return {"status": "rate_limit", "error_msg": result.get("error_msg", "Too many requests")}
        if error_code == 405:
            return {"status": "checkpoint", "error_msg": result.get("error_msg", "Checkpoint verification required")}

        if error_code == 406:
            try:
                error_data = json.loads(result.get("error_data", "{}"))
            except json.JSONDecodeError:
                return {"status": "error", "error_msg": "Failed to parse 2FA error data"}
            if "login_first_factor" not in error_data:
                return {"status": "checkpoint", "error_msg": "Account requires checkpoint verification"}

            totp_code = self._generate_totp(totp_secret)
            params2 = self._build_login_params(uid, password)
            params2.update({
                "credentials_type": "two_factor",
                "twofactor_code": totp_code,
                "userid": str(error_data["uid"]),
                "first_factor": error_data["login_first_factor"],
                "machine_id": error_data["machine_id"],
            })
            params2["sig"] = self._compute_sig(params2)

            try:
                r2 = self._request_with_retry("POST", AUTH_URL, data=params2, timeout=20)
                result2 = r2.json()
            except Exception as e:
                return {"status": "error", "error_msg": f"2FA request failed: {e}"}

            if "access_token" in result2:
                return {
                    "status": "ok",
                    "access_token": result2["access_token"],
                    "uid": result2.get("uid"),
                    "session_cookies": result2.get("session_cookies", []),
                    "machine_id": result2.get("machine_id"),
                    "secret": result2.get("secret"),
                }
            sub = result2.get("error_code", "?")
            msg = result2.get("error_msg", "Unknown 2FA error")
            if sub == 490 or "checkpoint" in msg.lower():
                return {"status": "checkpoint", "error_msg": msg}
            return {"status": "error", "error_msg": f"2FA failed ({sub}): {msg}"}

        return {"status": "error", "error_msg": f"Error {error_code}: {result.get('error_msg', 'Unknown')}"}

    # ---- Graph API helpers ----

    def get_user_info(self, access_token: str) -> dict:
        """GET /me"""
        self.session.headers["Authorization"] = f"OAuth {access_token}"
        self.session.headers["X-FB-Friendly-Name"] = "graphservice"
        try:
            try:
                r = self._request_with_retry("GET", f"{GRAPH_URL}/me", params={"fields": "id,name", "access_token": access_token}, timeout=15)
            except Exception as e:
                return {"error": True, "status": "network_error", "msg": str(e)}

            if r.headers.get("x-fb-integrity-required") == "checkpoint":
                return {"error": True, "status": "checkpoint", "msg": "Account requires checkpoint verification"}

            if not r.content:
                return {"error": True, "status": "empty_response", "msg": f"Empty response (HTTP {r.status_code})"}

            try:
                data = r.json()
            except (ValueError, json.JSONDecodeError):
                return {"error": True, "status": "parse_error", "msg": f"Non-JSON response (HTTP {r.status_code})"}

            if "error" in data:
                sub = data["error"].get("error_subcode", "")
                if sub == 490:
                    return {"error": True, "status": "checkpoint", "msg": data["error"]["message"]}
                return {"error": True, "status": "api_error", "msg": data["error"]["message"]}
            return {"error": False, "id": data.get("id"), "name": data.get("name")}
        finally:
            self.session.headers["Authorization"] = "OAuth null"
            self.session.headers["X-FB-Friendly-Name"] = "authenticate"

    def get_pages(self, access_token: str) -> dict:
        """GET /me/accounts"""
        self.session.headers["Authorization"] = f"OAuth {access_token}"
        self.session.headers["X-FB-Friendly-Name"] = "graphservice"
        try:
            try:
                r = self._request_with_retry(
                    "GET",
                    f"{GRAPH_URL}/me/accounts",
                    params={"fields": "id,name,access_token,category", "limit": "100", "access_token": access_token},
                    timeout=15,
                )
            except Exception as e:
                return {"error": True, "status": "network_error", "msg": str(e), "pages": []}

            if r.headers.get("x-fb-integrity-required") == "checkpoint":
                return {"error": True, "status": "checkpoint", "msg": "Account requires checkpoint verification", "pages": []}

            if not r.content:
                return {"error": True, "status": "empty_response", "msg": f"Empty response (HTTP {r.status_code})", "pages": []}

            try:
                data = r.json()
            except (ValueError, json.JSONDecodeError):
                return {"error": True, "status": "parse_error", "msg": f"Non-JSON response (HTTP {r.status_code})", "pages": []}

            if "error" in data:
                sub = data["error"].get("error_subcode", "")
                if sub == 490:
                    return {"error": True, "status": "checkpoint", "msg": data["error"]["message"], "pages": []}
                return {"error": True, "status": "api_error", "msg": data["error"]["message"], "pages": []}
            return {"error": False, "pages": data.get("data", []), "paging": data.get("paging")}
        finally:
            self.session.headers["Authorization"] = "OAuth null"
            self.session.headers["X-FB-Friendly-Name"] = "authenticate"

    def create_page(self, access_token: str, user_id: str, page_name: str, category_id: str = "2200") -> dict:
        """POST /{user_id}/accounts — create a Facebook Page."""
        self.session.headers["Authorization"] = f"OAuth {access_token}"
        self.session.headers["X-FB-Friendly-Name"] = "graphservice"
        try:
            try:
                r = self._request_with_retry(
                    "POST",
                    f"{GRAPH_URL}/{user_id}/accounts",
                    data={
                        "name": page_name,
                        "category_list": f'["{category_id}"]',
                        "access_token": access_token,
                    },
                    timeout=15,
                )
            except Exception as e:
                return {"error": True, "status": "network_error", "msg": str(e)}

            if r.headers.get("x-fb-integrity-required") == "checkpoint":
                return {"error": True, "status": "checkpoint", "msg": "Account requires checkpoint verification"}

            if not r.content:
                return {"error": True, "status": "empty_response", "msg": f"Empty response (HTTP {r.status_code})"}

            try:
                data = r.json()
            except (ValueError, json.JSONDecodeError):
                return {"error": True, "status": "parse_error", "msg": f"Non-JSON response (HTTP {r.status_code})"}

            if "error" in data:
                sub = data["error"].get("error_subcode", "")
                if sub == 490:
                    return {"error": True, "status": "checkpoint", "msg": data["error"]["message"]}
                return {"error": True, "status": "api_error", "msg": data["error"]["message"]}
            return {"error": False, "data": data}
        finally:
            self.session.headers["Authorization"] = "OAuth null"
            self.session.headers["X-FB-Friendly-Name"] = "authenticate"

    def search_categories(self, access_token: str, query: str) -> dict:
        """Search page categories."""
        self.session.headers["Authorization"] = f"OAuth {access_token}"
        self.session.headers["X-FB-Friendly-Name"] = "graphservice"
        try:
            try:
                r = self._request_with_retry(
                    "GET",
                    f"{GRAPH_URL}/pages/search",
                    params={"type": "placetopic", "q": query, "access_token": access_token},
                    timeout=15,
                )
            except Exception as e:
                return {"error": True, "status": "network_error", "msg": str(e), "categories": []}

            if r.headers.get("x-fb-integrity-required") == "checkpoint":
                return {"error": True, "status": "checkpoint", "msg": "Account requires checkpoint verification", "categories": []}

            if not r.content:
                return {"error": True, "status": "empty_response", "msg": f"Empty response (HTTP {r.status_code})", "categories": []}

            try:
                data = r.json()
            except (ValueError, json.JSONDecodeError):
                return {"error": True, "status": "parse_error", "msg": f"Non-JSON response (HTTP {r.status_code})", "categories": []}

            if "error" in data:
                sub = data["error"].get("error_subcode", "")
                if sub == 490:
                    return {"error": True, "status": "checkpoint", "msg": data["error"]["message"], "categories": []}
                return {"error": True, "status": "api_error", "msg": data["error"]["message"], "categories": []}
            return {"error": False, "categories": data.get("data", [])}
        finally:
            self.session.headers["Authorization"] = "OAuth null"
            self.session.headers["X-FB-Friendly-Name"] = "authenticate"
