r"""
Run PdaNetPC.exe every 2 minutes on Windows.

How to run manually
1. Install Python on Windows.
2. Save this file as `run_pdanet.py`.
3. Open Command Prompt or PowerShell.
4. Run: `python run_pdanet.py`
5. Stop it with `Ctrl+C`.

What it does
- Checks whether `PdaNetPC.exe` is already running.
- Starts it if it is not already running.
- Waits 2 minutes between checks/execution attempts.
- Prints a timestamped log line for each attempt.

Task Scheduler alternative
1. Open Task Scheduler.
2. Select "Create Task...".
3. On the General tab:
   - Give it a name such as `Run PdaNet Loop`.
   - Choose "Run only when user is logged on" if you want the app visible.
4. On the Triggers tab:
   - Add a trigger such as "At log on" or "At startup".
5. On the Actions tab:
   - Program/script: path to `python.exe`
   - Add arguments: full path to this script, for example:
     `"C:\path\to\run_pdanet.py"`
6. Save the task.

If you prefer Task Scheduler to launch PdaNet directly every 2 minutes instead of
running this script continuously:
1. Create a task for `C:\Program Files (x86)\PdaNet for Android\PdaNetPC.exe`
2. In Triggers, create a trigger and enable "Repeat task every: 2 minutes"
3. Set the duration to "Indefinitely"
"""

from __future__ import annotations

import datetime as dt
import os
import subprocess
import time


EXE_PATH = r"C:\Program Files (x86)\PdaNet for Android\PdaNetPC.exe"
PROCESS_NAME = "PdaNetPC.exe"
INTERVAL_SECONDS = 120


def log(message: str) -> None:
    timestamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}", flush=True)


def is_process_running(process_name: str) -> bool:
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {process_name}"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        log("`tasklist` was not found; skipping running-process check.")
        return False
    except Exception as exc:
        log(f"Failed to query running processes: {exc}")
        return False

    return process_name.lower() in result.stdout.lower()


def launch_pdanet() -> None:
    if not os.path.exists(EXE_PATH):
        log(f"Executable not found: {EXE_PATH}")
        return

    if is_process_running(PROCESS_NAME):
        log(f"{PROCESS_NAME} is already running; skipping launch.")
        return

    try:
        subprocess.Popen([EXE_PATH])
        log(f"Started {PROCESS_NAME}")
    except OSError as exc:
        log(f"Failed to launch {EXE_PATH}: {exc}")
    except Exception as exc:
        log(f"Unexpected error while launching {EXE_PATH}: {exc}")


def sleep_until_next_run(seconds: int) -> None:
    remaining = seconds
    while remaining > 0:
        time.sleep(min(1, remaining))
        remaining -= 1


def main() -> None:
    log("Starting PdaNet launcher loop. Press Ctrl+C to stop.")
    while True:
        log("Execution attempt started.")
        launch_pdanet()
        log(f"Waiting {INTERVAL_SECONDS} seconds before next attempt.")
        sleep_until_next_run(INTERVAL_SECONDS)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("Received Ctrl+C. Exiting gracefully.")
