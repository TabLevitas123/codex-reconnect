# Codex reconnect

A local floating ON/OFF control for resuming a stalled Codex CLI goal. When
connectivity and readiness allow, it activates the bound terminal, types
`/goal resume`, and presses Enter. It starts OFF.

The helper is an ordinary Python program. It runs no agent or model and uses
no API credentials. Its connectivity checks use unauthenticated HTTPS.

Project: [TabLevitas123/codex-reconnect](https://github.com/TabLevitas123/codex-reconnect).

The current implementation passes 70 focused tests. Independent review covers
the recovery fix for stale busy indicators and the exact `request timed out`
failure. The helper activates the terminal even when it already has focus.
`Waiting: Codex is working` refers to ongoing work, not a selected input field.
An actual X11 fixture verified command typing and Enter. A further [watcher-to-X11 fixture](docs/testing.md#joined-watcher-to-x11-fixture)
passed one run using scripted connectivity and a virtual clock. The production
watcher decision reached the real keyboard adapter and sent one command and
Enter to an owned window. Independent runtime review passed in this bounded fixture scope. Recovery
through a natural outage into a live Codex continuation remains unverified.

## Supported setup

Ubuntu with an X11 GNOME desktop and a single-tab GNOME Terminal window.
The observer targets the Codex CLI 0.159.2 layout and local SQLite schema.
Other terminals, Wayland and future CLI layouts have not been qualified.

Use the system Python with Tk, PyGObject, AT-SPI and Python Xlib. The external
commands are `curl`, `wmctrl` and `xdotool`. GNOME's Mutter idle monitor is
preferred; `xprintidle` is an optional fallback.

Typical Ubuntu dependencies:

```bash
sudo apt install python3-tk python3-gi gir1.2-atspi-2.0 python3-xlib curl wmctrl xdotool
```

## Try it

From the repository directory:

```bash
/usr/bin/python3 scripts/codex_reconnect_toggle.py --help
/usr/bin/python3 scripts/codex_reconnect_toggle.py --fixture
```

The fixture sends keys only to its own dummy text window. It executes no
command and does not access Codex or the network.

For a live terminal, first identify and manually verify the exact window,
thread, foreground TUI process, backend process and TTY. Follow
[usage](docs/usage.md) before passing `--qualify-target`.

The helper checks offline connectivity every thirty seconds and keeps pending
same-goal recovery until safe or cancelled. It also handles allowlisted typed
transient failures and qualified active-idle incidents. It protects observed
pauses, limits, completion, drafts and approval states. Unknown errors stay
blocked. See [design and limits](docs/design.md).

A "Sent /goal resume" label confirms keyboard delivery only. It does not prove
that Codex continued. The helper cannot promise perfect draft safety on X11.

## Development

```bash
/usr/bin/python3 tests/test_codex_reconnect_toggle.py
```

See [testing](docs/testing.md) for automated coverage and manual acceptance,
and [changes](CHANGELOG.md) for the initial behavior.
