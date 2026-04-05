import argparse
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from meta_api import MetaBusinessAPI


RESET = "\033[0m"
BOLD = "\033[1m"
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"


@dataclass
class RunState:
    command: str
    total: int
    delay: float
    logger: logging.Logger
    result_paths: dict[str, Path]
    summary: dict[str, int] = field(
        default_factory=lambda: {
            "total": 0,
            "success": 0,
            "checkpoint": 0,
            "rate_limit": 0,
            "disabled": 0,
            "wrong_pass": 0,
            "errors": 0,
        }
    )
    print_lock: threading.Lock = field(default_factory=threading.Lock)
    file_lock: threading.Lock = field(default_factory=threading.Lock)
    progress_lock: threading.Lock = field(default_factory=threading.Lock)
    summary_lock: threading.Lock = field(default_factory=threading.Lock)
    done: int = 0

    def next_progress(self) -> int:
        with self.progress_lock:
            self.done += 1
            return self.done

    def add_summary(self, key: str) -> None:
        with self.summary_lock:
            self.summary[key] += 1

    def append_result(self, key: str, line: str) -> None:
        path = self.result_paths.get(key)
        if not path:
            return
        with self.file_lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as handle:
                handle.write(f"{line}\n")

    def emit(self, color: str, message: str) -> None:
        with self.print_lock:
            print(f"{color}{message}{RESET}", flush=True)


def parse_accounts(filepath: str) -> list[dict[str, str]]:
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
                    "totp_secret": parts[2].replace(" ", ""),
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


def proxy_label(proxy: Optional[str]) -> str:
    if not proxy:
        return "direct"
    return proxy.split("@")[-1] if "@" in proxy else proxy.replace("http://", "")


def token_preview(token: str, keep: int = 8) -> str:
    if not token:
        return "-"
    return f"{token[:keep]}..." if len(token) > keep else token


