# Meta Business Suite API Research Tool

Python client replicating Meta Business Suite (`com.facebook.pages.app`) API calls. Built by reverse engineering the Android APK using jadx as part of a university final project.

## Disclaimer

Educational and research use only.

## Installation

```bash
pip install -r requirements.txt
```

## Usage

### Login and verify tokens

```bash
python run.py login --file accounts.txt
```

### Create a page for each account

```bash
python run.py create-page --file accounts.txt --name "PageName" --category 2200
```

### Fetch all pages for each account

```bash
python run.py get-pages --file accounts.txt
```

### Full workflow

```bash
python run.py full --file accounts.txt --name "PageName" --category 2200
```

## CLI flags

All commands support:

- `--threads N` to process accounts concurrently with `ThreadPoolExecutor` (default: `5`)
- `--delay SECONDS` to add a per-thread delay between accounts and reduce rate-limit spikes (default: `1.0`)
- `--proxy-file PATH` to override the proxy list file

Examples:

```bash
python run.py login --file accounts.txt --threads 10 --delay 0.5
python run.py create-page --file accounts.txt --name "PageName" --category 2200 --threads 3 --delay 2
```

## Output files

Each run creates timestamped artifacts:

- `logs/YYYY-MM-DD_HHMMSS.log` — per-request execution log with timestamps
- `results/tokens_YYYYMMDD_HHMMSS.txt` — `uid|access_token|name`
- `results/pages_YYYYMMDD_HHMMSS.txt` — `uid|page_id|page_name|page_token|category`
- `results/created_YYYYMMDD_HHMMSS.txt` — `page_id|page_name|page_token|owner_uid`
- `results/errors_YYYYMMDD_HHMMSS.txt` — `uid|status|error_message`

`login` writes token and error files, `get-pages` writes page and error files, `create-page` writes created-page and error files, and `full` writes all of them.

## Multi-threading behavior

- Accounts are distributed across worker threads in round-robin order
- Proxies are still assigned round-robin per account
- Delay is applied inside each worker thread between consecutive accounts handled by that worker
- Failures are isolated per account; one exception never stops the whole batch

## Proxy Support

- Put proxies in `proxies.txt`, one per line
- Supported formats:
  - `host:port:user:pass`
  - `host:port`
  - raw proxy URLs such as `http://user:pass@host:port`
- Proxies rotate per account during batch execution
- Pass `--proxy-file custom_proxies.txt` to use a different proxy list

Example:

```bash
python run.py login --file accounts.txt --proxy-file proxies.txt
```

## Credential format

Each line in `accounts.txt` uses:

```text
uid|password|2fa_secret
```

- `uid`: Facebook numeric ID or email address
- `password`: Account password
- `2fa_secret`: Base32-encoded TOTP secret used for automatic 2FA generation

Lines beginning with `#` are treated as comments. Blank lines are ignored.

## API Details

### Authentication endpoint and signature computation

- Authentication endpoint: `https://b-api.facebook.com/method/auth.login`
- Signature parameter: `sig`
- Signature algorithm:
  1. Sort all request parameters alphabetically by key
  2. Concatenate them as `key=value` with no separators
  3. Append the extracted app secret
  4. Compute the MD5 digest of the final string

The client reproduces the mobile authentication flow used by the Android app, including app identity values, device identifiers, and request headers extracted from the decompiled APK.

### TOTP / 2FA flow

- Initial login is sent with `credentials_type=password`
- If the API returns error code `406`, the client parses `error_data`
- A TOTP code is generated from the supplied Base32 2FA secret using RFC 6238 semantics
- A second login request is sent with:
  - `credentials_type=two_factor`
  - `twofactor_code`
  - `userid`
  - `first_factor`
  - `machine_id`

### Graph API page operations

- Base Graph URL: `https://b-graph.facebook.com`
- Supported operations:
  - `GET /me` for basic user verification
  - `GET /me/accounts` to list managed pages and page access tokens
  - `POST /{user_id}/accounts` to create a page
  - `GET /pages/search?type=placetopic&q=...` to search page categories

### App identity

The client uses the reverse-engineered Android app identity:

- App ID: `121876164619130`
- App Version: `546.0.0.56.106`
- Build Number: `917854681`
- API Key: `121876164619130` (the app uses the App ID as `api_key`)
- API Secret: `1ab2c5c902faedd339c14b2d58e929dc`
- Mobile authentication headers include:
  - `User-Agent: [FBAN/PagesManager;FBAV/546.0.0.56.106;FBBV/917854681;FBPN/com.facebook.pages.app;FBLC/en_US;FBCR/;FBMF/Google;FBBD/google;FBDV/Pixel 6;FBSV/13.0;FBCA/arm64-v8a:;FB_FW/1;]`
  - `X-FB-HTTP-Engine: Liger`
  - `X-FB-Connection-Quality: EXCELLENT`
  - `X-FB-Friendly-Name: authenticate`
  - `Accept-Language: en_US`

Only the headers confirmed in the APK decompilation are sent from Java:

- `User-Agent`
- `Content-Type: application/x-www-form-urlencoded`
- `X-FB-HTTP-Engine: Liger`
- `X-FB-Connection-Quality: EXCELLENT`
- `X-FB-Friendly-Name: authenticate`
- `Accept-Encoding: gzip, deflate`
- `Accept-Language: en_US`

## Error codes

| Code | Meaning |
|------|---------|
| 406 | 2FA required |
| 490 | Checkpoint |
| 1 | Disabled |
| 401 | Wrong password |
| 368 | Rate limited |

## Category IDs

Common page category IDs:

- `2256` = Beauty
- `2078` = Local Service
- `181475575221097` = Restaurant
- `2201` = Product/Service
- `2700` = Shopping & Retail
- `1703` = Brand
- `2603` = Website
