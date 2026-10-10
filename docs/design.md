# Design and limits

`ReconnectCycle` debounces network observations. `Controller` holds pending
intent, readiness debounce, cooldown and incident deduplication. `LiveObserver`
reads the qualified desktop and local metadata. `X11Actuator` performs the
bounded keyboard effect. Tests replace the observer and actuator with local
fixtures; production needs no LLM or API connection.

## Connectivity and recovery ownership

Two HTTPS endpoints check DNS, TLS and HTTP: Google's `generate_204` and
Cloudflare's `cdn-cgi/trace`. Each probe has a two-second total timeout.
Expected responses from both mean online; two failures mean offline;
disagreement means unknown. Curl ignores configuration, proxies and redirects,
sends no credentials and discards response bodies. These endpoints do not
prove that the model provider is reachable.

Offline probes run every thirty seconds; online or unknown probes are due
every two seconds. Network debounce requires six-second outage and recovery
periods. Unknown samples or a long gap reset debounce. Already pending
same-goal recovery survives them and waits for verified connectivity.

An active goal observed online establishes the baseline. A different goal
clears old ownership and pending intent. A change observed offline cannot
inherit old recovery. Observed pauses, limits, completion and unknown goal
statuses latch protection for that goal. Reobserving it as active or toggling
OFF/ON does not clear protection.

## Eligible stalls

The observer selects the latest overall turn by rollout order, never merely
the latest failed or completed turn. It reads SQLite in read-only mode.

| Latest turn and goal | Eligibility |
| --- | --- |
| Completed turn, active goal | Can qualify after thirty seconds of continuously safe idle observations. |
| Failed turn with an allowlisted typed transient | Can qualify after three seconds of consistent readiness with the same online baseline. |
| Newer in-progress turn | Blocks, even if the goal still reports blocked. |
| Interrupted turn, unknown error or missing metadata | Blocks. |
| Paused, limited, complete or protected goal | Blocks. |

Allowed transient types are `serverOverloaded`, `flexUnavailable`,
`internalServerError`, `httpConnectionFailed`, `responseStreamConnectionFailed`,
`responseStreamDisconnected` and `responseTooManyFailedAttempts`. Connection
variants with HTTP 4xx status remain blocked, including 429. A misalignment
marker blocks eligibility. Authentication, quota, rate limits, safety/refusal,
context limits and generic `other` errors do not qualify.
Three exact messages may qualify when Codex labels the failure `other`:
`request timed out`,
`stream disconnected before completion: Transport error: timeout`, and
`Error running remote compact task: stream disconnected before completion: Transport error: timeout`.
Matches are case-sensitive and accept no prefix, suffix or additional
diagnostic details. Generic `other` errors stay blocked.

Queue entries, deferred continuation, visible modal/approval states and drafts
still block typing. A typed failure alone is insufficient. Each goal/turn
incident gets one attempt, with a sixty-second cooldown across sends and
OFF/ON. A known zero-input deferral retains pending intent for another safe
attempt after cooldown. Partial input and unknown effect outcomes stay consumed
because automatic retyping could duplicate input.

## Target and input checks

Initial manual qualification associates the window with the thread and TTY.
Continuous checks pin process start times, executable, foreground TTY, backend
thread files, GTK window identity and the original accessible tab and terminal.
Exactly one tab and one terminal must remain. This proves original-widget
continuity; GNOME Terminal exposes no native accessible PID/TTY association.

AT-SPI terminal text is read only in memory. A recognized empty placeholder,
caret position and footer must match. GPT footer names allow either case;
composer input and `/goal resume` remain case-sensitive. Busy, reconnecting,
modal and explicit-stop indicators block. Mutter's idle monitor requires
thirty seconds without desktop input before activation and typing.

Before each effect, the adapter checks ON generation and fresh readiness.
It activates the target, checks focus, types the exact command, and waits up
to one second for its reflection. Only the unchanged placeholder or an owned
command prefix may wait. Changed input remains unsubmitted. Before Enter it
checks exact command ownership, focus, goal identity and the other guards.
Synthetic typing changes desktop idle, so this final check does not demand a
second thirty-second idle period. Old focus is restored only if still valid.

## Acceptance limits

X11 permits other clients to inject input. Events can race the final checks.
Hidden drafts or drafts identical to a placeholder cannot be ruled out
perfectly. A same-widget thread switch inside the TUI is not independently
proven by terminal metadata. Keep the qualified session selected.

The observer depends on the CLI layout and SQLite schema. Unknown or changed
observations block. Wayland, multiple terminal tabs, other terminal emulators,
crashed sessions and unattended login recovery are unsupported.

"Sent /goal resume" confirms the keyboard sequence. It does not verify a new
Codex turn. Automated tests and a dummy keyboard fixture do not establish
actual CLI continuation after a real outage.
