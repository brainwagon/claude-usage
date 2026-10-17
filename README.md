# Claude Usage Tray

A tiny macOS menu bar widget that shows how much of your Claude Code plan
limits you've used and when they reset.

The menu bar shows Clawd followed by your usage:

![The widget in the menu bar: Clawd, then "S 5% · W 77%"](screenshot.png)

- **S** is your 5-hour session limit.
- **W** is your weekly limit.

Click it for the details:

```
Session (5h): 5% used
    resets 10:39 AM  (in 2h 33m)
Weekly: 77% used
    resets Tue 9:59 AM  (in 3d 1h)
───
Updated 8:06 AM
Refresh now
Quit
```

## Requirements

- macOS
- Python 3 with [`rumps`](https://github.com/jaredks/rumps) (`pip3 install rumps`,
  which also installs PyObjC)
- Claude Code, signed in with a Claude subscription (the widget uses its login)

## Running it

```sh
python3 claude_usage_tray.py &
```

It runs in the menu bar only, with no Dock icon. Choose **Quit** from its menu
to stop it.

### Starting at login

To have the widget start when you log in, install a LaunchAgent. Run this from
the project folder (launchd doesn't expand `~` or `$HOME`, so the command fills
in your full paths):

```sh
PYTHON=$(command -v python3)   # must be the Python you installed rumps into
cat > ~/Library/LaunchAgents/com.claude-usage-tray.plist <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.claude-usage-tray</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON</string>
        <string>$PWD/claude_usage_tray.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardErrorPath</key>
    <string>$HOME/Library/Logs/claude-usage-tray.log</string>
</dict>
</plist>
EOF
launchctl load ~/Library/LaunchAgents/com.claude-usage-tray.plist
```

This starts the widget right away and at every login. Errors are written to
`~/Library/Logs/claude-usage-tray.log`.

Choosing **Quit** stops the widget until your next login. To start it again
right away, run `launchctl start com.claude-usage-tray`. To stop it starting at
login, unload the file and delete it:

```sh
launchctl unload ~/Library/LaunchAgents/com.claude-usage-tray.plist
rm ~/Library/LaunchAgents/com.claude-usage-tray.plist
```

## How it works

1. It reads the login token Claude Code stores in your macOS Keychain (the
   `Claude Code-credentials` item). You don't sign in separately.
2. Every 5 minutes it asks `https://api.anthropic.com/api/oauth/usage` for your
   usage, the same lookup Claude Code's `/usage` command does.
3. Every 30 seconds it updates the countdowns in the menu.

Checking usage doesn't run Claude, so the widget doesn't use up any of your
limits.

Clawd is drawn in code from the same block-character art Claude Code shows on
its startup screen, so there's no image file.

## Settings

These are constants near the top of `claude_usage_tray.py`:

| Setting          | Default | What it does                          |
| ---------------- | ------- | ------------------------------------- |
| `POLL_SECONDS`   | `300`   | How often to fetch usage from the API |
| `RENDER_SECONDS` | `30`    | How often to update the countdowns    |
| `CLAWD_RGB`      | orange  | Clawd's color                         |

To make Clawd bigger or smaller, change the default sizes in `clawd_image()`.

## Troubleshooting

- **"Login expired — run `claude` to refresh"**: the stored login token has
  expired. Run `claude` once and it renews the token. The widget never renews
  it itself, so that it can't interfere with Claude Code's saved login.
- **An "HTTP" error**: the usage endpoint isn't officially documented, so
  Anthropic may change or remove it. If that happens, the widget will need
  updating.
- **The menu bar shows `?`**: the widget hasn't fetched usage successfully yet.
  The menu shows the error, if there is one.
