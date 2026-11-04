# Changelog

## 2026-11-04: bounded command-caret reflection candidate

- Wait within the existing one-second deadline when the exact owned command
  appears with a caret still inside that prompt. A matching end caret and all
  submission guards remain required before one Return. A persistently moved
  caret times out; foreign input and unknown layouts still block immediately.
- Record fixed composer reason codes and Boolean reflection state without text.
- Pass 116 tests and an isolated actual Codex/X11 submission with one injected
  stale-caret snapshot, one Return and a CLI acknowledgment. The unchanged
  baseline also submitted successfully. Historical diagnostics confirm a
  pre-Enter reflection refusal but did not capture its exact parser subreason.
- Independently reviewed and installed, then enabled as an explicit fresh
  rearm. Fresh live checks show the CLI busy with no command or Return requests.
  Private counters did not transfer. Natural continuation remains unverified. See
  [verification](docs/caret-reflection-verification.json).

## 2026-11-03: exact Bad Request and Codex 0.166 footer recovery

- Recognize the exact `{"detail":"Bad Request"}` failure when metadata says
  `other`, has no additional details or misalignment, and the goal remains
  ACTIVE. Treat it as an ordinary stall with the existing two-attempt cap,
  incident deduplication and readiness guards. Other HTTP 400 errors remain
  unqualified.
- Accept the anchored Codex 0.166 agent-navigation footer with its optional
  warning count and `f2 to view` hint. Unknown footer content still blocks.
- Pass 113 synthetic tests and independent review. Install the reviewed source,
  replace a stale backend binding with a verified same-thread backend, and
  observe ON waiting for the busy CLI with zero action requests. Natural
  automatic continuation remains unverified.
- Restart as an explicit fresh rearm. Private in-memory incident and attempt
  counters cannot transfer; retain old logs, launcher backups and installed
  versions for rollback.

## 2026-10-18: paused recovery candidate

- Let ON recover a previously observed active goal after PAUSED/interrupted
  metadata, with all target, draft, readiness and retry guards.
- Keep startup pauses and other protected states blocked. Explain visibly
  that the schema has no pause reason and OFF preserves an intentional stop.
- Verify fresh same-target, same-goal ACTIVE metadata after keyboard delivery.
  Report an unverified result after fifteen seconds without that observation.
- Add synthetic observer/controller and verification regressions. Live
  activation and natural recovery remain unverified for this candidate.

## 2026-10-14: Enter delivery after an accessibility collision

- Match the accessible application's process to the GTK bus owner before
  selecting its window by geometry. Missing owners and duplicate frames still
  block. Draft, pause, approval and refusal checks remain intact.
- Reproduce typing without Enter when an unrelated frame appears at the same
  geometry. Pass all 89 focused tests and independent source review.
- Pass the updated owned X11 fixture with one command and Enter, restored
  focus and both-window cleanup in 1.99951 seconds. Install the corrected
  helper and confirm it recognizes the live terminal while Codex is working.
  Synthetic fixture metadata does not prove natural automatic continuation.
  See [verification](docs/enter-verification.json).

## 2026-10-13: ownership retention and composer diagnostics

- Retain a previously verified same-goal baseline through unknown connectivity;
  keep clearing it on goal changes. The regression failed before the fix.
- Report content, caret and footer blockers without recording their text or
  weakening draft checks. The historical draft blocker remains unexplained.
- Pass all 86 focused tests and refresh the owned X11 fixture source pin.
  Its new `--baseline-loss` scenario passed real keyboard delivery from an
  unfocused window after one preserved initial-focus failure. Independent
  review passed. Natural automatic Codex continuation remains unverified.

## 2026-10-12: repeated timeout recovery

- Keep retrying new recognized transport failures with capped backoff instead
  of stopping after two attempts. Preserve the ordinary-failure limit.
- Report retry limits and backoff accurately in transition diagnostics.
- Allow an online fresh monitoring cycle to adopt its first already blocked
  goal only when the latest turn has a recognized transport failure.
- Close that startup allowance after a goal change. Preserve drafts, pauses,
  approval boundaries, budgets and incident deduplication.

## 2026-10-07: stalled-turn recovery

- Ignore historical busy hints preceding a terminal transport error while
  preserving newer activity checks.
- Recognize the exact generic timeout diagnostic reported by the checked CLI.
- Clarify the busy label as `Waiting: Codex is working`.
- Verify activation of an already-focused target. The suite has 70 passing
  tests; the corrected watcher also passed one owned X11 integration run.
- Natural automatic recovery into a live Codex continuation remains unverified.

## Unreleased

- Add blocked-goal recovery for a latest failed ordinary technical error without requiring exact transport wording. Preserve explicit stops, ambiguous decisions and existing readiness guards.
- Cap consecutive automatic attempts at two, with explicit OFF/ON or a new safe completed active turn rearm. Keep protected goals, cooldown and consumed incidents.
- Preserve warning transport boundaries while ending stale activity at the latest terminal failure. All 78 focused tests pass.
- Verify the owned unfocused target route: activation, one command/Enter, old-focus restoration and both-window cleanup in 1.9395 seconds. Scripted connectivity does not establish natural automatic live continuation.

- Recognize only the exact observed remote-compaction network decoding failure reported as `other`, with no additional details or misalignment. The joined regression failed before the fix; all 73 focused tests now pass.
- Rebind the owned watcher-to-X11 fixture to the corrected source and this failure signature. The updated fixture passed one owned X11 run; independent review passed all 73 tests. Root manually resumed the live goal after restarting the corrected helper. Natural automatic live continuation remains unverified.

- Add a joined watcher-to-X11 fixture. One scripted-connectivity run delivered
  exactly one `/goal resume` and Enter to its owned window after stable
  readiness, with no offline or duplicate dispatch. Its virtual clock does
  not prove a real outage or automatic Codex continuation. Independent runtime review
  passed in this bounded fixture scope.

Initial standalone local reconnect control:

- Floating dark ON/OFF window, OFF on launch, with a qualified X11 keyboard adapter.
- Thirty-second offline connectivity checks and persistent same-goal pending recovery.
- Allowlisted typed transient recovery and thirty-second qualified active-idle debounce.
- Goal-specific protection, incident deduplication and sixty-second send cooldown.
- Fresh target, draft, focus, queue and goal checks through typing and Enter.
- Bounded private transition diagnostics, an owned keyboard fixture and focused tests.

Actual Codex continuation after an outage still requires live acceptance.

- Bind readiness debounce and every keyboard effect to the same goal, turn
  incident and recovery kind. Reset readiness after gaps or unknown samples
  while retaining pending recovery.

- Recognize the exact known remote-compaction transport timeout when Codex
  reports it as `other`, while rejecting unrelated unknown errors.
