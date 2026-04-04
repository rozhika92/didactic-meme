"""
Meta Business Suite API Client
Reverse-engineered from com.facebook.pages.app v546.0.0.56.106
University research project — educational use only
"""

import hashlib
import hmac
import struct
import time
import base64
import json
import uuid
import requests


# App identity extracted from APK decompilation
API_KEY = "882a8490361da98702bf97a021ddc14d"
API_SECRET = "62f8ce9f74b12f84c123cc23437a4a32"
APP_ID = "121876164619130"
APP_VERSION = "546.0.0.56.106"
BUILD_NUM = "917854681"

HEADERS = {
    "User-Agent": (
        "[FBAN/PagesManager;"
        f"FBAV/{APP_VERSION};"
        f"FBBV/{BUILD_NUM};"
        "FBPN/com.facebook.pages.app;"
        "FBLC/en_US;"
        "FBCR/;"
        "FBMF/Google;"
        "FBBD/google;"
        "FBDV/Pixel 6;"
        "FBSV/13.0;"
        "FBCA/arm64-v8a:;"
        "FB_FW/1;]"
    ),
    "Content-Type": "application/x-www-form-urlencoded",
    "X-FB-HTTP-Engine": "Liger",
    "X-FB-Connection-Type": "WIFI",
    "Accept-Language": "en_US",
}

AUTH_URL = "https://b-api.facebook.com/method/auth.login"
GRAPH_URL = "https://graph.facebook.com/v19.0"


