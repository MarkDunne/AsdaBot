"""Browser-assisted login.

The user logs in through their own Chromium-based browser (dedicated
profile) launched with no automation flags — Cloudflare Turnstile rejects
logins while a CDP debugging port is open. Afterwards an invisible headless
instance reads the session cookies straight off the profile's disk; only
the SLAS refresh token matters, since the token refresh flow mints all
other credentials from it.
"""

import base64
import contextlib
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import httpx
from websockets.sync.client import connect

from asdabot.auth import refresh_tokens
from asdabot.config import (
    ASDA_BASE,
    CHROME_PROFILE_DIR,
    FALLBACK_STORE_ID,
    PROFILE_API_KEY,
    PROFILE_API_URL,
    ensure_config_dir,
    load_account,
    save_account,
)

SESSION_COOKIE_NAMES = ("SLAS.AUTH_TOKEN", "SLAS.REFRESH_TOKEN")

MAC_BROWSERS = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
]
LINUX_BROWSERS = [
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
    "microsoft-edge",
    "brave-browser",
]
WINDOWS_BROWSERS = [
    r"Google\Chrome\Application\chrome.exe",
    r"Microsoft\Edge\Application\msedge.exe",
    r"BraveSoftware\Brave-Browser\Application\brave.exe",
]


def find_browser() -> str | None:
    """Locate an installed Chromium-based browser binary."""
    if sys.platform == "darwin":
        candidates = MAC_BROWSERS
    elif sys.platform == "win32":
        roots = [
            os.environ.get("PROGRAMFILES", r"C:\Program Files"),
            os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
            os.environ.get("LOCALAPPDATA", ""),
        ]
        candidates = [str(Path(root) / rel) for root in roots if root for rel in WINDOWS_BROWSERS]
    else:
        return next((path for name in LINUX_BROWSERS if (path := shutil.which(name))), None)
    return next((path for path in candidates if Path(path).exists()), None)


def require_browser() -> str:
    exe = find_browser()
    if not exe:
        raise RuntimeError(
            "No Chromium-based browser found. Install Chrome, Edge, Brave, or Chromium."
        )
    return exe


