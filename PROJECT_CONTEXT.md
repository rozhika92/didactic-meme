# Project Context — Meta Business Suite API Research

> University final project: reverse-engineering Meta Business Suite Android app API for educational purposes.

## Repository Structure

```
didactic-meme/
├── meta_api.py          # Core API client (MetaBusinessAPI class)
├── run.py               # CLI tool (login/create-page/get-pages/full)
├── accounts.txt         # Account file (uid|password|totp_secret per line)
├── proxies.txt          # Proxy list (host:port:user:pass per line)
├── requirements.txt     # Python deps (requests only)
├── apks/                # Patched APKs for emulator testing
│   ├── facebook_katana_v555_patched.apk
│   ├── meta_suite_v547_patched.apk
│   └── patch_apk.py     # APK patching script
├── PROJECT_CONTEXT.md   # This file
└── README.md
```

---

## App Identities (Extracted from APK Decompilation)

### Facebook Katana (Main Facebook App) — `com.facebook.katana`
- **APK Version:** v555.0.0.49.59 (build 470015326)
- **APP_ID / API_KEY:** `350685531728`
- **API_SECRET:** `62f8ce9f74b12f84c123cc23437a4a32`
- **FBAN:** `FB4A`
- **Package:** `com.facebook.katana`
- **UA-specific tags:** `FBLR/0;FBBK/1;` (no `FB_FW`)
- **Credential source:** Primary DEX, class `X.036` (found via `strings` + `grep`)

### Meta Business Suite (Pages Manager) — `com.facebook.pages.app`
- **APK Version:** v547.0.0.40.109 (build 922914561) / v546.0.0.56.106 (build 917854681)
- **APP_ID / API_KEY:** `121876164619130`
- **API_SECRET:** `1ab2c5c902faedd339c14b2d58e929dc`
- **FBAN:** `PagesManager`
- **Package:** `com.facebook.pages.app`
- **UA-specific tags:** `FB_FW/1;` (no `FBLR`/`FBBK`)
- **Credential source:** Multiple DEX files (8x APP_ID occurrences, 2x API_SECRET)

### Wrong Credentials to Avoid
- `882a8490361da98702bf97a021ddc14d` — this is the **katana** secret for an older API key
- Always verify APP_ID and API_SECRET come from the **same** APK decompilation

---

## API Specification

### Auth Endpoint
```
POST https://b-api.facebook.com/method/auth.login
Content-Type: application/x-www-form-urlencoded
```

### Graph Endpoint
```
https://b-graph.facebook.com
```

### Required Headers (7 total)
```python
{
    "User-Agent": "<dynamic UA string>",
    "Content-Type": "application/x-www-form-urlencoded",
    "X-FB-HTTP-Engine": "Liger",
    "X-FB-Connection-Quality": "EXCELLENT",
    "X-FB-Friendly-Name": "authenticate",
    "Accept-Encoding": "gzip, deflate",
    "Accept-Language": "en_US",
}
```

### User-Agent Format
```
Dalvik/2.1.0 (Linux; U; Android {version}; {device} Build/{build_tag}) [{UA_TAGS}]
```

**Katana UA tags (in order):**
```
FBAN/FB4A;FBAV/555.0.0.49.59;FBBV/470015326;FBDM/{density=2.75,width=1080,height=2400};
FBLC/en_US;FBCR/;FBMF/Google;FBBD/google;FBPN/com.facebook.katana;FBDV/Pixel 6;
FBSV/13.0;FBLR/0;FBBK/1;FBCA/arm64-v8a:armeabi-v7a;
```

**Pages Manager UA tags (in order):**
```
FBAN/PagesManager;FBAV/546.0.0.56.106;FBPN/com.facebook.pages.app;FBLC/en_US;
FBBV/917854681;FBCR/;FBMF/Google;FBBD/google;FBDV/Pixel 6;FBSV/13.0;
FBCA/arm64-v8a:armeabi-v7a;FBDM={density=2.75,width=1080,height=2400};FB_FW/1;
```

