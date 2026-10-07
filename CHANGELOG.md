# Changelog

## 2026-10-07: stalled-turn recovery

- Ignore historical busy hints preceding a terminal transport error while
  preserving newer activity checks.
- Recognize the exact generic timeout diagnostic reported by the checked CLI.
- Clarify the busy label as `Waiting: Codex is working`.
- Verify activation of an already-focused target. The suite has 70 passing
  tests; the corrected watcher also passed one owned X11 integration run.
- Natural automatic recovery into a live Codex continuation remains unverified.

## Unreleased

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
