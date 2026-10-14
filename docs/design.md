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
same-goal recovery survives them and waits for verified connectivity. A previously
verified same-goal baseline also survives unknown connectivity before pending
recovery begins; a different goal still clears that baseline.

An active goal observed online establishes the baseline. At startup or after
OFF/ON, the first observed goal can also establish it while online if it is
blocked and its latest overall turn is a safely classified allowlisted
transport failure. Unfamiliar blocked failures require an observed active
baseline. Offline or unknown connectivity, newer in-progress turns, blocked
completed turns and protected goals cannot establish this startup baseline.
A different goal
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
| Blocked goal and latest failed turn with an ordinary technical error | Can qualify without exact transport wording, with three-second readiness debounce and all guards below. |
| Failed turn with an allowlisted typed transient | Can qualify after three seconds of consistent readiness with the same online baseline. |
| Newer in-progress turn | Blocks, even if the goal still reports blocked. |
| Interrupted turn, ambiguous stop or missing metadata | Blocks. |
| Paused, limited, complete or protected goal | Blocks. |

Allowed transient types are `serverOverloaded`, `flexUnavailable`,
`internalServerError`, `httpConnectionFailed`, `responseStreamConnectionFailed`,
`responseStreamDisconnected` and `responseTooManyFailedAttempts`. Connection
variants with HTTP 4xx status remain blocked, including 429. A misalignment
marker blocks eligibility. Authentication, quota, rate limits, safety/refusal,
context limits remain blocked. For an active goal, generic `other` errors still need one of the exact transport signatures below.
Four exact messages may qualify when Codex labels the failure `other`:
`request timed out`,
`stream disconnected before completion: Transport error: timeout`, and
`Error running remote compact task: stream disconnected before completion: Transport error: timeout`, and
`Error running remote compact task: stream disconnected before completion: Transport error: network error: error decoding response body`.
Matches are case-sensitive and accept no prefix, suffix or additional
diagnostic details. Other errors outside the blocked-goal ordinary-failure lane stay blocked.

Queue entries, deferred continuation, visible modal/approval states and drafts
still block typing. A typed failure alone is insufficient. Each goal/turn
incident gets one attempt, with at least a sixty-second cooldown across sends and
OFF/ON. Repeated allowlisted transport failures wait sixty, 120, 240 and then
300 seconds between consecutive attempts. A new failed turn is required for
each attempt; repeatedly observing the same failure cannot send again. A known zero-input deferral retains pending intent for another safe
attempt after cooldown. Partial input and unknown effect outcomes stay consumed
because automatic retyping could duplicate input.

## Target and input checks

Initial manual qualification associates the window with the thread and TTY.
Continuous checks pin process start times, executable, foreground TTY, backend
thread files, GTK window identity and the original accessible tab and terminal.
Exactly one tab and one terminal must remain. This proves original-widget
continuity; GNOME Terminal exposes no native accessible PID/TTY association.
Frame selection first requires the accessible application's process ID to
match the owner of the window's GTK bus connection. Geometry then identifies
the frame within that application. Missing owners and multiple matching
frames still block; unrelated applications cannot qualify by geometry alone.

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

## Blocked-goal failures and retries

The goal schema has status and budget fields but no stop reason. BLOCKED alone is insufficient. The new lane requires the latest overall turn to be FAILED with type `other`, a nonempty message, null additional details and null misalignment. Unfamiliar technical wording may qualify. Required input or decisions, approval, pause, limit, security, refusal, authentication, quota, context exhaustion and user-interruption wording block before failure eligibility. Missing or ambiguous metadata, interrupted turns, blocked completed turns and newer in-progress turns remain blocked. This does not make every error recoverable.

A terminal error boundary ends preceding historical activity, including the existing warning transport markers. Activity after the newest boundary still blocks. Rendering grants no eligibility by itself; goal and latest-turn metadata remain required.

Exact allowlisted transport signatures are classified before unfamiliar blocked-goal failures. These transport incidents can continue retrying on new failed turns with the capped backoff above. The controller permits at most two consecutive automatic dispatches per goal for other eligible stalls. A newly observed safe completed ACTIVE turn resets the counter once. Explicit OFF→ON also rearms it. Neither clears protected goals, consumed incidents or cooldown. Confirmed zero-input deferrals refund their charged incident once; uncertain or partial effects remain charged. Completed metadata does not prove useful work. The counter lives in the running helper and does not persist across a restart.

Transition diagnostics report `automatic_retry_limit` when the ordinary-failure
ceiling blocks a dispatch and `transient_retry_backoff` while transport retries
wait. A readiness value of `ready` alone does not establish that a dispatch
is due.

Composer diagnostics distinguish `composer_content_unrecognized`,
`composer_caret_mismatch`, `composer_footer_unrecognized`,
`composer_prompt_missing` and `composer_input_mismatch`. Labels describe the
failed check without exposing text. Unrecognized content or a footer mismatch
never qualifies as an empty draft.