class CDP:
    """Minimal Chrome DevTools Protocol client over a synchronous websocket."""

    def __init__(self, ws_url: str):
        self.ws = connect(ws_url, max_size=16 * 1024 * 1024)
        self.msg_id = 0

    def call(self, method: str, params: dict | None = None) -> dict:
        self.msg_id += 1
        self.ws.send(json.dumps({"id": self.msg_id, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(self.ws.recv(timeout=30))
            if msg.get("id") == self.msg_id:
                if "error" in msg:
                    raise RuntimeError(f"CDP {method}: {msg['error'].get('message', msg['error'])}")
                return msg.get("result", {})

    def close(self):
        with contextlib.suppress(Exception):
            self.ws.close()


def _popen(*args: str) -> subprocess.Popen:
    exe = require_browser()
    CHROME_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    # Fixed binary from the candidate list above, no shell, no user input.
    return subprocess.Popen(  # noqa: S603
        [
            exe,
            f"--user-data-dir={CHROME_PROFILE_DIR}",
            "--no-first-run",
            "--no-default-browser-check",
            *args,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def _shutdown(proc: subprocess.Popen):
    """Stop the browser and its helper processes (they outlive the main process)."""
    if sys.platform == "win32":
        taskkill = Path(os.environ.get("SYSTEMROOT", r"C:\Windows")) / "System32" / "taskkill.exe"
        subprocess.run(  # noqa: S603
            [str(taskkill), "/pid", str(proc.pid), "/T", "/F"], capture_output=True, check=False
        )
        return
    proc.terminate()
    with contextlib.suppress(subprocess.TimeoutExpired):
        proc.wait(timeout=5)
    with contextlib.suppress(ProcessLookupError):
        os.killpg(proc.pid, signal.SIGTERM)
    time.sleep(1)


def _session_cookies() -> dict[str, str]:
    """Read the ASDA session cookies off the login profile via an invisible browser."""
    port_file = CHROME_PROFILE_DIR / "DevToolsActivePort"
    port_file.unlink(missing_ok=True)

    proc = _popen("--headless=new", "--remote-debugging-port=0", "about:blank")
    for _ in range(100):
        if port_file.exists() and len(port_file.read_text().splitlines()) >= 2:
            break
        time.sleep(0.2)
    else:
        proc.terminate()
        raise RuntimeError("Browser did not expose a DevTools port.")

    port, ws_path = port_file.read_text().splitlines()[:2]
    browser = CDP(f"ws://127.0.0.1:{port}{ws_path}")
    try:
        raw = browser.call("Storage.getCookies").get("cookies", [])
        browser.call("Browser.close")
    finally:
        browser.close()
        with contextlib.suppress(Exception):
            proc.wait(timeout=10)

    return {
        c["name"]: c["value"]
        for c in raw
        if c.get("domain", "").endswith("asda.com") and c["name"] in SESSION_COOKIE_NAMES
    }


def _is_logged_in(cookies: dict[str, str]) -> bool:
    """True once the SLAS token belongs to a real customer.

    ASDA mints guest SLAS tokens (upn:Guest) on first page load, so cookie
    presence alone doesn't mean the user has logged in.
    """
    token = cookies.get("SLAS.AUTH_TOKEN", "")
    if not cookies.get("SLAS.REFRESH_TOKEN") or token.count(".") != 2:
        return False
    try:
        payload = json.loads(base64.urlsafe_b64decode(token.split(".")[1] + "=="))
    except (ValueError, json.JSONDecodeError):
        return False
    return "upn:Guest" not in payload.get("isb", "")


def _fetch_profile(adb2c_token: str) -> dict:
    """Fetch the ASDA customer profile (address, store) from the CRM API."""
    resp = httpx.get(
        PROFILE_API_URL,
        headers={
            "ocp-apim-subscription-key": PROFILE_API_KEY,
            "request_origin": "asdaNewCo_gi",
            "content-type": "application/json",
        },
        cookies={"ADB2C.AUTH_TOKEN": adb2c_token},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def _extract_profile(profile_response: dict) -> tuple[str, dict]:
    """Pull (store_id, delivery address) from the CRM profile response."""
    info = profile_response.get("profile", {}).get("additionalInfo", {})
    addresses = profile_response.get("addresses", [])
    addr = next((a for a in addresses if a.get("default")), addresses[0] if addresses else None)
    if not addr or not addr.get("line1"):
        raise LookupError("No delivery address on the ASDA account.")

    return info.get("cnc_store_id", FALLBACK_STORE_ID), {
        "address1": addr.get("line1", ""),
        "address2": addr.get("line2", ""),
        "city": addr.get("city", ""),
        "postcode": addr.get("postcode", "").replace(" ", ""),
        "latitude": addr.get("latitude", ""),
        "longitude": addr.get("longitude", ""),
        "address_type": addr.get("addressType", "House"),
        "crm_address_id": addr.get("crmAddressId", ""),
        "first_name": info.get("firstName", ""),
        "last_name": info.get("lastName", ""),
    }


def browser_login() -> dict:
    """Log in via a clean browser session, then read the session off disk."""
    ensure_config_dir()

    print("Opening a browser window for ASDA login...")
    print("Log in to your ASDA account, keeping 'Keep me signed in' ticked.\n")
    proc = _popen(ASDA_BASE)
    input("Press Enter here once you've logged in... ")
    _shutdown(proc)

    print("Capturing your session...")
    cookies = _session_cookies()
    if not _is_logged_in(cookies):
        raise RuntimeError(
            "No login found. Log in with 'Keep me signed in' ticked, then try again."
        )

    account = load_account() or {}
    account["tokens"] = {"slas_refresh": cookies["SLAS.REFRESH_TOKEN"]}
    save_account(account)
    account = refresh_tokens()  # mints all other tokens and proves the session works

    try:
        profile = _fetch_profile(account["tokens"]["adb2c_auth"])
        account["store_id"], account["address"] = _extract_profile(profile)
        save_account(account)
    except Exception as e:
        print(f"Warning: couldn't fetch your delivery address ({e}). Keeping existing details.")

    return account