### Login Parameters (31 total, including sig)
```python
{
    "api_key": "<APP_ID>",
    "credentials_type": "password",
    "email": "<uid>",
    "format": "json",
    "method": "auth.login",
    "password": "<password>",
    "v": "1.0",
    "locale": "en_US",
    "client_country_code": "US",
    "generate_machine_id": "1",
    "generate_session_cookies": "1",
    "generate_analytics_claim": "1",
    "device_id": "<uuid4>",
    "adid": "<uuid4>",
    "advertiser_id": "<uuid4>",
    "family_device_id": "<uuid4>",
    "secure_family_device_id": "<uuid4>",
    "fb_api_req_friendly_name": "authenticate",
    "fb_api_caller_class": "AuthOperations",
    "meta_inf_fbmeta": "",
    "cpl": "true",
    "try_num": "1",
    "currently_logged_in_userid": "0",
    "enroll_misauth": "false",
    "return_ssl_resources": "0",
    "device_name": "Pixel 6",
    "device_model_name": "Pixel 6",
    "sim_serials": "[]",
    "encrypted_msisdn": "",
    "jazoest": "<computed>",
    "sig": "<md5_hash>",
}
```

### Signature Computation
```python
sig_str = "".join(f"{k}={v}" for k, v in sorted(params.items())) + API_SECRET
sig = hashlib.md5(sig_str.encode()).hexdigest()
```

### Jazoest Computation
```python
jazoest = f"2{sum(ord(c) for c in uid)}"
```

### 2FA Flow
1. Initial login returns `error_code: 406` with `error_data` containing `login_first_factor`, `machine_id`, `uid`
2. Generate TOTP code from account's Base32 secret
3. Re-send login with `credentials_type: "two_factor"`, `twofactor_code`, `userid`, `first_factor`, `machine_id`

### Error Codes
| Code | Meaning | Python Status |
|------|---------|--------------|
| (none) | Success | `"ok"` |
| 1 | Account disabled/banned | `"disabled"` |
| 104 | Incorrect signature | `"error"` |
| 401 | Invalid credentials | `"wrong_pass"` |
| 405 | Checkpoint required | `"checkpoint"` |
| 406 | 2FA required | triggers 2FA flow |
| 490 | Checkpoint after 2FA | `"checkpoint"` |

---

## APK Patching (Emulator Crash Fix)

### The Problem
Both APKs crash on emulators due to `DalvikInternals.<clinit>()` → `integrateWithLibSigChain()` → `mprotect: Permission denied`.

### The Fix
1. Decompile with `apktool d -f -r <apk>` (skip resources)
2. Patch `DalvikInternals.smali`: replace native methods with no-ops, wrap `<clinit>` in try-catch
3. Rebuild, sign with apksigner v2, zipalign

### Emulator Requirements
- **BlueStacks 5** or **MEmu Play** (ARM translation)
- Standard Android SDK emulator does NOT work (arm64-only native libs)
- Install Facebook Katana first → login → then install Meta Suite → "Continue as" flow

---

## Test Results (2026-04-05)
```
61574519184008 → disabled (error_code=1)
61577477375595 → disabled (error_code=1)
61577485963370 → disabled (error_code=1)
61575529792497 → wrong_pass (error_code=401) ← alive but wrong password
61576794272075 → disabled (error_code=1)
61577870139812 → disabled (error_code=1)
```

---

## Current Code Status

### What Works
- Full login flow with automatic 2FA
- All 31 login params + sig computation
- Graph API helpers (get_user_info, get_pages, create_page, search_categories)
- CLI with 4 subcommands, multi-threaded, proxy rotation

### Planned Changes
- Dual identity support (katana + pages_manager)
- `--identity` CLI flag
- `search-categories` subcommand
- `.gitignore`, cleanup committed artifacts
