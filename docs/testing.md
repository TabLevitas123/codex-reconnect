# Testing

## 2026-10-18: paused recovery candidate

All 97 focused tests pass. `git diff --check` passes.

New synthetic tests reproduce ACTIVE to PAUSED with an interrupted latest turn,
including separately updated goal and turn rows. Recovery dispatches once with
a verified same-goal baseline. Cold-start pauses, newer in-progress turns,
errors, drafts, changed identity, modal approvals, visible stop commands,
protected states, missing connectivity and budgets remain negative cases.

Joined observer/controller coverage also checks command delivery followed by
fresh ACTIVE metadata. Controller tests withhold verification for unchanged
PAUSED, BLOCKED, stale and unqualified observations, and cancel verification
on OFF or a different goal. These tests use private SQLite fixtures and mocked
keyboard effects. They do not prove live desktop delivery or natural recovery.

The reviewed source passed the owned X11 fixture with `--paused-goal` and
`--start-unfocused` in 2.3966 seconds. The production observer, controller and
keyboard adapter delivered exactly one `/goal resume` and Enter to the owned
text window. The fixture restored the companion's focus, closed both owned
windows after the external close guard passed, and joined its worker. Private
history remained unchanged. Connectivity, goal metadata and target observation
were synthetic. The ACTIVE acknowledgment used synthetic metadata after the
owned window received Enter, so it does not prove a native goal transition.

The reviewed helper was installed and enabled. Its fresh observation showed
`ON. Waiting: Codex is working`, verified online connectivity and
`composer_busy`, with no pending recovery or goal command sent while that turn
was running. Natural automatic live goal recovery remains unverified. See the
[portable verification receipt](paused-recovery-verification.json). Historical
results below remain tied to their recorded source revisions.

## 2026-10-14: Enter withheld after an accessibility collision

The 89-test suite includes a regression through the real terminal binding,
composer parser, observer and X11 actuator. An unrelated application's frame
appears at the target's geometry after typing. Against the previous source,
the adapter types once, withholds Enter and reports a changed goal because
the failed accessibility lookup returns unknown readiness. The corrected
lookup matches the GTK bus owner's process first and sends Enter once.

Missing or invalid owners and duplicate frames within the owner's application
still block. Original widget continuity and all existing draft, pause, approval,
refusal, incident and focus guards remain in effect. These tests use synthetic
AT-SPI objects and mocked keyboard effects. They do not prove natural recovery
or identify the exact cause of earlier sends whose diagnostics omitted the
actuator's refusal reason. A read-only desktop check reproduced the ambiguity
with the installed previous source. The candidate then found the original
terminal and recognized an empty composer while its turn was running. That
check sent no keys.

Independent review approved the exact source and passed all 89 tests. The
updated owned X11 fixture then passed in 1.99951 seconds from an unfocused
target. It received exactly one `/goal resume` and Enter, restored the
companion's focus, closed both owned windows after the close audit and joined
its worker. Connectivity, metadata and target observations were synthetic;
the keyboard adapter was the production implementation.

The corrected source was installed. A fresh helper observation showed
`ON. Waiting: Codex is working` and cleared the previous target identity error.
No goal command was sent while that turn was running. This establishes the
bounded keyboard route and live binding repair, without proving natural
automatic continuation. See the [portable receipt](enter-verification.json).

## 2026-10-13: ownership and composer diagnostics

All 86 focused tests pass. The joined observer/controller regression first
failed with zero dispatches instead of one after unknown connectivity discarded
a verified same-goal baseline. The fix retains that baseline; goal changes
still clear it. Composer diagnostics distinguish content, caret and footer
failures without recording text or changing empty-draft acceptance.

The earlier `draft_empty_false` log does not identify its underlying condition.
A later live read found an empty composer and a running turn. That read does
not establish the earlier cause or prove automatic continuation.

The current source pin is bound in the owned fixture. A desktop owner can
exercise the baseline-loss scenario in an unlocked X11 session:

```bash
/usr/bin/python3 tests/watch_to_x11_fixture.py --start-unfocused --baseline-loss --receipt /tmp/codex-reconnect-x11-result.json
```

The receipt path must not already exist. The fixture loads production source
relative to its checkout and verifies ownership before closing its windows.
An optional `--close-guard` must be the final argument. All remaining tokens
are executable/argument entries; the fixture appends a normalized hexadecimal
window ID and invokes them without a shell. For example:

```bash
/usr/bin/python3 tests/watch_to_x11_fixture.py --start-unfocused --baseline-loss --receipt /tmp/codex-reconnect-x11-result.json --close-guard /path/to/python /path/to/audit_protected_windows.py --check-close
```

On the project owner's desktop, supply the existing protected-window audit
command. It must pass for each owned window before destruction. Without this
option the fixture performs its own ownership check only.

