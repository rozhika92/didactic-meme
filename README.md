# Meta Business Suite API Research Tool

University final project focused on reverse-engineering the Meta Business Suite Android API for educational use. The client reproduces the verified mobile auth flow, handles automatic TOTP-based 2FA, and exposes batch CLI commands for login, page listing, page creation, and category search.

## Project overview

- Reverse-engineered from `com.facebook.katana` and `com.facebook.pages.app`
- Preserves the verified `auth.login` endpoint, 31 login parameters, MD5 `sig`, and 2FA flow
- Supports dual app identities through a shared Python client and CLI
- Includes patched APK workflow for emulator-based validation

## Quick start

Install dependencies:

```bash
pip install -r requirements.txt
```

Run a basic login batch:

```bash
python run.py login --file accounts.txt --identity katana
```

## App identities

| Identity | Package | API key | API secret | FBAN | Typical use |
|---|---|---|---|---|---|
| `katana` | `com.facebook.katana` | `350685531728` | `62f8ce9f74b12f84c123cc23437a4a32` | `FB4A` | Main Facebook app identity |
| `pages_manager` | `com.facebook.pages.app` | `121876164619130` | `1ab2c5c902faedd339c14b2d58e929dc` | `PagesManager` | Meta Business Suite / Pages Manager |

## CLI usage

All batch commands support `--identity`, `--threads`, `--delay`, and `--proxy-file`.

### `login`

```bash
python run.py login --file accounts.txt --identity katana
python run.py login --file accounts.txt --identity pages_manager --threads 10 --delay 0.5
```

### `create-page`

```bash
python run.py create-page --file accounts.txt --name "PageName" --category 2200 --identity katana
```

### `get-pages`

```bash
python run.py get-pages --file accounts.txt --identity pages_manager
```

### `full`

```bash
python run.py full --file accounts.txt --name "PageName" --category 2200 --identity katana
```

### `search-categories`

```bash
python run.py search-categories --query "restaurant" --token EAAB... --identity pages_manager
```

## APK patching

The Android APKs crash on common emulators because `DalvikInternals` attempts to integrate libsigchain and call `mprotect`. The reproducible patching workflow lives in @apks/patch_apk.py and replaces the failing native paths with no-ops before rebuild/signing.

Prepatched APKs are expected under `apks/` and tracked through Git LFS. If the filebin links expire, use @apks/patch_apk.py with the original APK inputs to regenerate patched builds.

## Emulator setup

- Use **BlueStacks 5** or **MEmu Play** with ARM translation
- Standard Android SDK emulators are not sufficient for these APKs
- Install Facebook Katana first and complete login
- Install Meta Business Suite second and use the in-app "Continue as" flow

## File structure

- @meta_api.py — API client, identity definitions, auth flow, and Graph helpers
- @run.py — CLI entrypoint with batch processing and category search
- @accounts.txt — account input file in `uid|password|totp_secret` format
- @proxies.txt — rotating proxy input file
- @requirements.txt — Python dependencies
- @apks/patch_apk.py — reproducible APK patching script
- @apks/ — patched APK storage location
- @PROJECT_CONTEXT.md — comprehensive technical reference for future sessions

## Technical reference

See @PROJECT_CONTEXT.md for the full API specification, extracted app identities, emulator notes, and current research status.
