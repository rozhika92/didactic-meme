import requests
import base64
import struct


def decode_java_string(b64_value: str) -> str:
    """
    Decode a Java ObjectOutputStream serialized string from base64.
    Format: \xac\xed\x00\x05\x74 + 2-byte big-endian length + UTF-8 string bytes.
    Some values use \x73\x72 (object) instead of \x74 (string) — handle gracefully.
    """
    raw = base64.b64decode(b64_value)
    # Look for string marker \x74
    idx = raw.find(b'\x74')
    if idx == -1:
        # Fallback: try to extract any readable text
        return raw.decode('utf-8', errors='ignore').strip('\x00')
    idx += 1  # skip the \x74 marker
    if idx + 2 > len(raw):
        return ""
    str_len = struct.unpack('>H', raw[idx:idx + 2])[0]
    idx += 2
    return raw[idx:idx + str_len].decode('utf-8', errors='replace')


def fetch_account(serial_number: str) -> dict:
    """
    Fetch Viber account data from the management backend.

    Endpoint: POST http://wa.mysocialfans.net/directLoginAccountLogin?serialNumber=<sn>
    """
    url = "http://wa.mysocialfans.net/directLoginAccountLogin"
    headers = {
        "Content-Type": "application/json",
        "os_version": "14",
        "sdk_int": "34",
        "brand": "samsung",
        "manufacturer": "samsung",
        "model": "SM-A525M",
        "product": "a52qub",
        "deviceId": "viber_checker_tool",
    }

    try:
        resp = requests.post(
            url, params={"serialNumber": serial_number}, headers=headers, timeout=15
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        return {"success": False, "error": str(e)}

    if not data.get("success"):
        return data

    result = data.get("result", {})
    restore = result.get("restoreFile", {})

    # Decode key fields from restoreFile
    key_fields = {
        "reg_member_id": "/data/data/com.viber.voip/files/preferences/reg_member_id",
        "device_key": "/data/data/com.viber.voip/files/preferences/device_key",
        "viber_udid": "/data/data/com.viber.voip/files/preferences/viber_udid",
        "phone_num": "/data/data/com.viber.voip/files/preferences/reg_viber_phone_num",
        "country_code": "/data/data/com.viber.voip/files/preferences/reg_viber_country_code",
    }

    decoded = {}
    for name, path in key_fields.items():
        if path in restore:
            decoded[name] = decode_java_string(restore[path])

    return {
        "success": True,
        "phone": result.get("phone", ""),
        "id": result.get("id", ""),
        "package": result.get("packageName", ""),
        "decoded_fields": decoded,
        "restore_file_count": len(restore),
    }
