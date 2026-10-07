# Changelog

## Unreleased

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
