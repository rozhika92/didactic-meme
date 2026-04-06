#!/usr/bin/env python3
"""
viber_checker.py — CLI tool for Viber Bot/Channel API interaction.

Subcommands:
  fetch    Fetch Viber account data from the management backend by serial number.
  check    Send phone numbers as contacts via the Viber Bot/Channel API.
  details  Get user details and online status for subscriber IDs.
"""

import argparse
import csv
import json
import os
import sys

from viber.account_fetcher import fetch_account
from viber.bot_api import ViberBotAPI
from viber.checker import ViberChecker
from viber.utils import load_contacts, download_avatar, green, red, yellow, cyan, bold

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def load_config() -> dict:
    """Load config.json if it exists, return empty dict otherwise."""
    if os.path.isfile(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


# ---------------------------------------------------------------------------
# Pretty-print helpers
# ---------------------------------------------------------------------------

def print_json(data: dict) -> None:
    """Print dict as indented, colored JSON."""
    text = json.dumps(data, indent=2, ensure_ascii=False)
    # Highlight keys in cyan, values in default
    lines = []
    for line in text.splitlines():
        if ': ' in line:
            key_part, _, val_part = line.partition(': ')
            lines.append(f"{cyan(key_part)}: {val_part}")
        else:
            lines.append(line)
    print('\n'.join(lines))


def print_table(results: list) -> None:
    """
    Print results as a Unicode box-drawing table:

    ╔══════════════════╦════════╦═══════════════════╗
    ║ Phone            ║ Status ║ Detail            ║
    ╠══════════════════╬════════╬═══════════════════╣
    ║ +60111234567     ║ ✓ sent ║ ok                ║
    ╚══════════════════╩════════╩═══════════════════╝
    """
    col_phone  = max(len("Phone"),  max((len(r["phone"])  for r in results), default=0))
    col_status = max(len("Status"), 6)   # "✓ sent" / "✗ err " both 6 visible chars
    col_detail = max(len("Detail"), max((len(r["detail"]) for r in results), default=0))

    def row(phone, status, detail, color_fn=None):
        p = phone.ljust(col_phone)
        s = status.ljust(col_status)
        d = detail.ljust(col_detail)
        if color_fn:
            s = color_fn(s)
        return f"║ {p} ║ {s} ║ {d} ║"

    top    = f"╔{'═' * (col_phone + 2)}╦{'═' * (col_status + 2)}╦{'═' * (col_detail + 2)}╗"
    mid    = f"╠{'═' * (col_phone + 2)}╬{'═' * (col_status + 2)}╬{'═' * (col_detail + 2)}╣"
    bottom = f"╚{'═' * (col_phone + 2)}╩{'═' * (col_status + 2)}╩{'═' * (col_detail + 2)}╝"

    print(top)
    print(row("Phone", "Status", "Detail"))
    print(mid)
    for r in results:
        if r["status"] == "sent":
            status_str = "✓ sent"
            cfn = green
        else:
            status_str = "✗ err "
            cfn = red
        print(row(r["phone"], status_str, r["detail"], cfn))
    print(bottom)


# ---------------------------------------------------------------------------
# Subcommand: fetch
# ---------------------------------------------------------------------------

def cmd_fetch(args: argparse.Namespace) -> int:
    serial = args.serial.strip()
    print(bold(f"Fetching account for serial: {cyan(serial)}"))
    print()

    result = fetch_account(serial)

    if not result.get("success"):
        print(red("Failed to fetch account data."))
        err = result.get("error") or result.get("message") or json.dumps(result)
        print(red(f"  Error: {err}"))
        return 1

    # Summary block
    print(bold("Account Info"))
    print(f"  {'Phone':20s} {green(result.get('phone', 'N/A'))}")
    print(f"  {'ID':20s} {result.get('id', 'N/A')}")
    print(f"  {'Package':20s} {result.get('package', 'N/A')}")
    print(f"  {'Restore file keys':20s} {result.get('restore_file_count', 0)}")
    print()

    decoded = result.get("decoded_fields", {})
    if decoded:
        print(bold("Decoded Fields"))
        for k, v in decoded.items():
            label = k.replace("_", " ").title()
            print(f"  {label:20s} {cyan(v) if v else yellow('(empty)')}")
        print()

    print(bold("Raw Response"))
    print_json(result)
    return 0


# ---------------------------------------------------------------------------
# Subcommand: check
# ---------------------------------------------------------------------------

def cmd_check(args: argparse.Namespace) -> int:
    config = load_config()

    # Resolve auth token: CLI arg > config file
    token = args.token or config.get("token", "")
    if not token:
        print(red("Error: Viber auth token is required."))
        print(red("  Pass --token <TOKEN> or set \"token\" in config.json"))
        return 1

    # Resolve phone list
    if not args.file and not args.phone:
        print(red("Error: provide --file <contacts.txt> or --phone <number>"))
        return 1

    if args.file:
        if not os.path.isfile(args.file):
            print(red(f"Error: contacts file not found: {args.file}"))
            return 1
        phone_numbers = load_contacts(args.file)
        if not phone_numbers:
            print(yellow("Warning: contacts file is empty or contains only comments."))
            return 0
        print(bold(f"Loaded {len(phone_numbers)} number(s) from {args.file}"))
    else:
        phone_numbers = [args.phone]
        print(bold(f"Checking single number: {cyan(args.phone)}"))

    delay = args.delay

    # Initialize API and checker
    bot_api = ViberBotAPI(token)
    checker = ViberChecker(bot_api)

    # Setup: webhook + account info
    print(bold("\nInitializing Viber Bot API..."))
    try:
        uid = checker.setup()
        print(f"  Webhook set    {green('OK')}")
        print(f"  Sender ID      {cyan(uid)}")
    except RuntimeError as e:
        print(red(f"  Setup failed: {e}"))
        return 1

    # Send contacts
    print(bold(f"\nSending {len(phone_numbers)} contact(s) (delay={delay}s)...\n"))
    results = checker.check_numbers(phone_numbers, delay=delay)

    # Print table
    print_table(results)
    print()

    # Summary
    sent   = sum(1 for r in results if r["status"] == "sent")
    errors = len(results) - sent
    total  = len(results)

    summary = f"{green(str(sent))} sent, {red(str(errors))} errors out of {bold(str(total))} total"
    print(f"  {summary}")
    print()

    # Optional JSON output
    if args.output:
        try:
            with open(args.output, "w") as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            print(f"  Results saved to {cyan(args.output)}")
        except OSError as e:
            print(red(f"  Could not write output file: {e}"))
            return 1

    # Optional CSV output
    if args.csv:
        try:
            with open(args.csv, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["phone", "status", "detail", "message_token"])
                for r in results:
                    writer.writerow([
                        r["phone"],
                        r["status"],
                        r["detail"],
                        r.get("message_token", ""),
                    ])
            print(f"  CSV saved to {cyan(args.csv)}")
        except OSError as e:
            print(red(f"  Could not write CSV file: {e}"))
            return 1

    return 0 if errors == 0 else 2


# ---------------------------------------------------------------------------
# Subcommand: details
# ---------------------------------------------------------------------------

def _fmt_last_online(ts: int) -> str:
    """Convert millisecond timestamp to a human-readable string, or '-' if zero."""
    if not ts:
        return "-"
    import datetime
    try:
        dt = datetime.datetime.utcfromtimestamp(ts / 1000)
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return str(ts)


def print_details_table(results: list) -> None:
    """Print subscriber details as a Unicode box-drawing table."""
    col_id     = max(len("ID"),            max((len(r["id"])   for r in results), default=0))
    col_name   = max(len("Name"),          max((len(r["name"]) for r in results), default=0))
    col_status = max(len("Online Status"), max((len(r["online_status_text"]) for r in results), default=0))
    col_last   = max(len("Last Online"),   max((len(_fmt_last_online(r["last_online"])) for r in results), default=0))
    col_avatar = max(len("Avatar URL"),    max((len(r["avatar_url"]) for r in results), default=0))

    status_color = {
        "online": green,
        "offline": red,
        "undisclosed": yellow,
    }

    def bar(tl, tm, tr, lc, mc, rc, bc):
        return (
            tl
            + bc * (col_id + 2) + lc
            + bc * (col_name + 2) + mc
            + bc * (col_status + 2) + mc
            + bc * (col_last + 2) + mc
            + bc * (col_avatar + 2)
            + tr
        )

    def row(id_, name, status, last, avatar, color_fn=None):
        s = status.ljust(col_status)
        if color_fn:
            s = color_fn(s)
        return (
            f"\u2551 {id_.ljust(col_id)} "
            f"\u2551 {name.ljust(col_name)} "
            f"\u2551 {s} "
            f"\u2551 {last.ljust(col_last)} "
            f"\u2551 {avatar.ljust(col_avatar)} \u2551"
        )

    print(bar('\u2554', '\u2566', '\u2557', '\u2566', '\u2566', '\u2566', '\u2550'))
    print(row("ID", "Name", "Online Status", "Last Online", "Avatar URL"))
    print(bar('\u2560', '\u256c', '\u2563', '\u256c', '\u256c', '\u256c', '\u2550'))
    for r in results:
        cfn = status_color.get(r["online_status_text"])
        print(row(
            r["id"],
            r["name"],
            r["online_status_text"],
            _fmt_last_online(r["last_online"]),
            r["avatar_url"],
            cfn,
        ))
    print(bar('\u255a', '\u2569', '\u255d', '\u2569', '\u2569', '\u2569', '\u2550'))


def cmd_details(args: argparse.Namespace) -> int:
    config = load_config()

    token = args.token or config.get("token", "")
    if not token:
        print(red("Error: Viber auth token is required."))
        print(red('  Pass --token <TOKEN> or set "token" in config.json'))
        return 1

    bot_api = ViberBotAPI(token)
    checker = ViberChecker(bot_api)

    print(bold("Initializing Viber Bot API..."))
    try:
        uid = checker.setup()
        print(f"  Webhook set    {green('OK')}")
        print(f"  Sender ID      {cyan(uid)}")
    except RuntimeError as e:
        print(red(f"  Setup failed: {e}"))
        return 1

    subscriber_ids = args.ids
    print(bold(f"\nFetching details for {len(subscriber_ids)} subscriber(s)...\n"))
    results = checker.get_subscriber_details(subscriber_ids)

    # Download avatars if requested
    for r in results:
        r["avatar_local_path"] = ""
        if args.avatars and r["avatar_url"]:
            local = download_avatar(r["avatar_url"], args.avatars, r["id"])
            r["avatar_local_path"] = local
            if local:
                print(f"  Avatar saved: {cyan(local)}")
            else:
                print(yellow(f"  Avatar download failed for {r['id']}"))

    if args.avatars:
        print()

    print_details_table(results)
    print()

    # Optional CSV output
    if args.csv:
        try:
            with open(args.csv, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["id", "name", "country", "language", "online_status",
                                  "last_online", "avatar_url", "avatar_local_path"])
                for r in results:
                    writer.writerow([
                        r["id"],
                        r["name"],
                        r["country"],
                        r["language"],
                        r["online_status_text"],
                        _fmt_last_online(r["last_online"]),
                        r["avatar_url"],
                        r.get("avatar_local_path", ""),
                    ])
            print(f"  CSV saved to {cyan(args.csv)}")
        except OSError as e:
            print(red(f"  Could not write CSV file: {e}"))
            return 1

    return 0


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="viber_checker",
        description="Viber Bot/Channel API CLI tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python viber_checker.py fetch --serial SN1234567890
  python viber_checker.py check --token TOKEN123 --phone +60111234567
  python viber_checker.py check --token TOKEN123 --file contacts.txt --output results.json
  python viber_checker.py check --file contacts.txt --delay 1.0 --csv out.csv
  python viber_checker.py details --token TOKEN123 --ids ID1 ID2 ID3
  python viber_checker.py details --token TOKEN123 --ids ID1 --avatars ./avatars --csv subs.csv
        """,
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    # -- fetch --
    p_fetch = sub.add_parser(
        "fetch",
        help="Fetch Viber account data by serial number",
        description="Query the account management backend for a device serial number.",
    )
    p_fetch.add_argument(
        "--serial",
        required=True,
        metavar="SERIAL",
        help="Device serial number to look up",
    )

    # -- check --
    p_check = sub.add_parser(
        "check",
        help="Send phone numbers as contacts via the Viber Bot API",
        description=(
            "Post phone numbers as contact messages to a Viber Channel.\n"
            "Open the channel in the Viber app to see which numbers are active Viber users."
        ),
    )
    p_check.add_argument(
        "--token",
        default=None,
        metavar="TOKEN",
        help="Viber Bot/Channel auth token (falls back to config.json)",
    )
    p_check.add_argument(
        "--file",
        default=None,
        metavar="FILE",
        help="Path to contacts file (one phone number per line)",
    )
    p_check.add_argument(
        "--phone",
        default=None,
        metavar="PHONE",
        help="Single phone number to check (e.g. +60111234567)",
    )
    p_check.add_argument(
        "--output",
        default=None,
        metavar="FILE",
        help="Save full results as JSON to this file",
    )
    p_check.add_argument(
        "--delay",
        type=float,
        default=0.5,
        metavar="SECONDS",
        help="Delay between API calls in seconds (default: 0.5)",
    )
    p_check.add_argument(
        "--csv",
        default=None,
        metavar="FILE",
        help="Save results as CSV file",
    )

    # -- details --
    p_details = sub.add_parser(
        "details",
        help="Get user details and online status for subscriber IDs",
        description=(
            "Fetch name, avatar, country, language, and online status for known\n"
            "subscriber IDs. Requires users to have subscribed to the bot/channel."
        ),
    )
    p_details.add_argument(
        "--token",
        default=None,
        metavar="TOKEN",
        help="Viber Bot/Channel auth token (falls back to config.json)",
    )
    p_details.add_argument(
        "--ids",
        required=True,
        nargs="+",
        metavar="ID",
        help="One or more subscriber IDs to look up",
    )
    p_details.add_argument(
        "--csv",
        default=None,
        metavar="FILE",
        help="Save results as CSV file",
    )
    p_details.add_argument(
        "--avatars",
        default=None,
        metavar="DIR",
        help="Download avatar images to this directory",
    )

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "fetch":
        return cmd_fetch(args)
    elif args.command == "check":
        return cmd_check(args)
    elif args.command == "details":
        return cmd_details(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
