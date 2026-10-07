# Usage

Run the helper in the same unlocked X11 desktop session as Codex. Keep the
qualified GNOME Terminal window open with exactly one tab and one terminal.
No autostart or system service is installed by this program.

## Bind a live target

Identify the existing Codex TUI and its backend. Verify the exact thread in
that terminal and the TUI's foreground TTY. Do not use a child-agent thread,
a second backend connection or stale process IDs.

These local commands can help inspect the binding:

```bash
xdotool selectwindow
ps -eo pid,ppid,comm
readlink /proc/TUI_PID/fd/0
```

`xdotool selectwindow` waits for you to select the intended window. Replace
`TUI_PID` before running the last command. Process names alone do not identify
the correct thread. Establish the thread ID from your existing local Codex
session metadata and verify that the selected terminal displays that session.

Replace every placeholder in this launch example:

```bash
/usr/bin/python3 scripts/codex_reconnect_toggle.py \
  --thread-id THREAD_UUID \
  --window-id WINDOW_XID \
  --tui-pid TUI_PID \
  --backend-pid BACKEND_PID \
  --tty /dev/pts/TTY_NUMBER \
  --qualify-target
```

`--qualify-target` records your manual confirmation that this window contains
that thread and TTY. It does not discover the association. The helper checks
process start times, executable, foreground TTY, backend thread files and the
original terminal widget afterward. Its default Codex directory is
`~/.codex`; use `--codex-dir CODEX_DIRECTORY` for another directory.

## Operate the control

Click OFF to turn monitoring ON. Click ON to cancel monitoring and pending
effects. Closing the control disables it. Every launch starts OFF. The window
stays above other windows while its process runs.

Allow the helper to observe the active goal while online. Offline HTTPS
checks run every thirty seconds. Readiness checks continue roughly every two
seconds, with bounded worker delays. Recovery waits through drafts, busy CLI
output and recent desktop input; it has no two-minute expiry.

A typed transient failure needs three seconds of consistent readiness. An
active goal whose latest turn completed needs thirty seconds of safe idle
observations. Sends have a sixty-second cooldown. Each goal/turn incident gets
one attempt, except an explicitly confirmed zero-input deferral. OFF, a goal
change or a protected goal state cancels pending recovery.

After a successful send, check Codex for actual continuation. If input changes
after typing, the helper leaves the command unsubmitted. Inspect that input
yourself before editing or submitting it; the helper never clears it.

## Diagnose a blocked control

| Symptom | What to check |
| --- | --- |
| Target changed or unknown | Verify current IDs and the original single-tab terminal. Relaunch with a freshly qualified binding if the process or widget changed. |
| Composer busy | Codex may be working or reconnecting. The helper waits. A newer in-progress turn also blocks recovery. |
| Desktop recent input | Stop typing or moving input for thirty seconds before the effect. |
| Draft or unfamiliar layout | Preserve the draft. Resolve it manually. Unsupported placeholders, clipped input and attachments defer. |
| Goal needs resume false | The latest turn may be unknown, interrupted, protected or still running. A generic blocked goal is insufficient. |
| Protected goal | A pause, limit, completion or unknown goal status was observed. Protection does not clear automatically for that same goal. |
| Recovery pending | Check connectivity and readiness. Pending intent survives unknown connectivity and observation gaps. |
| Command left unsubmitted or adapter failed | Inspect the bound terminal. Partial or uncertain input is not retried automatically. |

The program does not repair crashed terminals, expired authentication, quota,
safety refusals or unknown failures. It does not restart Codex.

## Diagnostics and privacy

State changes go to `~/.local/state/codex-reconnect-toggle/transitions.jsonl`.
Rotation retains the current file and one `.jsonl.1` file, each capped at
64 KiB. The helper requests private directory and file permissions.

Records contain fixed event/reason codes, Boolean observations and elapsed
time. They omit terminal text, drafts, objectives, queue payloads, thread IDs,
window titles and credentials. Terminal text and typed error metadata are
examined in memory. Keep your launch command private if its binding arguments
identify a personal session. Review any diagnostic file before sharing it.
