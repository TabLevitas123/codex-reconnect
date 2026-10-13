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

Allow the helper to observe the active goal while online. A freshly enabled
helper can also adopt its first observed blocked goal while online when the
latest turn is an allowlisted transport failure. Unfamiliar blocked failures
need a previously observed active baseline. Newer running turns and protected
goals remain ineligible. Offline HTTPS
checks run every thirty seconds. Readiness checks continue roughly every two
seconds, with bounded worker delays. Recovery waits through drafts, busy CLI
output and recent desktop input; it has no two-minute expiry.

A typed transient or qualified blocked technical failure needs three seconds of consistent readiness. An
active goal whose latest turn completed needs thirty seconds of safe idle
observations. Sends have at least a sixty-second cooldown. Recognized transport
failures on new failed turns wait sixty, 120, 240 and then 300 seconds between
consecutive attempts. Each goal/turn incident gets one attempt, except an
explicitly confirmed zero-input deferral. OFF, a goal
change or a protected goal state cancels pending recovery.

Two consecutive automatic attempts stop further retries for unfamiliar ordinary
failures and other eligible stalls. Recognized transport failures can continue
on new failed turns after the capped backoff, with all readiness guards still
required. Repeated observations of the same incident never cause another send.
A newly observed safe completed active turn or explicit OFF/ON rearms the
counter. Rearm does not clear protected goals, already consumed incidents or
the sixty-second cooldown. Confirmed zero-input deferrals do not spend an
attempt. The counter is local to the running helper.

The target may be behind other windows or unfocused. The adapter activates the qualified target before typing and restores the previous focus only while both identities and focus remain safe. An owned two-window fixture verified that route; it does not prove arbitrary desktop conditions.

After a successful send, check Codex for actual continuation. If input changes
after typing, the helper leaves the command unsubmitted. Inspect that input
yourself before editing or submitting it; the helper never clears it.

## Diagnose a blocked control

| Symptom | What to check |
| --- | --- |
| Target changed or unknown | Verify current IDs and the original single-tab terminal. Relaunch with a freshly qualified binding if the process or widget changed. |
| Composer busy | Codex may be working or reconnecting. The helper waits. A newer in-progress turn also blocks recovery. |
| Desktop recent input | Stop typing or moving input for thirty seconds before the effect. |
| Draft or unrecognized composer content | Preserve the input. Unsupported placeholders, clipped input and attachments defer. |
| Composer caret position unverified | Confirm the selected session and resolve the input position manually. The helper does not move or clear it. |
| Composer footer unrecognized | A changed layout cannot qualify as an empty draft. Preserve the input and report the layout change. |
| Goal needs resume false | The latest turn may be unknown, interrupted, protected or still running. Blocked alone is insufficient; the latest turn must be a safely classified terminal failure. |
| Protected goal | A pause, limit, completion or unknown goal status was observed. Protection does not clear automatically for that same goal. |
| Automatic retry limit | Inspect the repeated failure. Explicit OFF/ON rearms the counter but does not remove protection or incident deduplication. |
| Transient retry backoff | Wait for the capped delay. A new failed turn and safe readiness are required before another transport retry. |
| Recovery pending | Check connectivity and readiness. Pending intent survives unknown connectivity and observation gaps. |
| Command left unsubmitted or adapter failed | Inspect the bound terminal. Partial or uncertain input is not retried automatically. |

The program does not repair crashed terminals, expired authentication, quota,
safety refusals or ambiguous needed-user decisions. It does not restart Codex.

## Diagnostics and privacy

State changes go to `~/.local/state/codex-reconnect-toggle/transitions.jsonl`.
Rotation retains the current file and one `.jsonl.1` file, each capped at
64 KiB. The helper requests private directory and file permissions.

Records contain fixed event/reason codes, Boolean observations and elapsed
time. They omit terminal text, drafts, objectives, queue payloads, thread IDs,
window titles and credentials. Terminal text and typed error metadata are
examined in memory. Keep your launch command private if its binding arguments
identify a personal session. Review any diagnostic file before sharing it.
