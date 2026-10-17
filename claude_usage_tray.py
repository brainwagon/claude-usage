#!/usr/bin/python3
"""Menu bar widget showing Claude Code usage limits and reset times.

Reads the OAuth token Claude Code stores in the macOS Keychain and polls the
same usage endpoint that `/usage` uses. Requires `rumps` (pip install rumps).
"""
import json
import subprocess
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone

import rumps
from AppKit import NSBundle, NSColor, NSImage, NSRectFill

USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
KEYCHAIN_SERVICE = "Claude Code-credentials"
POLL_SECONDS = 300      # how often to hit the API
RENDER_SECONDS = 30     # how often to refresh countdowns

LABELS = {"session": "Session (5h)", "weekly_all": "Weekly", "weekly_opus": "Weekly Opus",
          "weekly_sonnet": "Weekly Sonnet"}
SHORT = {"session": "S", "weekly_all": "W"}

# Clawd, as drawn by Claude Code's startup banner. Terminal quadrant blocks
# are twice as tall as wide, so each cell is drawn 1pt wide by 2pt tall.
CLAWD = [
    "...############...",
    "...##.######.##...",
    ".################.",
    "...############...",
    "....#.#....#.#....",
]
CLAWD_RGB = (0xD9, 0x77, 0x57)


def clawd_image(px_w=1.0, px_h=2.0):
    w, h = len(CLAWD[0]) * px_w, len(CLAWD) * px_h
    img = NSImage.alloc().initWithSize_((w, h))
    img.lockFocus()
    NSColor.colorWithSRGBRed_green_blue_alpha_(*(c / 255 for c in CLAWD_RGB), 1.0).set()
    for r, row in enumerate(CLAWD):
        y = h - (r + 1) * px_h  # AppKit's origin is bottom-left
        for c, ch in enumerate(row):
            if ch == "#":
                NSRectFill(((c * px_w, y), (px_w, px_h)))
    img.unlockFocus()
    return img


def read_token():
    out = subprocess.run(
        ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
        capture_output=True, text=True, check=True).stdout
    return json.loads(out)["claudeAiOauth"]["accessToken"]


def fetch_usage():
    req = urllib.request.Request(USAGE_URL, headers={
        "Authorization": f"Bearer {read_token()}",
        "anthropic-beta": "oauth-2025-04-20",
        "User-Agent": "claude-usage-tray",
    })
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.load(resp)


def parse_limits(data):
    """Return [(kind, percent, resets_at datetime|None)]."""
    limits = data.get("limits")
    if limits:
        return [(l["kind"], l.get("percent") or 0, parse_time(l.get("resets_at")))
                for l in limits]
    # Fallback for the older response shape.
    out = []
    for key, kind in (("five_hour", "session"), ("seven_day", "weekly_all")):
        if data.get(key):
            out.append((kind, round(data[key]["utilization"] or 0),
                        parse_time(data[key].get("resets_at"))))
    return out


def parse_time(s):
    return datetime.fromisoformat(s) if s else None


def until(dt):
    secs = int((dt - datetime.now(timezone.utc)).total_seconds())
    if secs <= 0:
        return "now"
    d, rem = divmod(secs, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    if d:
        return f"{d}d {h}h"
    if h:
        return f"{h}h {m:02d}m"
    return f"{m}m"


def local_time(dt):
    local = dt.astimezone()
    fmt = "%-I:%M %p" if local.date() == datetime.now().date() else "%a %-I:%M %p"
    return local.strftime(fmt)


class UsageApp(rumps.App):
    def __init__(self):
        super().__init__("Claude", title=" …", quit_button=None)
        self._icon_nsimage = clawd_image()  # bypass rumps' forced 20x20 icon size
        self.data = None
        self.error = None
        self.updated = None
        self.lock = threading.Lock()
        self.refresh_now(None)
        rumps.Timer(lambda _: self.refresh_now(None), POLL_SECONDS).start()
        rumps.Timer(lambda _: self.render(), RENDER_SECONDS).start()

    def refresh_now(self, _):
        threading.Thread(target=self._fetch, daemon=True).start()

    def _fetch(self):
        try:
            data, error = fetch_usage(), None
        except urllib.error.HTTPError as e:
            data = None
            error = ("Login expired — run `claude` to refresh" if e.code == 401
                     else f"HTTP {e.code}")
        except Exception as e:  # network down, keychain locked, etc.
            data, error = None, str(e)[:80]
        with self.lock:
            if data is not None:
                self.data, self.updated = data, datetime.now()
            self.error = error
        # The render timer picks this up on the main thread.

    def render(self):
        with self.lock:
            data, error, updated = self.data, self.error, self.updated

        items = []
        if data:
            limits = parse_limits(data)
            parts = [f"{SHORT.get(k, k[0].upper())} {p}%" for k, p, _ in limits
                     if k in SHORT]
            self.title = " " + " · ".join(parts)
            for kind, pct, resets in limits:
                items.append(rumps.MenuItem(f"{LABELS.get(kind, kind)}: {pct}% used"))
                if resets:
                    items.append(rumps.MenuItem(
                        f"    resets {local_time(resets)}  (in {until(resets)})"))
            extra = data.get("extra_usage") or {}
            if extra.get("is_enabled"):
                items.append(rumps.MenuItem(
                    f"Extra usage: ${extra.get('used_credits', 0) / 100:.2f}"
                    f" of ${extra.get('monthly_limit', 0) / 100:.2f}"))
        else:
            self.title = " ?"

        items.append(None)
        if error:
            items.append(rumps.MenuItem(f"⚠︎ {error}"))
        if updated:
            items.append(rumps.MenuItem(f"Updated {updated.strftime('%-I:%M %p')}"))
        items.append(rumps.MenuItem("Refresh now", callback=self.refresh_now))
        items.append(rumps.MenuItem("Quit", callback=rumps.quit_application))

        self.menu.clear()
        self.menu = items


if __name__ == "__main__":
    # Hide the Python rocket from the Dock; live only in the menu bar.
    NSBundle.mainBundle().infoDictionary()["LSUIElement"] = "1"
    app = UsageApp()
    rumps.Timer(lambda t: (app.render(), t.stop()), 2).start()  # first paint after fetch
    app.run()
