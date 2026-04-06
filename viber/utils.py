import os
import re
import requests as _requests


def format_phone_number(phone: str) -> str:
    """Normalize phone number to international format with + prefix."""
    phone = re.sub(r'[\s\-\(\)\.]', '', phone.strip())
    if not phone.startswith('+'):
        phone = '+' + phone
    return phone


def load_contacts(filepath: str) -> list:
    """Load phone numbers from a text file. One per line. Skips empty lines and # comments."""
    numbers = []
    with open(filepath, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                numbers.append(line)
    return numbers


# ANSI color helpers
class Color:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    RESET = '\033[0m'


def green(text): return f"{Color.GREEN}{text}{Color.RESET}"
def red(text): return f"{Color.RED}{text}{Color.RESET}"
def yellow(text): return f"{Color.YELLOW}{text}{Color.RESET}"
def cyan(text): return f"{Color.CYAN}{text}{Color.RESET}"
def bold(text): return f"{Color.BOLD}{text}{Color.RESET}"


def download_avatar(url: str, save_dir: str, filename: str) -> str:
    """Download avatar image from URL. Returns local file path or empty string on failure."""
    if not url:
        return ""
    os.makedirs(save_dir, exist_ok=True)
    # Determine extension from URL or default to .jpg
    ext = os.path.splitext(url.split('?')[0])[1] or '.jpg'
    filepath = os.path.join(save_dir, f"{filename}{ext}")
    try:
        resp = _requests.get(url, timeout=10)
        resp.raise_for_status()
        with open(filepath, 'wb') as f:
            f.write(resp.content)
        return filepath
    except Exception:
        return ""
