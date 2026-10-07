# Testing

## Busy-indicator recovery fix

The current suite has 70 passing tests. New observer/controller regressions
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

Also verify that OFF cancels pending work and that paused or limited goals,
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