The final candidate passed the owned X11 scenario in 2.133 seconds. Starting
behind a companion window, it activated the target, typed exactly
`/goal resume`, pressed Enter once, and restored the companion's focus.
Both owned windows closed after the explicit audit and the worker joined.
The first attempt failed before dispatch because no active X11 window was
available while GNOME quick settings was open. That failure was retained;
the same candidate passed after the popup was dismissed.

The fixture uses synthetic composer and SQLite inputs with the production
observer, controller and actuator. It does not qualify live GNOME/TTY
observation, provider recovery or actual Codex continuation. Independent
source and result reviews passed. See the [verification record](ownership-recovery-verification.json).
Historical results below remain tied to their earlier source revisions.

## Repeated timeout and startup recovery

The previous focused suite had 84 tests. It reproduces three distinct transport
failures through the production observer and controller, verifies continued
retries with capped backoff, and keeps ordinary failures limited to two attempts.
Startup cases cover an already blocked goal, offline and unknown connectivity,
protected states, and a goal switch followed by return to the original goal.
A goal switch closes startup adoption until a fresh monitoring cycle.

These checks use controlled time, private fixture databases and mocked keyboard
effects. They do not prove natural recovery after an actual network outage.

## Busy-indicator recovery fix

The earlier busy-indicator suite had 78 passing tests. New observer/controller regressions
first reproduced two missed-recovery mechanisms: an old interrupt hint before
a terminal error, and a failed turn whose exact message was `request timed out`.
A separate failing case covered the timeout's terminal display. The fixes
preserve refusal during genuine current activity, drafts, explicit pauses,
approval prompts and unrecognized failures.

The X11 adapter explicitly activates an already-focused target before typing.
One real watcher-to-X11 fixture run against the corrected source received
exactly `/goal resume` and one Enter in 1.722 seconds. It used an owned test
window and scripted connectivity. Automatic recovery into a live Codex turn
remains unverified. See [the bounded result](busy-recovery-verification.json).

## Automated tests

From the repository directory:

```bash
/usr/bin/python3 tests/test_codex_reconnect_toggle.py
```

The initial implementation has 67 passing tests, independently rerun during
source review. They use synthetic observations, mocked keyboard effects and
temporary SQLite fixtures. They do not send keys to
Codex, probe the live network or mutate a native goal.

Coverage includes network debounce, cold-start network behavior, OFF,
cooldown, drafts, focus and target changes, exact command reflection,
goal-specific protection, diagnostics deduplication and rotation, typed turn
eligibility, incident deduplication and zero-input versus uncertain outcomes.

The delayed-idle regression replays pending recovery at 7997.4 seconds,
continued deferral at 8117.8, and readiness at 8206.2. The previous default
120-second expiry loses pending recovery; the candidate retains it and makes
one mocked attempt. A production observer/controller test with a fake clock
checks offline probes at 0, 30 and 60 seconds and dispatch after restoration.
These tests reproduce mechanisms, not a real network outage.

## Owned keyboard fixture

In an unlocked X11 session:

```bash
/usr/bin/python3 scripts/codex_reconnect_toggle.py --fixture
```

Click the fixture's test button with an empty buffer. Confirm that it receives
exactly `/goal resume` and Enter and reports the adapter result. Click again
with the existing input present; it must preserve that input and defer.
You can also enter a draft before testing and confirm that it stays unchanged.
Close the owned fixture when done.

The fixture executes no command and accesses no live Codex state. It proves
the keyboard adapter path only. Its test button does not simulate the
production connectivity scheduler; the automated tests exercise that pipeline.

## Joined watcher-to-X11 fixture

The separate `tests/watch_to_x11_fixture.py` joins production turn eligibility,
observer readiness, connectivity scheduling and controller decisions to the
real X11 keyboard adapter. It uses private synthetic history and goal data,
one worker and one owned Tk window. The fixture sends no keys to Codex.

One desktop-owner run passed with exit code 0 in 1.859346 seconds. Scripted
connectivity produced offline probes at virtual seconds 2, 32 and 62. The
last probe restored connectivity. Stable readiness allowed one dispatch at
virtual second 66. The owned text window received exactly `/goal resume` and
one Enter. No input occurred while offline, and later observations through
virtual second 142 produced no duplicate dispatch, including after cooldown.
The worker joined and the owned window closed.

The clock advances virtually. This was not a real thirty-second outage.
Identity, goal, composer and idle inputs use fixture adapters; connectivity
is scripted. Production eligibility and readiness methods remain in use.
The run does not qualify the asynchronous UI queue, GNOME/TTY observation,
provider behavior, native goal mutation or natural automatic continuation.
The 67-test historical suite was not rerun for this joined fixture. Prior
adapter review and the separate manual live-command proof remain separate.
Independent runtime review passed in this bounded fixture scope. See the redacted
[watcher verification record](watch-to-x11-verification.json).

