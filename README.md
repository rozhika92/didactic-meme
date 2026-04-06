# Viber Checker

A Python CLI tool for interacting with the **Viber Bot/Channel REST API** and a Viber account management backend. It provides three features:

1. **Account Fetcher** — Query a device management backend by serial number to retrieve Viber account credentials and decoded device data.
2. **Contact Checker** — Post phone numbers as contact messages to a Viber Channel via the official Bot API, letting you determine which numbers belong to active Viber users.
3. **Subscriber Details** — Fetch name, avatar, country, language, and online status for known subscriber IDs.

---

## Prerequisites

- Python 3.7+
- A Viber **Bot** or **Channel** auth token
- (Optional) Access to the account management backend for the `fetch` subcommand

### Getting a Viber Channel Auth Token

1. Open the Viber app → **More** → **Viber for Business**.
2. Create a **Channel** (or use an existing one).
3. Go to Channel **Settings** → copy the **Auth Token**.

Alternatively, apply for a Viber Bot account at: https://help.viber.com/hc/en-us/articles/15247629658525

---

## Installation

```bash
pip install -r requirements.txt
```

---

## Usage

### `fetch` — Retrieve account data by serial number

```bash
python viber_checker.py fetch --serial SN1234567890
```

**Output:**
- Phone number registered to the account
- Internal account ID and package name
- Decoded fields from the restore file: `reg_member_id`, `device_key`, `viber_udid`, `phone_num`, `country_code`
- Count of restore file keys

**Example:**
```
Fetching account for serial: SN1234567890

Account Info
  Phone                +60111234567
  ID                   abc123
  Package              com.viber.voip
  Restore file keys    47

Decoded Fields
  Reg Member Id        8675309
  Device Key           abcdef1234567890
  Viber Udid           xxxx-yyyy-zzzz
  Phone Num            60111234567
  Country Code         MY
```

---

### `check` — Send phone numbers as contacts via the Viber Bot API

```bash
# Single number
python viber_checker.py check --token YOUR_TOKEN --phone +60111234567

# From a contacts file
python viber_checker.py check --token YOUR_TOKEN --file contacts.txt

# Save results to JSON
python viber_checker.py check --token YOUR_TOKEN --file contacts.txt --output results.json

# Save results to CSV
python viber_checker.py check --token YOUR_TOKEN --file contacts.txt --csv results.csv

# Custom delay between API calls
python viber_checker.py check --token YOUR_TOKEN --file contacts.txt --delay 1.0

# Use token from config.json (no --token flag needed)
python viber_checker.py check --file contacts.txt
```

**Options:**

| Flag | Description |
|------|-------------|
| `--token TOKEN` | Viber Bot/Channel auth token (overrides config.json) |
| `--file FILE` | Path to contacts file (one phone number per line) |
| `--phone PHONE` | Single phone number, e.g. `+60111234567` |
| `--output FILE` | Save full JSON results to this file |
| `--csv FILE` | Save results as CSV (`phone,status,detail,message_token`) |
| `--delay SECONDS` | Delay between API calls (default: `0.5`) |

**Example output:**
```
Initializing Viber Bot API...
  Webhook set    OK
  Sender ID      Uxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

Sending 4 contact(s) (delay=0.5s)...

╔══════════════════╦════════╦══════════════════════╗
║ Phone            ║ Status ║ Detail               ║
╠══════════════════╬════════╬══════════════════════╣
║ +60111234567     ║ ✓ sent ║ ok                   ║
║ +60129876543     ║ ✓ sent ║ ok                   ║
║ +14155551234     ║ ✗ err  ║ invalidAuthToken     ║
║ +447911123456    ║ ✓ sent ║ ok                   ║
╚══════════════════╩════════╩══════════════════════╝

  3 sent, 1 errors out of 4 total
```

---

### `details` — Fetch subscriber details and online status

```bash
# Look up one or more subscriber IDs
python viber_checker.py details --token YOUR_TOKEN --ids Uabc123 Udef456

# Download avatar images to a local directory
python viber_checker.py details --token YOUR_TOKEN --ids Uabc123 --avatars ./avatars

# Save results to CSV
python viber_checker.py details --token YOUR_TOKEN --ids Uabc123 Udef456 --csv subs.csv

# Combine all options
python viber_checker.py details --ids Uabc123 --avatars ./avatars --csv subs.csv
```

**Options:**

