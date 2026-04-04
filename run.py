import argparse
import random
import time
from pathlib import Path

from meta_api import MetaBusinessAPI


GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"


def parse_accounts(filepath):
    accounts = []
    with open(filepath, "r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [part.strip() for part in line.split("|")]
            if len(parts) != 3:
                raise ValueError(f"Invalid account line: {raw_line.rstrip()}")
            accounts.append(
                {
                    "uid": parts[0],
                    "password": parts[1],
                    "totp_secret": parts[2],
                }
            )
    return accounts


def load_proxies(filepath):
    """Load proxies from file. Format: host:port:user:pass (one per line). Comments/blank lines skipped."""
    proxies = []
    path = Path(filepath)
    if not path.exists():
        return proxies
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(":")
            if len(parts) == 4:
                host, port, user, pw = parts
                proxies.append(f"http://{user}:{pw}@{host}:{port}")
            elif len(parts) == 2:
                proxies.append(f"http://{line}")
            else:
                proxies.append(line if "://" in line else f"http://{line}")
    return proxies


def append_line(filepath, line):
    with open(filepath, "a", encoding="utf-8") as handle:
        handle.write(f"{line}\n")


def print_status(color, message):
    print(f"{color}{message}{RESET}")


def print_summary(summary):
    print(
        "Summary: "
        f"{summary['success']} success, "
        f"{summary['checkpoint']} checkpoint, "
        f"{summary['disabled']} disabled, "
        f"{summary['errors']} errors"
    )


def make_summary():
    return {"success": 0, "checkpoint": 0, "disabled": 0, "errors": 0}


def login_account(account, proxy=None):
    client = MetaBusinessAPI(proxy=proxy)
    return client, client.login(account["uid"], account["password"], account["totp_secret"])


def handle_login(args):
    accounts = parse_accounts(args.file)
    proxies = load_proxies(args.proxy_file)
    output_path = Path("tokens.txt")
    summary = make_summary()

    for index, account in enumerate(accounts, start=1):
        try:
            proxy = proxies[(index - 1) % len(proxies)] if proxies else None
            if proxy:
                display = proxy.split("@")[-1] if "@" in proxy else proxy.replace("http://", "")
                print(f"  Using proxy: {display}")
            client, result = login_account(account, proxy=proxy)
            status = result.get("status")

            if status == "ok":
                user_info = client.get_user_info(result["access_token"])
                if user_info.get("error"):
                    summary["errors"] += 1
                    print_status(
                        RED,
                        f"[{index}/{len(accounts)}] {account['uid']} login ok but verification failed: {user_info.get('msg', 'Unknown error')}",
                    )
                else:
                    append_line(
                        output_path,
                        f"{result.get('uid') or account['uid']}|{result['access_token']}|{user_info.get('name', '')}",
                    )
                    summary["success"] += 1
                    print_status(
                        GREEN,
                        f"[{index}/{len(accounts)}] {account['uid']} success -> {user_info.get('name', '')}",
                    )
            elif status == "checkpoint":
                summary["checkpoint"] += 1
                print_status(
                    YELLOW,
                    f"[{index}/{len(accounts)}] {account['uid']} checkpoint: {result.get('error_msg', 'Checkpoint required')}",
                )
            elif status == "disabled":
                summary["disabled"] += 1
                print_status(
                    YELLOW,
                    f"[{index}/{len(accounts)}] {account['uid']} disabled: {result.get('error_msg', 'Account disabled')}",
                )
            else:
                summary["errors"] += 1
                print_status(
                    RED,
                    f"[{index}/{len(accounts)}] {account['uid']} error: {result.get('error_msg', 'Unknown error')}",
                )
        except Exception as exc:
            summary["errors"] += 1
            print_status(RED, f"[{index}/{len(accounts)}] {account['uid']} exception: {exc}")

        if index < len(accounts):
            time.sleep(random.uniform(1, 3))

    print_summary(summary)


def handle_create_page(args):
    accounts = parse_accounts(args.file)
    proxies = load_proxies(args.proxy_file)
    output_path = Path("results.txt")
    summary = make_summary()

    for index, account in enumerate(accounts, start=1):
        try:
            proxy = proxies[(index - 1) % len(proxies)] if proxies else None
            if proxy:
                display = proxy.split("@")[-1] if "@" in proxy else proxy.replace("http://", "")
                print(f"  Using proxy: {display}")
            client, result = login_account(account, proxy=proxy)
            status = result.get("status")

            if status != "ok":
                if status == "checkpoint":
                    summary["checkpoint"] += 1
                    print_status(
                        YELLOW,
                        f"[{index}/{len(accounts)}] {account['uid']} checkpoint: {result.get('error_msg', 'Checkpoint required')}",
                    )
                elif status == "disabled":
                    summary["disabled"] += 1
                    print_status(
                        YELLOW,
                        f"[{index}/{len(accounts)}] {account['uid']} disabled: {result.get('error_msg', 'Account disabled')}",
                    )
                else:
                    summary["errors"] += 1
                    print_status(
                        RED,
                        f"[{index}/{len(accounts)}] {account['uid']} login error: {result.get('error_msg', 'Unknown error')}",
                    )
                if index < len(accounts):
                    time.sleep(random.uniform(1, 3))
                continue

            user_id = str(result.get("uid") or account["uid"])
            created = client.create_page(result["access_token"], user_id, args.name, args.category)
            if created.get("error"):
                summary["errors"] += 1
                print_status(
                    RED,
                    f"[{index}/{len(accounts)}] {account['uid']} create-page error: {created.get('msg', 'Unknown error')}",
                )
            else:
                pages_result = client.get_pages(result["access_token"])
                if pages_result.get("error"):
                    summary["errors"] += 1
                    print_status(
                        RED,
                        f"[{index}/{len(accounts)}] {account['uid']} page fetch error: {pages_result.get('msg', 'Unknown error')}",
                    )
                else:
                    matched_page = next(
                        (
                            page
                            for page in pages_result.get("pages", [])
                            if page.get("name") == args.name
                        ),
                        None,
                    )
                    if matched_page is None:
                        summary["errors"] += 1
                        print_status(
                            RED,
                            f"[{index}/{len(accounts)}] {account['uid']} page created but token not found for {args.name}",
                        )
                    else:
                        append_line(
                            output_path,
                            f"{matched_page.get('id', '')}|{matched_page.get('name', '')}|{matched_page.get('access_token', '')}|{user_id}",
                        )
                        summary["success"] += 1
                        print_status(
                            GREEN,
                            f"[{index}/{len(accounts)}] {account['uid']} created page -> {matched_page.get('id', '')} {matched_page.get('name', '')}",
                        )
        except Exception as exc:
            summary["errors"] += 1
            print_status(RED, f"[{index}/{len(accounts)}] {account['uid']} exception: {exc}")

        if index < len(accounts):
            time.sleep(random.uniform(1, 3))

    print_summary(summary)


def render_pages_table(account_uid, pages):
    print(f"Account: {account_uid}")
    if not pages:
        print("  No pages found")
        return

    id_width = max(len("Page ID"), *(len(str(page.get("id", ""))) for page in pages))
    name_width = max(len("Page Name"), *(len(page.get("name", "")) for page in pages))
    cat_width = max(len("Category"), *(len(page.get("category", "")) for page in pages))

    header = f"  {'Page ID'.ljust(id_width)}  {'Page Name'.ljust(name_width)}  {'Category'.ljust(cat_width)}"
    print(header)
    print(f"  {'-' * id_width}  {'-' * name_width}  {'-' * cat_width}")
    for page in pages:
        print(
            "  "
            f"{str(page.get('id', '')).ljust(id_width)}  "
            f"{page.get('name', '').ljust(name_width)}  "
            f"{page.get('category', '').ljust(cat_width)}"
        )


def handle_get_pages(args):
    accounts = parse_accounts(args.file)
    proxies = load_proxies(args.proxy_file)
    output_path = Path("pages.txt")
    summary = make_summary()

    for index, account in enumerate(accounts, start=1):
        try:
            proxy = proxies[(index - 1) % len(proxies)] if proxies else None
            if proxy:
                display = proxy.split("@")[-1] if "@" in proxy else proxy.replace("http://", "")
                print(f"  Using proxy: {display}")
            client, result = login_account(account, proxy=proxy)
            status = result.get("status")

            if status != "ok":
                if status == "checkpoint":
                    summary["checkpoint"] += 1
                    print_status(
                        YELLOW,
                        f"[{index}/{len(accounts)}] {account['uid']} checkpoint: {result.get('error_msg', 'Checkpoint required')}",
                    )
                elif status == "disabled":
                    summary["disabled"] += 1
                    print_status(
                        YELLOW,
                        f"[{index}/{len(accounts)}] {account['uid']} disabled: {result.get('error_msg', 'Account disabled')}",
                    )
                else:
                    summary["errors"] += 1
                    print_status(
                        RED,
                        f"[{index}/{len(accounts)}] {account['uid']} login error: {result.get('error_msg', 'Unknown error')}",
                    )
                if index < len(accounts):
                    time.sleep(random.uniform(1, 3))
                continue

            pages_result = client.get_pages(result["access_token"])
            if pages_result.get("error"):
                summary["errors"] += 1
                print_status(
                    RED,
                    f"[{index}/{len(accounts)}] {account['uid']} get-pages error: {pages_result.get('msg', 'Unknown error')}",
                )
            else:
                pages = pages_result.get("pages", [])
                render_pages_table(account["uid"], pages)
                for page in pages:
                    append_line(
                        output_path,
                        f"{account['uid']}|{page.get('id', '')}|{page.get('name', '')}|{page.get('access_token', '')}|{page.get('category', '')}",
                    )
                summary["success"] += 1
                print_status(
                    GREEN,
                    f"[{index}/{len(accounts)}] {account['uid']} fetched {len(pages)} pages",
                )
        except Exception as exc:
            summary["errors"] += 1
            print_status(RED, f"[{index}/{len(accounts)}] {account['uid']} exception: {exc}")

        if index < len(accounts):
            time.sleep(random.uniform(1, 3))

    print_summary(summary)


def handle_full(args):
    accounts = parse_accounts(args.file)
    proxies = load_proxies(args.proxy_file)
    tokens_path = Path("tokens.txt")
    results_path = Path("results.txt")
    pages_path = Path("pages.txt")
    summary = make_summary()

    for index, account in enumerate(accounts, start=1):
        try:
            proxy = proxies[(index - 1) % len(proxies)] if proxies else None
            if proxy:
                display = proxy.split("@")[-1] if "@" in proxy else proxy.replace("http://", "")
                print(f"  Using proxy: {display}")
            client, result = login_account(account, proxy=proxy)
            status = result.get("status")

            if status != "ok":
                if status == "checkpoint":
                    summary["checkpoint"] += 1
                    print_status(
                        YELLOW,
                        f"[{index}/{len(accounts)}] {account['uid']} checkpoint: {result.get('error_msg', 'Checkpoint required')}",
                    )
                elif status == "disabled":
                    summary["disabled"] += 1
                    print_status(
                        YELLOW,
                        f"[{index}/{len(accounts)}] {account['uid']} disabled: {result.get('error_msg', 'Account disabled')}",
                    )
                else:
                    summary["errors"] += 1
                    print_status(
                        RED,
                        f"[{index}/{len(accounts)}] {account['uid']} login error: {result.get('error_msg', 'Unknown error')}",
                    )
                if index < len(accounts):
                    time.sleep(random.uniform(1, 3))
                continue

            user_info = client.get_user_info(result["access_token"])
            if user_info.get("error"):
                summary["errors"] += 1
                print_status(
                    RED,
                    f"[{index}/{len(accounts)}] {account['uid']} verification failed: {user_info.get('msg', 'Unknown error')}",
                )
                if index < len(accounts):
                    time.sleep(random.uniform(1, 3))
                continue

            user_id = str(result.get("uid") or account["uid"])
            append_line(
                tokens_path,
                f"{user_id}|{result['access_token']}|{user_info.get('name', '')}",
            )

            created = client.create_page(result["access_token"], user_id, args.name, args.category)
            if created.get("error"):
                summary["errors"] += 1
                print_status(
                    RED,
                    f"[{index}/{len(accounts)}] {account['uid']} create-page error: {created.get('msg', 'Unknown error')}",
                )
                if index < len(accounts):
                    time.sleep(random.uniform(1, 3))
                continue

            pages_result = client.get_pages(result["access_token"])
            if pages_result.get("error"):
                summary["errors"] += 1
                print_status(
                    RED,
                    f"[{index}/{len(accounts)}] {account['uid']} get-pages error: {pages_result.get('msg', 'Unknown error')}",
                )
                if index < len(accounts):
                    time.sleep(random.uniform(1, 3))
                continue

            pages = pages_result.get("pages", [])
            render_pages_table(account["uid"], pages)
            for page in pages:
                append_line(
                    pages_path,
                    f"{account['uid']}|{page.get('id', '')}|{page.get('name', '')}|{page.get('access_token', '')}|{page.get('category', '')}",
                )

            matched_page = next(
                (
                    page
                    for page in pages
                    if page.get("name") == args.name
                ),
                None,
            )
            if matched_page is None:
                summary["errors"] += 1
                print_status(
                    RED,
                    f"[{index}/{len(accounts)}] {account['uid']} page created but token not found for {args.name}",
                )
            else:
                append_line(
                    results_path,
                    f"{matched_page.get('id', '')}|{matched_page.get('name', '')}|{matched_page.get('access_token', '')}|{user_id}",
                )
                summary["success"] += 1
                print_status(
                    GREEN,
                    f"[{index}/{len(accounts)}] {account['uid']} full flow success -> {matched_page.get('id', '')} {matched_page.get('name', '')}",
                )
        except Exception as exc:
            summary["errors"] += 1
            print_status(RED, f"[{index}/{len(accounts)}] {account['uid']} exception: {exc}")

        if index < len(accounts):
            time.sleep(random.uniform(1, 3))

    print_summary(summary)


def build_parser():
    parser = argparse.ArgumentParser(
        description="Meta Business Suite API Research Tool"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    login_parser = subparsers.add_parser("login", help="Log in accounts and save tokens")
    login_parser.add_argument("--file", required=True, help="Path to accounts file")
    login_parser.add_argument("--proxy-file", default="proxies.txt", help="Path to proxies file (default: proxies.txt)")
    login_parser.set_defaults(func=handle_login)

    create_page_parser = subparsers.add_parser("create-page", help="Create a page for each account")
    create_page_parser.add_argument("--file", required=True, help="Path to accounts file")
    create_page_parser.add_argument("--name", required=True, help="Page name to create")
    create_page_parser.add_argument("--category", default="2256", help="Page category ID")
    create_page_parser.add_argument("--proxy-file", default="proxies.txt", help="Path to proxies file (default: proxies.txt)")
    create_page_parser.set_defaults(func=handle_create_page)

    get_pages_parser = subparsers.add_parser("get-pages", help="Fetch pages for each account")
    get_pages_parser.add_argument("--file", required=True, help="Path to accounts file")
    get_pages_parser.add_argument("--proxy-file", default="proxies.txt", help="Path to proxies file (default: proxies.txt)")
    get_pages_parser.set_defaults(func=handle_get_pages)

    full_parser = subparsers.add_parser("full", help="Run login, create-page, and get-pages flow")
    full_parser.add_argument("--file", required=True, help="Path to accounts file")
    full_parser.add_argument("--name", required=True, help="Page name to create")
    full_parser.add_argument("--category", default="2256", help="Page category ID")
    full_parser.add_argument("--proxy-file", default="proxies.txt", help="Path to proxies file (default: proxies.txt)")
    full_parser.set_defaults(func=handle_full)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