A desktop owner can run this bounded fixture in an unlocked X11 session.
Use a new private receipt path each time:

```bash
timeout --signal=TERM --kill-after=2s 30s /usr/bin/python3 tests/watch_to_x11_fixture.py --receipt "$XDG_RUNTIME_DIR/watch-to-x11-result.json"
```

## Live acceptance

A desktop owner must qualify the exact target according to [usage](usage.md).
Use a naturally occurring eligible incident. Do not deliberately disrupt
other sessions to create an outage.

Confirm that ON monitoring observes the intended active goal, that the
incident is eligible, and that pending recovery survives drafts or busy
output. Once safe and online, verify target activation, the literal command,
Enter and a subsequent Codex turn. Compare the bounded transition codes with
what happened in the terminal. Do not treat the send label as proof of
continuation.

Also verify that OFF cancels pending work and that unowned paused or limited goals,
drafts and newer in-progress turns cause no input. Actual acceptance should
record the CLI version and desktop setup without publishing personal session
bindings or terminal text.

## Recorded verification

On 2026-10-07, independent review checked the exact source and all 67 tests
passed. Three additional regressions reproduced and corrected incident
changes inheriting a previous debounce, observation gaps counting as stable
readiness, and changed incidents reaching keyboard dispatch.

Actual X11 tests delivered `/goal resume` and Enter to the owned fixture. A
nonempty buffer blocked repeat input. Read-only checks recognized the qualified
live terminal and refused input while Codex was working. No natural outage or
real goal continuation was induced. See [verification metadata](verification.json).

A further regression covers the exact remote-compaction transport timeout
reported as `other`, with negative checks for altered and protected messages.
An explicitly requested manual X11 submission of `/goal resume` changed the
real current goal from blocked to active. This proves the live command route,
not an automatic watcher trigger or natural outage recovery.

On 2026-10-10, a synthetic SQLite regression reproduced a missed recovery for
the exact message `stream disconnected before completion: Transport error: timeout`
with type `other`, null additional details and null misalignment. The real
composer parser, observer and controller returned no dispatch despite idle
input. Adding this complete message to eligibility produced one mocked dispatch.
All 72 tests passed. Altered messages, policy failures, additional details,
misalignment, newer in-progress turns, protected goals, paused or exhausted
goals, drafts, approvals and changed target identity still blocked input.
This verifies the local decision path. Independent review and automatic live
continuation for this incident remain unverified.

## Remote-compaction network decoding regression

On 2026-10-11, the exact failed-turn message was `Error running remote compact task: stream disconnected before completion: Transport error: network error: error decoding response body`, with type `other`, null additional details and null misalignment. The joined composer/SQLite observer/controller regression first returned no dispatch despite idle input. Adding only that complete message produced one mocked dispatch. All 73 focused tests passed.

The regression preserves blocking for newer in-progress turns, current activity, drafts, approvals, protected or paused goals, exhausted limits, changed target identity, altered messages and extra error details. A current in-progress turn still blocks recovery even when a previous turn has the newly recognized error.

The watcher-to-X11 fixture now pins the corrected source and uses this exact failure in its private synthetic history. Its current revision passed one root-owned X11 run with one command and Enter in 1.7792 seconds. The worker joined and the owned window closed. Independent source review passed all 73 focused tests. Earlier fixture results above remain historical evidence for their recorded source revisions. No natural outage or automatic live continuation is established by this update.

Root also restarted the corrected live helper, enabled monitoring and manually submitted the user-requested `/goal resume` through X11. The goal became active. This was a manual submission, not a natural automatic recovery. See [the compact verification record](network-decoding-verification.json).

## Blocked unfamiliar failure and unfocused target

The current 78-test suite adds blocked unfamiliar-error recovery, offline waiting, protected-stop falsifiers and the two-attempt circuit breaker. The blocked generic failure and warning-boundary cases each failed against their preserved prior candidate and passed after correction. Newer in-progress turns, current activity, drafts, approvals, identity changes, pauses and limits remain negative cases.

Independent source/test/fixture review passed. Root then ran the owned watcher-to-X11 fixture with `--start-unfocused`. An active baseline preceded scripted connectivity loss; failed synthetic metadata then reported BLOCKED with an unfamiliar ordinary technical error. Exactly one dispatch typed `/goal resume` and Enter into the target after production activation. The previous companion focus was restored and both owned windows closed. Real wall time was 1.9395 seconds. No keys went to a live Codex terminal in this fixture.

This proves the bounded unfocused keyboard route with scripted connectivity. It does not establish a natural outage, full live GNOME/TTY observation or automatic live continuation. Earlier results remain tied to their historical source revisions. See [the current compact verification](stall-recovery-verification.json).