| Flag | Description |
|------|-------------|
| `--token TOKEN` | Viber Bot/Channel auth token (overrides config.json) |
| `--ids ID [ID ...]` | One or more subscriber IDs to look up |
| `--avatars DIR` | Download avatar images to this directory |
| `--csv FILE` | Save results as CSV (`id,name,country,language,online_status,last_online,avatar_url,avatar_local_path`) |

**Example output:**
```
Initializing Viber Bot API...
  Webhook set    OK
  Sender ID      Uxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

Fetching details for 2 subscriber(s)...

╔══════════════════════╦══════════════╦═══════════════╦══════════════════════╦══════════════════════════════╗
║ ID                   ║ Name         ║ Online Status ║ Last Online          ║ Avatar URL                   ║
╠══════════════════════╬══════════════╬═══════════════╬══════════════════════╬══════════════════════════════╣
║ Uabc123              ║ Alice Smith  ║ online        ║ -                    ║ https://example.com/a.jpg    ║
║ Udef456              ║ Bob Jones    ║ offline       ║ 2026-03-30 14:22 UTC ║ https://example.com/b.jpg    ║
╚══════════════════════╩══════════════╩═══════════════╩══════════════════════╩══════════════════════════════╝
```

**Note:** `get_user_details` and `get_online` only work for users who have **subscribed** to your bot or channel. Unsubscribed users will return empty details and `not_a_member` online status.

---

## Interpreting Results

| Status | Meaning |
|--------|---------|
| `✓ sent` | The contact was successfully posted to the Viber Channel |
| `✗ err` | The API rejected the request (see Detail column for reason) |

**Important:** A `sent` status only confirms the message was delivered to the channel — it does **not** directly indicate whether the number is registered on Viber. To check Viber registration, open your Channel in the Viber app: contacts that resolve with a Viber profile picture and name are active Viber users.

Common error detail values:

| Detail | Cause |
|--------|-------|
| `invalidAuthToken` | Token is wrong or expired |
| `notSubscribed` | Sender ID is not a channel subscriber |
| `tooManyRequests` | Rate limit hit — increase `--delay` |

---

## Config File

`config.json` stores defaults used when CLI flags are omitted:

```json
{
    "token": "",
    "uid": "",
    "first_time": 1,
    "webhook_url": "https://proton.me/"
}
```

| Key | Description |
|-----|-------------|
| `token` | Default Viber Bot/Channel auth token |
| `uid` | (Informational) Your sender user ID |
| `first_time` | Flag to track first-time setup |
| `webhook_url` | Webhook URL passed to `set_webhook` |

Set `"token"` here to avoid passing `--token` on every command.

---

## Contacts File Format

`contacts.txt` — one phone number per line in international format:

```
# Lines starting with # are ignored
+60111234567
+60129876543
+14155551234
+447911123456
```

Phone numbers are normalized automatically: spaces, dashes, parentheses, and dots are stripped, and a `+` prefix is added if missing.

---

## Limitations

- **Rate limiting:** Viber's Bot API enforces rate limits. Use `--delay 1.0` or higher for large batches.
- **Webhook requirement:** The `check` command calls `set_webhook` on every run. The URL (`https://proton.me/`) is a placeholder — Viber will return 200 without actually receiving callbacks.
- **Channel vs. Bot:** The `post` endpoint requires a **Channel** token, not a Bot token. Bots use a different messaging flow.
- **No direct Viber registration lookup:** The API does not expose a "is this number on Viber?" endpoint. Contact-posting is the indirect method for bulk checks.
- **Subscriber-only APIs:** `get_user_details` and `get_online` (used by the `details` subcommand) only return data for users who have subscribed to your bot or channel. Non-subscribers return empty detail fields and `not_a_member` online status.
- **`fetch` backend:** The account management backend (`wa.mysocialfans.net`) is private infrastructure. The `fetch` subcommand will not work without valid credentials/access.

---

## Project Structure

```
├── viber_checker.py        # Main CLI entry point
├── viber/
│   ├── __init__.py
│   ├── account_fetcher.py  # Management backend client + Java string decoder
│   ├── bot_api.py          # Viber Bot/Channel REST API wrapper (incl. get_user_details)
│   ├── checker.py          # High-level phone checking + subscriber details logic
│   └── utils.py            # Phone formatting, file loading, avatar download, ANSI colors
├── config.json             # Default token and settings
├── contacts.txt            # Sample contact list
└── requirements.txt
```

---

## API Reference

- Viber Bot/Channel REST API: https://developers.viber.com/docs/api/rest-bot-api/
- Viber Channel creation: https://help.viber.com/hc/en-us/articles/15247629658525
