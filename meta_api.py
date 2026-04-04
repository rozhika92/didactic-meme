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
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# App identity extracted from APK decompilation
API_KEY = "121876164619130"
API_SECRET = "1ab2c5c902faedd339c14b2d58e929dc"
APP_ID = "121876164619130"
APP_VERSION = "546.0.0.56.106"
BUILD_NUM = "917854681"

# Full User-Agent matching C3JY.java UA builder from decompiled APK
USER_AGENT = (
    "Dalvik/2.1.0 (Linux; U; Android 13; Pixel 6 Build/TQ3A.230901.001) "
    "[FBAN/PagesManager;"
    "FBAV/546.0.0.56.106;"
    "FBPN/com.facebook.pages.app;"
    "FBLC/en_US;"
    "FBBV/917854681;"
    "FBCR/;"
    "FBMF/Google;"
    "FBBD/google;"
    "FBDV/Pixel 6;"
    "FBSV/13.0;"
    "FBCA/arm64-v8a:armeabi-v7a;"
    "FBDM/{density=2.75,width=1080,height=2400};"
    "FB_FW/1;]"
)

# Headers matching Tigon HTTP client (C32H.java, C34E.java, AbstractC62042STp.java)
HEADERS = {
    "User-Agent": USER_AGENT,
    "Content-Type": "application/x-www-form-urlencoded",
    "X-FB-HTTP-Engine": "Liger",
    "X-FB-Connection-Quality": "EXCELLENT",
    "X-FB-Friendly-Name": "authenticate",
    "Accept-Encoding": "gzip, deflate",
    "Accept-Language": "en_US",
}

AUTH_URL = "https://b-api.facebook.com/method/auth.login"
GRAPH_URL = "https://b-graph.facebook.com"


class MetaBusinessAPI:
    """Client mimicking Meta Business Suite Android app API calls."""

    def __init__(self, proxy: str = None):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        # Retry on proxy/connection errors
        retry = Retry(total=3, backoff_factor=1, status_forcelist=[502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        # Default device fingerprint
        self.device_id = str(uuid.uuid4())
        self.adid = str(uuid.uuid4())
        self.family_device_id = str(uuid.uuid4())
        if proxy:
            self.session.proxies = {"http": proxy, "https": proxy}

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

    @staticmethod
    def _compute_sig(params: dict) -> str:
        """MD5 signature: sort params, concat key=value, append secret, hash."""
        sig_str = "".join(f"{k}={v}" for k, v in sorted(params.items())) + API_SECRET
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
        """Build login params matching decompiled C0ML.java AuthenticateMethod."""
        params = {
            # Core auth
            "api_key": API_KEY,
            "credentials_type": "password",
            "email": uid,
            "format": "json",
            "method": "auth.login",
            "password": password,
            "v": "1.0",
            "locale": "en_US",
            "client_country_code": "US",
            # Session
            "generate_machine_id": "1",
            "generate_session_cookies": "1",
            "generate_analytics_claim": "1",
            # Device fingerprint
            "device_id": self.device_id,
            "adid": self.adid,
            "advertiser_id": self.adid,
            "family_device_id": self.family_device_id,
            "secure_family_device_id": self.device_id,
            # App identification
            "fb_api_req_friendly_name": "authenticate",
            "fb_api_caller_class": "AuthOperations",
            "meta_inf_fbmeta": "",
            "cpl": "true",
            "try_num": "1",
            "currently_logged_in_userid": "0",
            "enroll_misauth": "false",
            "return_ssl_resources": "0",
            # Device info
            "device_name": "Pixel 6",
            "device_model_name": "Pixel 6",
            "sim_serials": "[]",
            "encrypted_msisdn": "",
            "jazoest": self._compute_jazoest(uid),
        }
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
            r = self.session.post(AUTH_URL, data=params, timeout=20)
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
                r2 = self.session.post(AUTH_URL, data=params2, timeout=20)
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
        r = self.session.get(f"{GRAPH_URL}/me", params={"fields": "id,name", "access_token": access_token}, timeout=15)
        data = r.json()
        if "error" in data:
            sub = data["error"].get("error_subcode", "")
            if sub == 490:
                return {"error": True, "status": "checkpoint", "msg": data["error"]["message"]}
            return {"error": True, "status": "api_error", "msg": data["error"]["message"]}
        return {"error": False, "id": data.get("id"), "name": data.get("name")}

    def get_pages(self, access_token: str) -> dict:
        """GET /me/accounts"""
        r = self.session.get(
            f"{GRAPH_URL}/me/accounts",
            params={"fields": "id,name,access_token,category", "limit": "100", "access_token": access_token},
            timeout=15,
        )
        data = r.json()
        if "error" in data:
            return {"error": True, "msg": data["error"]["message"], "pages": []}
        return {"error": False, "pages": data.get("data", []), "paging": data.get("paging")}

    def create_page(self, access_token: str, user_id: str, page_name: str, category_id: str = "2200") -> dict:
        """POST /{user_id}/accounts — create a Facebook Page."""
        r = self.session.post(
            f"{GRAPH_URL}/{user_id}/accounts",
            data={
                "name": page_name,
                "category_list": f'["{category_id}"]',
                "access_token": access_token,
            },
            timeout=15,
        )
        data = r.json()
        if "error" in data:
            return {"error": True, "msg": data["error"]["message"]}
        return {"error": False, "data": data}

    def search_page_categories(self, access_token: str, query: str) -> list:
        """Search for valid page category IDs. Returns list of {id, name} dicts."""
        r = self.session.get(
            f"{GRAPH_URL}/pages/search",
            params={"type": "placetopic", "q": query, "access_token": access_token},
            timeout=15,
        )
        data = r.json()
        if "error" in data:
            return []
        return data.get("data", [])

    def search_categories(self, access_token: str, query: str) -> dict:
        """Search page categories."""
        r = self.session.get(
            f"{GRAPH_URL}/pages/search",
            params={"type": "placetopic", "q": query, "access_token": access_token},
            timeout=15,
        )
        data = r.json()
        if "error" in data:
            return {"error": True, "msg": data["error"]["message"], "categories": []}
        return {"error": False, "categories": data.get("data", [])}