class MetaBusinessAPI:
    """Client mimicking Meta Business Suite Android app API calls."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.device_id = str(uuid.uuid4())
        self.adid = str(uuid.uuid4())
        self.family_device_id = str(uuid.uuid4())

    @staticmethod
    def _compute_sig(params: dict) -> str:
        """
        MD5 signature used by Facebook mobile API.
        Sort params alphabetically, concat key=value pairs, append API_SECRET, MD5 hash.
        """
        sig_str = "".join(f"{k}={v}" for k, v in sorted(params.items())) + API_SECRET
        return hashlib.md5(sig_str.encode()).hexdigest()

    @staticmethod
    def _generate_totp(secret_base32: str, digits: int = 6, interval: int = 30) -> str:
        """Generate a TOTP code from a Base32 secret (RFC 6238)."""
        secret = secret_base32.upper().replace(" ", "")
        # Pad to multiple of 8
        padding = 8 - len(secret) % 8
        if padding != 8:
            secret += "=" * padding
        key = base64.b32decode(secret)
        counter = struct.pack(">Q", int(time.time()) // interval)
        mac = hmac.new(key, counter, hashlib.sha1).digest()
        offset = mac[-1] & 0x0F
        code = struct.unpack(">I", mac[offset:offset + 4])[0] & 0x7FFFFFFF
        return str(code % (10 ** digits)).zfill(digits)

    def _build_login_params(self, uid: str, password: str) -> dict:
        """Build the base login parameters matching the decompiled app."""
        params = {
            "api_key": API_KEY,
            "credentials_type": "password",
            "email": uid,
            "format": "json",
            "generate_machine_id": "1",
            "generate_session_cookies": "1",
            "locale": "en_US",
            "method": "auth.login",
            "password": password,
            "return_ssl_resources": "0",
            "v": "1.0",
            "generate_analytics_claim": "1",
            "cpl": "true",
            "currently_logged_in_userid": "0",
            "device_id": self.device_id,
            "adid": self.adid,
            "family_device_id": self.family_device_id,
            "secure_family_device_id": "",
            "meta_inf_fbmeta": "",
            "fb_api_req_friendly_name": "authenticate",
            "fb_api_caller_class": "AuthOperations",
        }
        return params

    def login(self, uid: str, password: str, totp_secret: str) -> dict:
        """
        Full login flow with automatic 2FA handling.
        
        Returns dict with keys:
          - status: "ok" | "checkpoint" | "disabled" | "wrong_pass" | "error"
          - access_token: str (if status == "ok")
          - uid: int (if status == "ok")
          - session_cookies: list (if status == "ok")
          - error_msg: str (if status != "ok")
        """
        # Step 1: initial password login
        params = self._build_login_params(uid, password)
        params["sig"] = self._compute_sig(params)

        try:
            r = self.session.post(AUTH_URL, data=params, timeout=15)
            result = r.json()
        except Exception as e:
            return {"status": "error", "error_msg": str(e)}

        # Direct success (no 2FA)
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

        # Disabled / banned
        if error_code == 1:
            return {"status": "disabled", "error_msg": "Account disabled or banned"}

        # Wrong credentials
        if error_code == 401:
            return {"status": "wrong_pass", "error_msg": "Invalid credentials"}

        # 2FA required
        if error_code == 406:
            try:
                error_data = json.loads(result.get("error_data", "{}"))
            except json.JSONDecodeError:
                return {"status": "error", "error_msg": "Failed to parse 2FA error data"}

            if "login_first_factor" not in error_data:
                return {"status": "checkpoint", "error_msg": "Account requires checkpoint verification"}

            # Step 2: submit TOTP code
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
                r2 = self.session.post(AUTH_URL, data=params2, timeout=15)
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
            else:
                sub = result2.get("error_code", "?")
                msg = result2.get("error_msg", "Unknown 2FA error")
                if sub == 490 or "checkpoint" in msg.lower():
                    return {"status": "checkpoint", "error_msg": msg}
                return {"status": "error", "error_msg": f"2FA failed ({sub}): {msg}"}

        # Generic / unknown
        return {"status": "error", "error_msg": f"Error {error_code}: {result.get('error_msg', 'Unknown')}"}

    # ---- Graph API helpers ----

    def get_user_info(self, access_token: str) -> dict:
        """GET /me — returns id, name."""
        r = self.session.get(
            f"{GRAPH_URL}/me",
            params={"fields": "id,name", "access_token": access_token},
            timeout=10,
        )
        data = r.json()
        if "error" in data:
            sub = data["error"].get("error_subcode", "")
            if sub == 490:
                return {"error": True, "status": "checkpoint", "msg": data["error"]["message"]}
            return {"error": True, "status": "api_error", "msg": data["error"]["message"]}
        return {"error": False, "id": data.get("id"), "name": data.get("name")}

    def get_pages(self, access_token: str) -> dict:
        """GET /me/accounts — list pages + their access tokens."""
        r = self.session.get(
            f"{GRAPH_URL}/me/accounts",
            params={
                "fields": "id,name,access_token,category",
                "limit": "100",
                "access_token": access_token,
            },
            timeout=10,
        )
        data = r.json()
        if "error" in data:
            return {"error": True, "msg": data["error"]["message"], "pages": []}
        return {"error": False, "pages": data.get("data", []), "paging": data.get("paging")}

    def create_page(self, access_token: str, user_id: str, page_name: str, category_id: str = "2256") -> dict:
        """POST /{user_id}/accounts — create a new Facebook Page."""
        r = self.session.post(
            f"{GRAPH_URL}/{user_id}/accounts",
            data={
                "name": page_name,
                "category_enum": category_id,
                "access_token": access_token,
            },
            timeout=15,
        )
        data = r.json()
        if "error" in data:
            return {"error": True, "msg": data["error"]["message"]}
        return {"error": False, "data": data}

    def search_categories(self, access_token: str, query: str) -> dict:
        """Search page categories."""
        r = self.session.get(
            f"{GRAPH_URL}/pages/search",
            params={"type": "placetopic", "q": query, "access_token": access_token},
            timeout=10,
        )
        data = r.json()
        if "error" in data:
            return {"error": True, "msg": data["error"]["message"], "categories": []}
        return {"error": False, "categories": data.get("data", [])}