def setup_logger(base_dir: Path, timestamp: str) -> tuple[logging.Logger, Path]:
    logs_dir = base_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / f"{timestamp}.log"
    logger = logging.getLogger(f"meta_batch_{timestamp}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.handlers.clear()
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S"))
    logger.addHandler(handler)
    return logger, log_path


def make_result_paths(base_dir: Path, timestamp: str, command: str) -> dict[str, Path]:
    results_dir = base_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    paths = {"errors": results_dir / f"errors_{timestamp}.txt"}
    if command in {"login", "full"}:
        paths["tokens"] = results_dir / f"tokens_{timestamp}.txt"
    if command in {"get-pages", "full"}:
        paths["pages"] = results_dir / f"pages_{timestamp}.txt"
    if command in {"create-page", "full"}:
        paths["created"] = results_dir / f"created_{timestamp}.txt"
    return paths


def checkpoint_like(message: str) -> bool:
    lowered = (message or "").lower()
    return "checkpoint" in lowered or "verification" in lowered or "405" in lowered


def classify_login_failure(result: dict) -> tuple[str, str, str, str]:
    status = result.get("status")
    message = result.get("error_msg", "Unknown error")
    if status == "rate_limit":
        return "rate_limit", "🚫", YELLOW, message
    if status == "checkpoint" or checkpoint_like(message):
        return "checkpoint", "⚠️", YELLOW, message
    if status == "disabled":
        return "disabled", "❌", RED, message
    if status == "wrong_pass":
        return "wrong_pass", "❌", RED, message
    return "errors", "❌", RED, message


def classify_graph_failure(result: dict) -> tuple[str, str, str, str]:
    status = result.get("status")
    message = result.get("msg", result.get("error_msg", "Unknown error"))
    if status == "checkpoint" or checkpoint_like(message):
        return "checkpoint", "⚠️", YELLOW, message
    return "errors", "❌", RED, message


def finalize_failure(state: RunState, uid: str, summary_key: str, symbol: str, color: str, detail: str, error_message: str) -> None:
    state.add_summary(summary_key)
    state.append_result("errors", f"{uid}|{summary_key}|{error_message}")
    progress = state.next_progress()
    state.emit(color, f"[{progress}/{state.total}] {symbol} {uid} → {detail}")


def finalize_success(state: RunState, color: str, uid: str, detail: str) -> None:
    state.add_summary("success")
    progress = state.next_progress()
    state.emit(color, f"[{progress}/{state.total}] ✅ {uid} → {detail}")


def login_account(account: dict[str, str], proxy: Optional[str] = None) -> tuple[MetaBusinessAPI, dict]:
    client = MetaBusinessAPI(proxy=proxy)
    client.new_device_fingerprint(seed=account["uid"])
    return client, client.login(account["uid"], account["password"], account["totp_secret"])


def log_login_result(logger: logging.Logger, uid: str, proxy: Optional[str], result: dict) -> None:
    route = proxy_label(proxy)
    status = result.get("status")
    if status == "ok":
        logger.info("Login %s via %s → OK (token: %s)", uid, route, token_preview(result.get("access_token", "")))
    elif status == "checkpoint":
        logger.warning("Login %s via %s → CHECKPOINT (%s)", uid, route, result.get("error_msg", "Unknown error"))
    elif status == "rate_limit":
        logger.warning("Login %s via %s → RATE_LIMIT (%s)", uid, route, result.get("error_msg", "Unknown error"))
    elif status == "wrong_pass":
        logger.error("Login %s via %s → WRONG_PASS (%s)", uid, route, result.get("error_msg", "Unknown error"))
    elif status == "disabled":
        logger.error("Login %s via %s → DISABLED (%s)", uid, route, result.get("error_msg", "Unknown error"))
    else:
        logger.error("Login %s via %s → ERROR (%s)", uid, route, result.get("error_msg", "Unknown error"))


def fetch_user_info(client: MetaBusinessAPI, logger: logging.Logger, uid: str, access_token: str) -> dict:
    user_info = client.get_user_info(access_token)
    if user_info.get("error"):
        logger.error("GET /me %s → %s", uid, user_info.get("msg", "Unknown error"))
    else:
        logger.info("GET /me %s → %s", uid, user_info.get("name", ""))
    return user_info


def fetch_pages(client: MetaBusinessAPI, logger: logging.Logger, uid: str, access_token: str) -> dict:
    pages_result = client.get_pages(access_token)
    if pages_result.get("error"):
        logger.error("GET /me/accounts %s → %s", uid, pages_result.get("msg", "Unknown error"))
    else:
        logger.info("GET /me/accounts %s → %s page(s)", uid, len(pages_result.get("pages", [])))
    return pages_result


def create_page(client: MetaBusinessAPI, logger: logging.Logger, uid: str, access_token: str, owner_uid: str, page_name: str, category: str) -> dict:
    created = client.create_page(access_token, owner_uid, page_name, category)
    if created.get("error"):
        logger.error("Create page %s → %s", uid, created.get("msg", "Unknown error"))
    else:
        logger.info("Create page %s → OK", uid)
    return created


def process_login(state: RunState, account: dict[str, str], proxy: Optional[str]) -> None:
    uid = account["uid"]
    client, result = login_account(account, proxy=proxy)
    log_login_result(state.logger, uid, proxy, result)
    if result.get("status") != "ok":
        summary_key, symbol, color, message = classify_login_failure(result)
        finalize_failure(state, uid, summary_key, symbol, color, message, message)
        return

    access_token = result["access_token"]
    resolved_uid = str(result.get("uid") or uid)
    user_info = fetch_user_info(client, state.logger, uid, access_token)
    if user_info.get("error"):
        summary_key, symbol, color, message = classify_graph_failure(user_info)
        finalize_failure(state, uid, summary_key, symbol, color, message, message)
        return

    page_count = "?"
    pages_result = fetch_pages(client, state.logger, uid, access_token)
    if not pages_result.get("error"):
        page_count = str(len(pages_result.get("pages", [])))

    state.append_result("tokens", f"{resolved_uid}|{access_token}|{user_info.get('name', '')}")
    finalize_success(state, GREEN, uid, f"{user_info.get('name', '')} | Pages: {page_count} | Token: {token_preview(access_token)}")


def process_create_page(state: RunState, account: dict[str, str], proxy: Optional[str], page_name: str, category: str) -> None:
    uid = account["uid"]
    client, result = login_account(account, proxy=proxy)
    log_login_result(state.logger, uid, proxy, result)
    if result.get("status") != "ok":
        summary_key, symbol, color, message = classify_login_failure(result)
        finalize_failure(state, uid, summary_key, symbol, color, message, message)
        return

    access_token = result["access_token"]
    owner_uid = str(result.get("uid") or uid)
    user_info = fetch_user_info(client, state.logger, uid, access_token)
    owner_label = user_info.get("name", uid) if not user_info.get("error") else uid

    created = create_page(client, state.logger, uid, access_token, owner_uid, page_name, category)
    if created.get("error"):
        message = created.get("msg", "Unknown error")
        finalize_failure(state, uid, "errors", "❌", RED, message, message)
        return

    pages_result = fetch_pages(client, state.logger, uid, access_token)
    if pages_result.get("error"):
        summary_key, symbol, color, message = classify_graph_failure(pages_result)
        finalize_failure(state, uid, summary_key, symbol, color, message, message)
        return

    matched_page = next((page for page in pages_result.get("pages", []) if page.get("name") == page_name), None)
    if matched_page is None:
        message = f"Page created but token not found for {page_name}"
        state.logger.error("Create page %s → %s", uid, message)
        finalize_failure(state, uid, "errors", "❌", RED, message, message)
        return

    state.append_result(
        "created",
        f"{matched_page.get('id', '')}|{matched_page.get('name', '')}|{matched_page.get('access_token', '')}|{owner_uid}",
    )
    finalize_success(
        state,
        GREEN,
        uid,
        f"{owner_label} | Created: {matched_page.get('name', '')} | Page ID: {matched_page.get('id', '')} | Token: {token_preview(matched_page.get('access_token', ''))}",
    )


def process_get_pages(state: RunState, account: dict[str, str], proxy: Optional[str]) -> None:
    uid = account["uid"]
    client, result = login_account(account, proxy=proxy)
    log_login_result(state.logger, uid, proxy, result)
    if result.get("status") != "ok":
        summary_key, symbol, color, message = classify_login_failure(result)
        finalize_failure(state, uid, summary_key, symbol, color, message, message)
        return

    access_token = result["access_token"]
    user_info = fetch_user_info(client, state.logger, uid, access_token)
    owner_label = user_info.get("name", uid) if not user_info.get("error") else uid
    pages_result = fetch_pages(client, state.logger, uid, access_token)
    if pages_result.get("error"):
        summary_key, symbol, color, message = classify_graph_failure(pages_result)
        finalize_failure(state, uid, summary_key, symbol, color, message, message)
        return

    pages = pages_result.get("pages", [])
    owner_uid = str(result.get("uid") or uid)
    for page in pages:
        state.append_result(
            "pages",
            f"{owner_uid}|{page.get('id', '')}|{page.get('name', '')}|{page.get('access_token', '')}|{page.get('category', '')}",
        )

    finalize_success(state, GREEN, uid, f"{owner_label} | Pages: {len(pages)}")


def process_full(state: RunState, account: dict[str, str], proxy: Optional[str], page_name: str, category: str) -> None:
    uid = account["uid"]
    client, result = login_account(account, proxy=proxy)
    log_login_result(state.logger, uid, proxy, result)
    if result.get("status") != "ok":
        summary_key, symbol, color, message = classify_login_failure(result)
        finalize_failure(state, uid, summary_key, symbol, color, message, message)
        return

    access_token = result["access_token"]
    owner_uid = str(result.get("uid") or uid)
    user_info = fetch_user_info(client, state.logger, uid, access_token)
    if user_info.get("error"):
        summary_key, symbol, color, message = classify_graph_failure(user_info)
        finalize_failure(state, uid, summary_key, symbol, color, message, message)
        return

    state.append_result("tokens", f"{owner_uid}|{access_token}|{user_info.get('name', '')}")

    created = create_page(client, state.logger, uid, access_token, owner_uid, page_name, category)
    if created.get("error"):
        message = created.get("msg", "Unknown error")
        finalize_failure(state, uid, "errors", "❌", RED, message, message)
        return

    pages_result = fetch_pages(client, state.logger, uid, access_token)
    if pages_result.get("error"):
        summary_key, symbol, color, message = classify_graph_failure(pages_result)
        finalize_failure(state, uid, summary_key, symbol, color, message, message)
        return

    pages = pages_result.get("pages", [])
    for page in pages:
        state.append_result(
            "pages",
            f"{owner_uid}|{page.get('id', '')}|{page.get('name', '')}|{page.get('access_token', '')}|{page.get('category', '')}",
        )

    matched_page = next((page for page in pages if page.get("name") == page_name), None)
    if matched_page is None:
        message = f"Page created but token not found for {page_name}"
        state.logger.error("Create page %s → %s", uid, message)
        finalize_failure(state, uid, "errors", "❌", RED, message, message)
        return

    state.append_result(
        "created",
        f"{matched_page.get('id', '')}|{matched_page.get('name', '')}|{matched_page.get('access_token', '')}|{owner_uid}",
    )
    finalize_success(
        state,
        GREEN,
        uid,
        f"{user_info.get('name', '')} | Pages: {len(pages)} | Token: {token_preview(access_token)} | Created: {matched_page.get('id', '')}",
    )


def process_account(state: RunState, account: dict[str, str], proxy: Optional[str], args: argparse.Namespace) -> None:
    try:
        if state.command == "login":
            process_login(state, account, proxy)
        elif state.command == "create-page":
            process_create_page(state, account, proxy, args.name, args.category)
        elif state.command == "get-pages":
            process_get_pages(state, account, proxy)
        elif state.command == "full":
            process_full(state, account, proxy, args.name, args.category)
        else:
            raise ValueError(f"Unsupported command: {state.command}")
    except Exception as exc:
        uid = account["uid"]
        state.logger.exception("Unhandled exception for %s", uid)
        finalize_failure(state, uid, "errors", "❌", RED, str(exc), str(exc))


def build_lanes(accounts: list[dict[str, str]], proxies: list[str], thread_count: int) -> list[list[tuple[dict[str, str], Optional[str]]]]:
    lane_count = max(1, min(thread_count, len(accounts)))
    lanes: list[list[tuple[dict[str, str], Optional[str]]]] = [[] for _ in range(lane_count)]
    for index, account in enumerate(accounts):
        proxy = proxies[index % len(proxies)] if proxies else None
        lanes[index % lane_count].append((account, proxy))
    return [lane for lane in lanes if lane]


def process_lane(lane: list[tuple[dict[str, str], Optional[str]]], state: RunState, args: argparse.Namespace) -> None:
    for offset, (account, proxy) in enumerate(lane):
        process_account(state, account, proxy, args)
        if state.delay > 0 and offset < len(lane) - 1:
            time.sleep(state.delay)


def print_summary(summary: dict[str, int], command: str, result_paths: dict[str, Path], log_path: Path) -> None:
    lines = [
        f" Total:      {summary['total']}",
        f" ✅ Success:  {summary['success']}",
        f" ⚠️  Checkpoint: {summary['checkpoint']}",
        f" 🚫 Rate limited: {summary['rate_limit']}",
        f" ❌ Disabled: {summary['disabled']}",
        f" ❌ Wrong pass: {summary['wrong_pass']}",
        f" ❌ Errors:   {summary['errors']}",
    ]
    width = max(len(" RESULTS SUMMARY "), *(len(line) for line in lines))
    print(f"{BOLD}{CYAN}╔{'═' * (width + 2)}╗{RESET}")
    print(f"{BOLD}{CYAN}║{' RESULTS SUMMARY '.center(width + 2)}║{RESET}")
    print(f"{BOLD}{CYAN}╠{'═' * (width + 2)}╣{RESET}")
    for line in lines:
        print(f"{BOLD}{CYAN}║{RESET} {line.ljust(width)} {BOLD}{CYAN}║{RESET}")
    print(f"{BOLD}{CYAN}╚{'═' * (width + 2)}╝{RESET}")

    print()
    print(f"{BOLD}Command:{RESET} {command}")
    print(f"{BOLD}Log file:{RESET} {log_path}")
    for key in ("tokens", "pages", "created", "errors"):
        if key in result_paths:
            print(f"{BOLD}{key.title()}:{RESET} {result_paths[key]}")


def add_common_args(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument("--file", required=True, help="Path to accounts file")
    subparser.add_argument("--proxy-file", default="proxies.txt", help="Path to proxies file (default: proxies.txt)")
    subparser.add_argument("--threads", type=int, default=5, help="Number of worker threads (default: 5)")
    subparser.add_argument("--delay", type=float, default=1.0, help="Delay in seconds between accounts per thread (default: 1.0, recommend: 2.0)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Meta Business Suite API Research Tool")
    subparsers = parser.add_subparsers(dest="command", required=True)

    login_parser = subparsers.add_parser("login", help="Log in accounts and save tokens")
    add_common_args(login_parser)

    create_page_parser = subparsers.add_parser("create-page", help="Create a page for each account")
    add_common_args(create_page_parser)
    create_page_parser.add_argument("--name", required=True, help="Page name to create")
    create_page_parser.add_argument("--category", default="2200", help="Page category ID (default: 2200)")

    get_pages_parser = subparsers.add_parser("get-pages", help="Fetch pages for each account")
    add_common_args(get_pages_parser)

    full_parser = subparsers.add_parser("full", help="Run login, create-page, and get-pages flow")
    add_common_args(full_parser)
    full_parser.add_argument("--name", required=True, help="Page name to create")
    full_parser.add_argument("--category", default="2200", help="Page category ID (default: 2200)")

    return parser


def validate_args(args: argparse.Namespace) -> None:
    if args.threads < 1:
        raise ValueError("--threads must be >= 1")
    if args.delay < 0:
        raise ValueError("--delay must be >= 0")


def run_command(args: argparse.Namespace) -> None:
    validate_args(args)
    accounts = parse_accounts(args.file)
    if not accounts:
        raise ValueError("No valid accounts found in input file")

    base_dir = Path.cwd()
    result_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    logger, log_path = setup_logger(base_dir, log_stamp)
    result_paths = make_result_paths(base_dir, result_stamp, args.command)

    state = RunState(
        command=args.command,
        total=len(accounts),
        delay=args.delay,
        logger=logger,
        result_paths=result_paths,
    )
    state.summary["total"] = len(accounts)

    proxies = load_proxies(args.proxy_file)
    lanes = build_lanes(accounts, proxies, args.threads)
    logger.info(
        "Starting command=%s accounts=%s threads=%s delay=%s proxies=%s",
        args.command,
        len(accounts),
        len(lanes),
        args.delay,
        len(proxies),
    )

    with ThreadPoolExecutor(max_workers=len(lanes)) as pool:
        futures = [pool.submit(process_lane, lane, state, args) for lane in lanes]
        for future in as_completed(futures):
            future.result()

    logger.info("Completed command=%s summary=%s", args.command, state.summary)
    print_summary(state.summary, args.command, result_paths, log_path)
    for handler in logger.handlers[:]:
        handler.close()
        logger.removeHandler(handler)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    run_command(args)


if __name__ == "__main__":
    main()
