# Codex reconnect

A local floating ON/OFF control for resuming a stalled or unexpectedly paused Codex CLI goal. When
connectivity and readiness allow, it activates the bound terminal, types
`/goal resume`, and presses Enter. It starts OFF.

The helper is an ordinary Python program. It runs no agent or model and uses
no API credentials. Its connectivity checks use unauthenticated HTTPS.

Project: [TabLevitas123/codex-reconnect](https://github.com/TabLevitas123/codex-reconnect).

The current candidate passes 97 focused tests, including paused-goal recovery and ACTIVE verification. Terminal accessibility checks
match the GTK bus owner's process before comparing window geometry. Unrelated
applications with the same bounds no longer interrupt command delivery.
An owned blocked goal can qualify when its latest turn failed with an unfamiliar ordinary technical error. Recovery no longer depends only on exact transport messages. Limits, approvals, security or refusal states, authentication, quota, context limits and ambiguous needed-user decisions remain protected. ON also authorizes same-goal PAUSED/interrupted recovery after an observed active baseline. The schema has no pause reason, so accidental and deliberate Escape cannot be distinguished. Use OFF before an intentional stop. Visible stop commands still block input.

Allowlisted transport failures can retry on new failed turns with a delay that grows from sixty seconds to five minutes. Unfamiliar ordinary failures stop after two consecutive automatic attempts until a new safe completed active turn or explicit OFF/ON rearm. Incident deduplication and all readiness guards still apply. Read [design and limits](docs/design.md) for the exact boundary.

Independent source review passed all 89 tests. The corrected source passed an
owned X11 fixture from an unfocused target, delivering exactly one `/goal resume`
and Enter, restoring the companion's focus and closing both owned windows in
1.99951 seconds. The fixture used scripted connectivity and synthetic metadata.
The installed helper then recognized its live terminal and displayed
`ON. Waiting: Codex is working`. See [verification](docs/enter-verification.json).
Natural automatic live continuation remains unverified. Earlier verification
records remain tied to their recorded source revisions.

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
same-goal recovery until safe or cancelled. It also handles qualified blocked technical failures, allowlisted typed
transients and active-idle incidents. It protects observed
unowned pauses, limits, completion, drafts and approval states. Ambiguous stops stay
blocked. See [design and limits](docs/design.md).

The control distinguishes unrecognized composer content, an unverified caret and
an unfamiliar footer without recording their text. Previously verified
same-goal recovery ownership survives unknown connectivity. A "Sent /goal resume"
label confirms keyboard delivery only. A later "Verified: goal is ACTIVE" label requires fresh same-target, same-goal ACTIVE metadata. ACTIVE status alone does not prove a new turn or useful progress. The helper cannot promise perfect draft safety on X11.

## Development

```bash
/usr/bin/python3 tests/test_codex_reconnect_toggle.py
```

See [testing](docs/testing.md) for automated coverage and manual acceptance,
and [changes](CHANGELOG.md) for the initial behavior.
