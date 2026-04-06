"""
Meta Business Suite API Client
Reverse-engineered from com.facebook.pages.app and com.facebook.katana
University research project — educational use only
"""

import base64
import hashlib
import hmac
import json
import logging
import random
import struct
import time
import uuid
from curl_cffi import requests as curl_requests


logger = logging.getLogger(__name__)


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
        "app_version": "545.0.0.58.109",
        "build_num": "909563321",
        "fban": "PAAA",
        "package": "com.facebook.pages.app",
        "ua_suffix_tags": "FB_FW/2;FBSN/Android;FBDI/null;",
    },
}

DEFAULT_IDENTITY = "katana"

AUTH_URL = "https://b-api.facebook.com/method/auth.login"
GRAPH_URL = "https://b-graph.facebook.com"
GRAPH_WWW_URL = "https://graph-www.facebook.com"

# Verified doc_ids extracted from MBS APK v547 via Frida JNI hooking on Android emulator.
# GraphQLServiceFactory.createClientDocIdForQueryNameHash(3178286506L)
# returned "317828650610284500029763397346".
#
# Format: str(query_name_hash) + str(field1_uint64) from fbandroid_graph_metadata.bin.
# The hash 3178286506 alone is NOT the doc_id — it is resolved by native C++ code
# inside libgraphservice-jni-factory (packed in libstartup.so / libscrollmerged.so).
RESOLVED_DOC_IDS = {
    "BizAppCreatePageMutation": "317828650610284500029763397346",
    "InstagramCollabAcceptMutation": "14626597345362839530295772214",
    "InstagramCollabDeclineMutation": "32723968003686238167148904534",
    "BIZMessengerPageCreateOrUpdateOrderMutation": "44080350911158068324316851480",
}


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
        pages_android_version = android_version if android_version != "13.0" else "13"
        tags = (
            f"FBAN/{ident['fban']};"
            f"FBAV/{ident['app_version']};"
            f"FBDM/{{density=2.75,width=1080,height=2400}};"
            f"FBLC/en_US;"
            f"FBBV/{ident['build_num']};"
            f"{ident['ua_suffix_tags']}"
            f"FBCR/;"
            f"FBMF/Google;"
            f"FBBD/google;"
            f"FBDV/{device};"
            f"FBSV/{pages_android_version};"
            f"FBCA/arm64-v8a:null;"
        )
    return (
        f"Dalvik/2.1.0 (Linux; U; Android {pages_android_version if identity_name == 'pages_manager' else android_version}; "
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
        if identity == "pages_manager":
            self.session.headers.update({
                "x-graphql-client-library": "graphservice",
                "x-graphql-request-purpose": "fetch",
                "X-FB-HTTP-Engine": "Tigon/Liger",
                "x-fb-request-analytics-tags": json.dumps({
                    "network_tags": {
                        "product": self.ident["api_key"],
                        "request_category": "graphql",
                        "purpose": "fetch",
                        "retry_attempt": "0",
                    },
                    "application_tags": "graphservice",
                }),
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

    @staticmethod
    def _checkpoint_error(message: str) -> dict:
        return {"error": True, "status": "checkpoint", "msg": message}

    @staticmethod
    def _api_error(message: str, status: str = "api_error") -> dict:
        return {"error": True, "status": status, "msg": message}

    def _parse_json_response(self, response, empty_payload: dict):
        if response.headers.get("x-fb-integrity-required") == "checkpoint":
            return self._checkpoint_error("Account requires checkpoint verification")

        if not response.content:
            return {**empty_payload, "error": True, "status": "empty_response", "msg": f"Empty response (HTTP {response.status_code})"}

        try:
            return response.json()
        except (ValueError, json.JSONDecodeError):
            return {**empty_payload, "error": True, "status": "parse_error", "msg": f"Non-JSON response (HTTP {response.status_code})"}

    @staticmethod
    def _extract_graphql_message(payload: dict) -> tuple[str, str]:
        errors = payload.get("errors") or []
        if errors:
            first = errors[0] or {}
            message = first.get("message") or payload.get("message") or "Unknown GraphQL error"
            code = str(first.get("code") or first.get("error_subcode") or first.get("extensions", {}).get("code") or "")
            return message, code
        return payload.get("message", "Unknown GraphQL error"), ""

    def _graphql_success_result(self, payload: dict) -> dict | None:
        page = ((payload.get("data") or {}).get("biz_app_create_page") or {}).get("page")
        if not page:
            page = ((payload.get("data") or {}).get("page_create") or {}).get("page")
        if not page:
            return None
        return {
            "error": False,
            "data": {
                "id": page.get("id"),
                "name": page.get("name"),
            },
            "method": "graphql",
        }

    def _normalize_graph_payload_error(self, payload: dict) -> dict | None:
        error_block = payload.get("error")
        if not error_block:
            return None
        if payload.get("status") and payload.get("msg"):
            return payload
        if isinstance(error_block, dict):
            message = error_block.get("message", "Unknown API error")
            subcode = str(error_block.get("error_subcode", ""))
            if subcode == "490" or "checkpoint" in message.lower():
                return self._checkpoint_error(message)
            return self._api_error(message)
        return self._api_error(str(error_block))

    @staticmethod
    def _extract_category_results(payload: dict) -> list[dict]:
        data = payload.get("data") or {}
        candidates = []
        if isinstance(data.get("page_category_search"), list):
            candidates = data["page_category_search"]
        elif isinstance(data.get("page_category_search"), dict):
            candidates = data["page_category_search"].get("data", [])

        categories = []
        for item in candidates or []:
            category_id = item.get("id")
            name = item.get("name")
            if category_id and name:
                categories.append({"id": str(category_id), "name": name})
        return categories

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

    def create_page_graphql(self, access_token: str, page_name: str, category_ids: list[str]) -> dict:
        """Create a page via Facebook's internal GraphQL API (used by MBS app).

        Uses the verified doc_id extracted from the MBS APK v547 native library.
        Request format matches VUH.java (RelayPrefetcherMethod) serializer exactly:
        doc_id, variables, fb_api_req_friendly_name, server_timestamps, format, access_token.
        """
        self.session.headers["Authorization"] = f"OAuth {access_token}"
        self.session.headers["X-FB-Friendly-Name"] = "BizAppCreatePageMutation"

        # Set mutation-specific headers (the real app sets purpose=mutation for writes)
        original_purpose = self.session.headers.get("x-graphql-request-purpose")
        original_analytics = self.session.headers.get("x-fb-request-analytics-tags")
        if self.identity == "pages_manager":
            self.session.headers["x-graphql-request-purpose"] = "mutation"
            self.session.headers["x-fb-request-analytics-tags"] = json.dumps({
                "network_tags": {
                    "product": self.ident["api_key"],
                    "request_category": "graphql",
                    "purpose": "mutation",
                    "retry_attempt": "0",
                },
                "application_tags": "graphservice",
            })

        # Variables must include client_mutation_id (from AbstractC4627AKg.java)
        mutation_id = str(uuid.uuid4())
        variables = json.dumps({
            "input": {
                "name": page_name,
                "categories": category_ids,
                "client_mutation_id": mutation_id,
            }
        })

        doc_id = RESOLVED_DOC_IDS["BizAppCreatePageMutation"]

        attempts = [
            # Primary: exact match of VUH.java RelayPrefetcherMethod serializer
            {
                "name": "relay_doc_id",
                "data": {
                    "doc_id": doc_id,
                    "variables": variables,
                    "fb_api_req_friendly_name": "BizAppCreatePageMutation",
                    "server_timestamps": "true",
                    "format": "JSON",
                    "access_token": access_token,
                },
            },
            # Fallback: FQL approach (server recognizes biz_app_create_page, error 1675039)
            {
                "name": "fql_biz_app_create_page",
                "data": {
                    "q": "biz_app_create_page(<input>) { page { id name } }",
                    "variables": variables,
                    "fb_api_req_friendly_name": "BizAppCreatePageMutation",
                    "server_timestamps": "true",
                    "format": "JSON",
                    "access_token": access_token,
                },
            },
        ]

        last_error = self._api_error("GraphQL page creation failed")
        try:
            for endpoint in (f"{GRAPH_URL}/graphql", f"{GRAPH_WWW_URL}/graphql"):
                for attempt in attempts:
                    try:
                        response = self._request_with_retry(
                            "POST",
                            endpoint,
                            data=attempt["data"],
                            timeout=15,
                        )
                    except Exception as e:
                        last_error = {"error": True, "status": "network_error", "msg": str(e)}
                        logger.info("create_page_graphql attempt=%s endpoint=%s failed status=%s", attempt["name"], endpoint, last_error["status"])
                        continue

                    payload = self._parse_json_response(response, {})
                    normalized_error = self._normalize_graph_payload_error(payload)
                    if normalized_error:
                        last_error = normalized_error
                        logger.info("create_page_graphql attempt=%s endpoint=%s failed status=%s msg=%s", attempt["name"], endpoint, last_error.get("status"), last_error.get("msg", ""))
                        if last_error.get("status") == "checkpoint":
                            return last_error
                        continue

                    success = self._graphql_success_result(payload)
                    if success:
                        logger.info("create_page_graphql succeeded via %s on %s", attempt["name"], endpoint)
                        return success

                    message, code = self._extract_graphql_message(payload)
                    if code == "490" or "checkpoint" in message.lower():
                        last_error = self._checkpoint_error(message)
                    elif message:
                        last_error = self._api_error(message)
                    else:
                        last_error = self._api_error("Unknown GraphQL error")
                    logger.info("create_page_graphql attempt=%s endpoint=%s failed status=%s msg=%s", attempt["name"], endpoint, last_error.get("status"), last_error.get("msg", ""))

            return last_error
        finally:
            self.session.headers["Authorization"] = "OAuth null"
            self.session.headers["X-FB-Friendly-Name"] = "authenticate"
            # Restore original graphql headers
            if original_purpose is not None:
                self.session.headers["x-graphql-request-purpose"] = original_purpose
            elif "x-graphql-request-purpose" in self.session.headers:
                del self.session.headers["x-graphql-request-purpose"]
            if original_analytics is not None:
                self.session.headers["x-fb-request-analytics-tags"] = original_analytics
            elif "x-fb-request-analytics-tags" in self.session.headers:
                del self.session.headers["x-fb-request-analytics-tags"]

    def get_valid_categories(self, access_token: str) -> list[dict]:
        """Get valid page categories. Tries multiple approaches."""
        fallback_categories = [
            {"id": "2200", "name": "Local Business"},
            {"id": "1601", "name": "Business/Economy Website"},
            {"id": "2603", "name": "Internet Company"},
            {"id": "1000", "name": "Business"},
        ]
        self.session.headers["Authorization"] = f"OAuth {access_token}"
        self.session.headers["X-FB-Friendly-Name"] = "PageCategorySearchQuery"
        try:
            try:
                rest_response = self._request_with_retry(
                    "GET",
                    f"{GRAPH_URL}/fb_page_categories",
                    params={"access_token": access_token},
                    timeout=15,
                )
                if rest_response.content:
                    rest_data = rest_response.json()
                    if isinstance(rest_data, dict) and "data" in rest_data:
                        cats = [
                            {"id": str(c["id"]), "name": c["name"]}
                            for c in rest_data["data"]
                            if c.get("id") and c.get("name")
                        ]
                        if cats:
                            return cats
            except Exception:
                pass

            try:
                response = self._request_with_retry(
                    "POST",
                    f"{GRAPH_URL}/graphql",
                    data={
                        "q": 'query { page_category_search(query: "Business") { id name } }',
                        "access_token": access_token,
                    },
                    timeout=15,
                )
            except Exception:
                response = None

            if response is not None:
                payload = self._parse_json_response(response, {})
                if not payload.get("error"):
                    categories = self._extract_category_results(payload)
                    if categories:
                        return categories

            for query in ("Business", "Local Business", "Brand", "Company"):
                result = self.search_categories(access_token, query)
                if not result.get("error") and result.get("categories"):
                    return result["categories"]

            return fallback_categories
        finally:
            self.session.headers["Authorization"] = "OAuth null"
            self.session.headers["X-FB-Friendly-Name"] = "authenticate"

    def create_page(self, access_token: str, user_id: str, page_name: str, category_id: str = None) -> dict:
        """Create a Facebook Page via GraphQL first, then REST fallback."""
        if not category_id:
            categories = self.get_valid_categories(access_token)
            if categories:
                category_id = categories[0].get("id", "2200")
            else:
                category_id = "2200"

        graphql_result = self.create_page_graphql(access_token, page_name, [category_id])
        if not graphql_result.get("error"):
            logger.info("create_page used graphql category_id=%s", category_id)
            return graphql_result

        logger.info("create_page falling back to rest category_id=%s reason=%s", category_id, graphql_result.get("msg", "unknown"))
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
            logger.info("create_page used rest category_id=%s", category_id)
            return {"error": False, "data": data, "method": "rest"}
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
