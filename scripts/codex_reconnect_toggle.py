#!/usr/bin/env python3
"""Floating local reconnect control with a bounded X11 resume adapter."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
import json
import math
import os
from pathlib import Path
import queue
import re
import shutil
import sqlite3
import subprocess
import threading
import time
from typing import Callable, Protocol


@dataclass(frozen=True)
class Target:
    thread_id: str
    window_id: str
    tui_pid: int
    start_ticks: str
    executable: str


@dataclass(frozen=True)
class Readiness:
    """A live bridge must supply every guard; unknown never means ready."""

    target: Target | None = None
    route_verified: bool | None = None
    draft_empty: bool | None = None
    idle: bool | None = None
    no_modal: bool | None = None
    no_explicit_pause: bool | None = None
    budget_available: bool | None = None
    recovery_owned: bool | None = None
    same_goal: bool | None = None
    goal_needs_resume: bool | None = None
    queue_empty: bool | None = None
    command_pending: bool = False
    composer_idle: bool | None = None
    desktop_idle: bool | None = None
    goal_id: str | None = None
    stall_kind: str | None = None
    incident_id: tuple | None = None

    def blocker(self, expected: Target) -> str | None:
        if self.target != expected:
            return "Target identity changed or unknown"
        for name in self.__dataclass_fields__:
            if name not in ("target", "command_pending", "composer_idle", "desktop_idle", "goal_id", "stall_kind", "incident_id") and getattr(self, name) is not True:
                if name == "idle" and self.idle is False:
                    if self.composer_idle is False:
                        return "Blocked: Codex composer busy"
                    if self.desktop_idle is False:
                        return "Blocked: desktop input within 30 seconds"
                return "Blocked: " + name.replace("_", " ")
        return None

    def reason_code(self, expected: Target) -> str:
        if self.target != expected:
            return "target_unknown_or_changed"
        for name in self.__dataclass_fields__:
            if name not in ("target", "command_pending", "composer_idle", "desktop_idle", "goal_id", "stall_kind", "incident_id"):
                value = getattr(self, name)
                if value is not True:
                    if name == "idle" and value is False:
                        if self.composer_idle is False:
                            return "composer_busy"
                        if self.desktop_idle is False:
                            return "desktop_recent_input"
                    return name + ("_unknown" if value is None else "_false")
        return "ready"


class TransitionDiagnostics:
    """Deduplicated enum/Boolean records, capped at two 64 KiB files."""

    def __init__(self, path: Path, max_bytes: int = 65536):
        self.path, self.max_bytes = path, max_bytes
        self.previous = None
        self.started = time.monotonic()
        self.lock = threading.Lock()

    def __call__(self, state: dict) -> None:
        with self.lock:
            self._record(state)

    def _record(self, state: dict) -> None:
        events = {"sample", "off", "on", "recovery_pending", "pending_expired",
                  "action_requested", "action_sent_unverified", "action_deferred", "action_failed"}
        phases = {"off", "watching", "outage_pending", "outage", "recovery_pending"}
        guards = {name for name in Readiness.__dataclass_fields__ if name not in
                  ("target", "command_pending", "composer_idle", "desktop_idle", "goal_id", "stall_kind", "incident_id")}
        reasons = {"ready", "target_unknown_or_changed", "composer_busy", "desktop_recent_input"}
        reasons |= {name + suffix for name in guards for suffix in ("_false", "_unknown")}
        record = {}
        for key, allowed in (("event", events), ("phase", phases), ("reason", reasons)):
            value = state.get(key)
            if isinstance(value, str) and value in allowed:
                record[key] = value
        for key in ("online", "pending", "sample_gap", "stale_observation", "composer_idle", "desktop_idle"):
            value = state.get(key)
            if value is None or type(value) is bool:
                record[key] = value
        if record == self.previous:
            return
        self.previous = dict(record)
        record["elapsed_seconds"] = round(time.monotonic() - self.started, 1)
        data = (json.dumps(record, sort_keys=True) + "\n").encode()
        try:
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            if self.path.exists() and self.path.stat().st_size + len(data) > self.max_bytes:
                self.path.replace(self.path.with_suffix(self.path.suffix + ".1"))
            fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
            with os.fdopen(fd, "ab") as output:
                output.write(data)
        except OSError:
            # Diagnostics cannot grant or remove action authority.
            pass


@dataclass(frozen=True)
class Observation:
    online: bool | None
    readiness: Readiness
    observed_at: float | None = None
    goal_epoch: int | None = None


class Observer(Protocol):
    def observe(self) -> Observation: ...


class Actuator(Protocol):
    def resume(self, target: Target, readiness: Readiness) -> str: ...


class ReconnectCycle:
    """Debounce network hints and emit one candidate per observed outage."""

    def __init__(self, outage_seconds: float = 6, recovery_seconds: float = 6,
                 cooldown_seconds: float = 60, max_sample_gap: float = 5):
        if any(not math.isfinite(v) or v < 0 for v in
               (outage_seconds, recovery_seconds, cooldown_seconds, max_sample_gap)):
            raise ValueError("Durations must be finite and nonnegative")
        self.outage_seconds = outage_seconds
        self.recovery_seconds = recovery_seconds
        self.cooldown_seconds = cooldown_seconds
        self.max_sample_gap = max_sample_gap
        self.enabled = False
        self.phase = "off"
        self.since: float | None = None
        self.last_attempt: float | None = None
        self.last_sample: float | None = None

    def enable(self, enabled: bool) -> None:
        self.enabled = enabled
        self.phase = "watching" if enabled else "off"
        self.since = None
        # Keep cooldown across OFF/ON so toggling cannot bypass it.

    def sample(self, online: bool | None, now: float) -> bool:
        if not math.isfinite(now) or (self.last_sample is not None and now < self.last_sample):
            raise ValueError("Samples require increasing finite monotonic time")
        previous_sample, self.last_sample = self.last_sample, now
        if not self.enabled:
            return False
        if previous_sample is not None and now - previous_sample > self.max_sample_gap:
            self.phase, self.since = "watching", None
        if online is None:
            # Unknown breaks debounce and drops an ambiguous outage cycle.
            self.phase, self.since = "watching", None
            return False
        if not online:
            if self.phase not in ("outage_pending", "outage"):
                self.phase, self.since = "outage_pending", now
            if self.phase == "outage_pending" and now - self.since >= self.outage_seconds:
                self.phase = "outage"
            return False
        if self.phase == "outage":
            self.phase, self.since = "recovery_pending", now
        if self.phase == "recovery_pending":
            if now - self.since < self.recovery_seconds:
                return False
            self.phase, self.since = "watching", None
            if self.last_attempt is not None and now - self.last_attempt < self.cooldown_seconds:
                return False
            self.last_attempt = now
            return True
        if self.phase == "outage_pending":
            self.phase, self.since = "watching", None
        return False


class Controller:
    def __init__(self, target: Target, cycle: ReconnectCycle, actuator: Actuator,
                 ready_seconds: float = 0, pending_seconds: float | None = None,
                 trace: Callable[[dict], None] | None = None):
        self.target, self.cycle, self.actuator = target, cycle, actuator
        self.ready_seconds, self.pending_seconds = ready_seconds, pending_seconds
        self.pending_since: float | None = None
        self.ready_since: float | None = None
        self.ready_fingerprint: tuple | None = None
        self.label = "OFF"
        self.trace = trace
        self.action_count = 0
        self.goal_epoch: int | None = None
        self.consumed_incidents: set[tuple] = set()
        self.last_dispatch: float | None = None

    def accept(self, observation: Observation, now: float) -> None:
        old_pending, old_actions = self.pending_since, self.action_count
        previous_sample = self.cycle.last_sample
        sampled = observation.observed_at
        stale = sampled is None or not math.isfinite(sampled) or not 0 <= now - sampled <= 3
        self._accept(observation, now)
        if self.trace:
            event = "sample"
            if not self.cycle.enabled:
                event = "off"
            elif self.action_count > old_actions:
                event = "action_requested"
            elif self.label == "Deferred recovery expired; waiting for another outage":
                event = "pending_expired"
            elif old_pending is None and self.pending_since is not None:
                event = "recovery_pending"
            readiness = Readiness() if stale else observation.readiness
            self.trace({"event": event, "phase": self.cycle.phase,
                        "online": None if stale else observation.online,
                        "pending": self.pending_since is not None,
                        "sample_gap": previous_sample is not None and now - previous_sample > self.cycle.max_sample_gap,
                        "stale_observation": stale, "reason": readiness.reason_code(self.target),
                        "composer_idle": readiness.composer_idle, "desktop_idle": readiness.desktop_idle})

    def _accept(self, observation: Observation, now: float) -> None:
        if observation.goal_epoch is not None and observation.goal_epoch != self.goal_epoch:
            self.goal_epoch = observation.goal_epoch
            self.pending_since = self.ready_since = None
            self.cycle.enable(self.cycle.enabled)
        previous_sample = self.cycle.last_sample
        if not math.isfinite(now) or (previous_sample is not None and now < previous_sample):
            self.ready_since = None
            self.label = "Recovery pending. Waiting for valid observation time"
            return
        if previous_sample is not None and now - previous_sample > self.cycle.max_sample_gap:
            self.ready_since = None
        sampled = observation.observed_at
        if sampled is None or not math.isfinite(sampled) or not 0 <= now - sampled <= 3:
            observation = Observation(None, Readiness())
        fingerprint = (observation.readiness.goal_id, observation.readiness.incident_id,
                       observation.readiness.stall_kind)
        if fingerprint != self.ready_fingerprint:
            self.ready_fingerprint = fingerprint
            self.ready_since = None
        candidate = self.cycle.sample(observation.online, now)
        if not self.cycle.enabled:
            self.pending_since = self.ready_since = None
        if not self.cycle.enabled:
            self.label = "OFF"
            return
        named_stall = observation.readiness.stall_kind in ("transport", "active_idle")
        incident = observation.readiness.incident_id
        if named_stall and incident is not None and incident not in self.consumed_incidents and self.pending_since is None:
            self.pending_since, self.ready_since = now, None
        elif candidate and not named_stall:
            self.pending_since, self.ready_since = now, None
        if self.pending_since is not None and self.pending_seconds is not None and now - self.pending_since > self.pending_seconds:
            self.pending_since = self.ready_since = None
            self.label = "Deferred recovery expired; waiting for another outage"
            return
        blocker = observation.readiness.blocker(self.target)
        self.label = blocker or "Monitoring: " + self.cycle.phase.replace("_", " ")
        if self.pending_since is None:
            return
        if incident is not None and incident in self.consumed_incidents:
            self.pending_since = self.ready_since = None
            return
        if observation.readiness.no_explicit_pause is False:
            self.pending_since = self.ready_since = None
            self.label = "Blocked: protected goal; recovery cancelled"
            return
        if observation.online is not True:
            self.ready_since = None
            self.label = "Recovery pending. Waiting for verified connectivity"
            return
        if blocker:
            self.ready_since = None
            self.label = "Recovery pending. " + blocker
            return
        if self.ready_since is None:
            self.ready_since = now
        if now - self.ready_since < (max(30, self.ready_seconds) if observation.readiness.stall_kind == "active_idle" else self.ready_seconds):
            self.label = "Recovery pending. Confirming stable readiness"
            return
        if self.last_dispatch is not None and now - self.last_dispatch < self.cycle.cooldown_seconds:
            self.label = "Recovery pending. Waiting for cooldown"
            return
        self.pending_since = self.ready_since = None
        self.last_dispatch = now
        self.action_count += 1
        if incident is not None:
            self.consumed_incidents.add(incident)
        try:
            self.label = self.actuator.resume(self.target, observation.readiness)
        except Exception:
            self.label = "Blocked: resume adapter failed"


    def effect_result(self, result: str, readiness: Readiness, now: float) -> None:
        # Only these results guarantee that no typing was attempted. Unknown
        # errors and partial input consume the incident to avoid duplicate input.
        zero_input = {"Deferred: disabled or not ready", "Deferred: target no longer ready",
                      "Deferred: readiness changed after activation", "Deferred: target did not activate"}
        if self.cycle.enabled and result in zero_input:
            self.consumed_incidents.discard(readiness.incident_id)
            self.pending_since, self.ready_since = now, None



def process_identity(pid: int) -> tuple[str, str]:
    proc = Path("/proc") / str(pid)
    stat = (proc / "stat").read_text()
    # The command name can contain spaces and closing parentheses.
    fields = stat[stat.rfind(")") + 2:].split()
    return fields[19], str((proc / "exe").resolve(strict=True))


def command(args: list[str]) -> str:
    result = subprocess.run(args, capture_output=True, text=True, timeout=3, check=True)
    return result.stdout.strip()


def normalized_xid(value: str) -> str:
    return str(int(value, 16) if value.startswith("0x") else int(value))


@dataclass(frozen=True)
class WindowPin:
    title: str
    owner_pid: int
    owner_ticks: str


def stable_title(title: str) -> str:
    # Codex updates only the leading activity glyph during an existing turn.
    return re.sub(r"^[\u2800-\u28ff◐◓◑◒●•✻✽✶✳✢✦]+\s*", "", title)


def window_pin(xid: str) -> WindowPin:
    title = stable_title(command(["xdotool", "getwindowname", xid]))
    owner = int(command(["xdotool", "getwindowpid", xid]))
    return WindowPin(title, owner, process_identity(owner)[0])


def client_window_id(widget_xid: int) -> str:
    """Walk Tk's native child ancestry to the WM-managed client, not its frame."""
    from Xlib import display
    connection = display.Display()
    try:
        root = connection.screen().root
        prop = root.get_full_property(connection.intern_atom("_NET_CLIENT_LIST"), 0)
        clients = set(map(int, prop.value)) if prop is not None else set()
        window = connection.create_resource_object("window", widget_xid)
        for _ in range(12):
            if window.id in clients:
                return str(window.id)
            parent = window.query_tree().parent
            if parent.id == window.id or parent.id == root.id:
                break
            window = parent
        raise ValueError("Cannot identify the managed client window")
    finally:
        connection.close()


def window_geometry(xid: str) -> tuple[int, int, int, int]:
    from Xlib import display
    connection = display.Display()
    try:
        root = connection.screen().root
        window = connection.create_resource_object("window", int(normalized_xid(xid)))
        location = root.translate_coords(window, 0, 0)
        size = window.get_geometry()
        return location.x, location.y, size.width, size.height
    finally:
        connection.close()


@dataclass(frozen=True)
class Goal:
    goal_id: str
    status: str
    token_budget: int | None
    tokens_used: int
    queue_count: int
    deferred: bool


def read_goal(thread_id: str, codex_dir: Path) -> Goal:
    # Select metadata only. Never select objective, messages or queue payload.
    with sqlite3.connect((codex_dir / "goals_1.sqlite").as_uri() + "?mode=ro",
                         uri=True, timeout=1) as db:
        row = db.execute("SELECT goal_id,status,token_budget,tokens_used FROM thread_goals "
                         "WHERE thread_id=?", (thread_id,)).fetchone()
        deferred = bool(db.execute("SELECT count(*) FROM thread_goal_continuation_deferrals "
                                   "WHERE thread_id=?", (thread_id,)).fetchone()[0])
    with sqlite3.connect((codex_dir / "queue_1.sqlite").as_uri() + "?mode=ro",
                         uri=True, timeout=1) as db:
        count = db.execute("SELECT count(*) FROM queued_items WHERE thread_id=?",
                           (thread_id,)).fetchone()[0]
    if row is None:
        raise ValueError("Target has no goal")
    return Goal(*row, count, deferred)



def resumable_turn(codex_dir: Path, thread_id: str) -> tuple[str | None, str | None]:
    with sqlite3.connect((codex_dir / "thread_history_1.sqlite").as_uri() + "?mode=ro",
                         uri=True, timeout=1) as db:
        row = db.execute("SELECT turn_id,status,error_json FROM thread_turns WHERE thread_id=? "
                         "ORDER BY rollout_ordinal DESC LIMIT 1", (thread_id,)).fetchone()
    if row is None:
        return None, None
    turn_id, status, error_json = row
    if status == "completed":
        return "active_idle", turn_id
    if status != "failed" or not error_json:
        return None, turn_id
    error = json.loads(error_json)
    if not isinstance(error, dict) or error.get("misalignment") is not None:
        return None, turn_id
    info = error.get("codexErrorInfo")
    if info == "other" and error.get("additionalDetails") is None:
        # This CLI reports the verified remote-compaction timeout as `other`.
        # Match its complete diagnostic in memory; never generalize `other`.
        message = error.get("message")
        if isinstance(message, str) and re.fullmatch(
            r"Error running remote compact task: stream disconnected before completion: Transport error: timeout",
            message,
        ):
            return "transport", turn_id
    if info in ("serverOverloaded", "flexUnavailable", "internalServerError"):
        return "transport", turn_id
    allowed = {"httpConnectionFailed", "responseStreamConnectionFailed",
               "responseStreamDisconnected", "responseTooManyFailedAttempts"}
    if not isinstance(info, dict) or len(info) != 1:
        return None, turn_id
    name, details = next(iter(info.items()))
    if name not in allowed:
        return None, turn_id
    if not isinstance(details, dict):
        return None, turn_id
    code = details.get("httpStatusCode")
    if code is not None and (type(code) is not int or 400 <= code < 500):
        return None, turn_id
    return "transport", turn_id


class ConnectivitySchedule:
    def __init__(self):
        self.next_check = 0.0
        self.online: bool | None = None

    def due(self, now: float) -> bool:
        return now >= self.next_check

    def record(self, online: bool | None, now: float) -> None:
        self.online = online
        self.next_check = now + (30 if online is False else 2)

def internet_online() -> bool | None:
    # curl's total timeout bounds DNS, TLS and HTTP together. Ignore curlrc,
    # inherited proxies and redirects; send no credentials or response text.
    successes = []
    for url, expected in [("https://www.google.com/generate_204", "204"),
                          ("https://www.cloudflare.com/cdn-cgi/trace", "200")]:
        try:
            code = command(["curl", "-q", "--noproxy", "*", "--connect-timeout", "1",
                            "--max-time", "2", "--silent", "--output", "/dev/null",
                            "--write-out", "%{http_code}", url])
            successes.append(code == expected)
        except (OSError, subprocess.SubprocessError):
            successes.append(False)
    if all(successes):
        return True
    if not any(successes):
        return False
    return None


@dataclass(frozen=True)
class Composer:
    empty: bool
    idle: bool
    no_modal: bool
    interruption: bool
    command_pending: bool = False


PLACEHOLDERS = {"Ask Codex to do anything", "Ask Codex to do anything.",
                "Find and fix a bug in @filename", "Write tests for @filename",
                "Explain this codebase", "Implement {feature}", "Improve documentation in @filename",
                "Summarize recent commits", "Use /skills to list available skills"}


def parse_composer(text: str, caret: int, expected_input: str = "") -> Composer:
    """Parse visible terminal content in memory, never return or log its text."""
    lines = text.splitlines(keepends=True)
    prompts = [i for i, line in enumerate(lines) if re.match(r"^\s*›(?: |$)", line)]
    if not prompts:
        return Composer(False, False, False, False)
    index = prompts[-1]
    prompt = lines[index].rstrip("\r\n")
    raw_suffix = re.sub(r"^\s*› ?", "", prompt)
    offset = sum(map(len, lines[:index]))
    caret_here = caret == offset + prompt.index("›") + 2
    # Only blank rows and the known footer may follow an empty composer.
    tail = "".join(lines[index + 1:])
    tail_ok = all(not line.strip() or re.fullmatch(
        r"\s*(?:\? for shortcuts(?:\s+.*)?|\d+% context left(?:\s+.*)?|"
        r"(?i:gpt-)[\w.\-]+(?:\s+.*)?)\s*", line)
        for line in tail.splitlines())
    recent = "".join(lines[max(0, index - 12):]).lower()
    transport_errors = list(re.finditer(
        r"(?:^|\n)\s*(?:■|error:|⚠)\s*[^\n]*(?:network|"
        r"connection.*(?:lost|failed|closed)|stream.*(?:disconnect|error)|"
        r"retries exhausted|transport.*error|error sending request)[^\n]*", recent))
    # Retry messages before a terminal error are history. The explicit live
    # interrupt hint always blocks, including when an older error is visible.
    current_status = recent[transport_errors[-1].end():] if transport_errors else recent
    busy = "esc to interrupt" in recent or bool(re.search(
        r"(?:^|\n)\s*[•●]?\s*(?:working|thinking|connecting|reconnecting|running)(?:\s|\.)",
        current_status))
    modal = bool(re.search(r"approve|approval|allow this|press enter to continue|"
                           r"\[y/n\]|history search|input disabled|attachment|image attached|"
                           r"goal paused|goal complete|budget.limit|usage.limit|authenticat|unauthorized|sign.in|"
                           r"quota|rate.limit|billing|cyber.policy|misalignment|safety|refusal|context.limit", recent))
    interruption = bool(transport_errors)
    if expected_input:
        empty = raw_suffix == expected_input and caret == offset + len(prompt)
        pending = (not empty and tail_ok and
                   ((expected_input.startswith(raw_suffix) and caret == offset + len(prompt))
                    or (raw_suffix.rstrip() in PLACEHOLDERS and caret_here)))
    else:
        empty = raw_suffix.rstrip() in PLACEHOLDERS and caret_here
        pending = False
    # A bare blank prompt could contain invisible whitespace or clipped input.
    return Composer(empty and tail_ok, not busy, not modal, interruption, pending)


@dataclass(frozen=True)
class TerminalBinding:
    bus_name: str
    window_object: str
    frame_path: str
    tab_path: str
    terminal_path: str


def single_tab_actions(actions: dict) -> bool:
    try:
        return (actions["active-tab"][0] is False and actions["active-tab"][2] == [0]
                and all(actions[name][0] is False for name in
                        ("tabs-menu", "tab-switch-left", "tab-switch-right", "tab-detach")))
    except (KeyError, IndexError, TypeError):
        return False


def gtk_window_properties(xid: str) -> tuple[str, str]:
    from Xlib import display
    connection = display.Display()
    try:
        window = connection.create_resource_object("window", int(normalized_xid(xid)))
        values = []
        for name in ("_GTK_UNIQUE_BUS_NAME", "_GTK_WINDOW_OBJECT_PATH"):
            prop = window.get_full_property(connection.intern_atom(name), 0)
            if prop is None:
                raise ValueError("GTK window binding unavailable")
            values.append(bytes(prop.value).decode("utf-8").rstrip("\0"))
        return tuple(values)
    finally:
        connection.close()


def gi_modules():
    import gi
    gi.require_version("Atspi", "2.0")
    gi.require_version("Gio", "2.0")
    from gi.repository import Atspi, Gio, GLib
    return Atspi, Gio, GLib


def desktop_idle_ms() -> int:
    try:
        _, Gio, GLib = gi_modules()
        connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        value = connection.call_sync(
            "org.gnome.Mutter.IdleMonitor", "/org/gnome/Mutter/IdleMonitor/Core",
            "org.gnome.Mutter.IdleMonitor", "GetIdletime", None,
            GLib.VariantType.new("(t)"), Gio.DBusCallFlags.NONE, 1000, None,
        ).unpack()[0]
        if not isinstance(value, int) or value < 0:
            raise ValueError("Invalid desktop idle observation")
        return value
    except Exception:
        if shutil.which("xprintidle"):
            value = int(command(["xprintidle"]))
            if value >= 0:
                return value
        raise ValueError("Desktop idle observation unavailable") from None


def terminal_context(xid: str) -> tuple[TerminalBinding, object]:
    Atspi, Gio, GLib = gi_modules()
    wanted = window_geometry(xid)
    bus_name, window_object = gtk_window_properties(xid)
    connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    actions = connection.call_sync(
        bus_name, window_object, "org.gtk.Actions", "DescribeAll", None,
        GLib.VariantType.new("(a{s(bgav)})"), Gio.DBusCallFlags.NONE, 1000, None,
    ).unpack()[0]
    if not single_tab_actions(actions):
        raise ValueError("Target must remain a single-tab terminal window")
    frames = []
    desktop = Atspi.get_desktop(0)
    for i in range(desktop.get_child_count()):
        app = desktop.get_child_at_index(i)
        for j in range(app.get_child_count()):
            frame = app.get_child_at_index(j)
            try:
                ext = frame.get_component_iface().get_extents(Atspi.CoordType.SCREEN)
                if all(abs(a - b) <= 2 for a, b in zip(wanted, (ext.x, ext.y, ext.width, ext.height))):
                    frames.append(frame)
            except Exception:
                continue
    if len(frames) != 1:
        raise ValueError("Accessible target frame is ambiguous")
    tabs, terminals = [], []
    pending = [frames[0]]
    visited = 0
    while pending and visited < 512:
        node = pending.pop()
        visited += 1
        role = node.get_role_name()
        if role == "terminal":
            terminals.append(node)
        elif role == "page tab":
            tabs.append(node)
        pending.extend(node.get_child_at_index(i) for i in range(node.get_child_count()))
    if len(tabs) != 1 or len(terminals) != 1 or pending:
        raise ValueError("Accessible target tab or terminal is ambiguous")
    if not terminals[0].get_state_set().contains(Atspi.StateType.SHOWING):
        raise ValueError("Original terminal is not showing")
    binding = TerminalBinding(bus_name, window_object, frames[0].path, tabs[0].path, terminals[0].path)
    return binding, terminals[0].get_text_iface()


def visible_composer(xid: str, expected_input: str = "",
                     expected_binding: TerminalBinding | None = None) -> Composer:
    binding, terminal = terminal_context(xid)
    if expected_binding is None or binding != expected_binding:
        raise ValueError("Original qualified terminal binding changed or unavailable")
    Atspi, _, _ = gi_modules()
    length = Atspi.Text.get_character_count(terminal)
    start = max(0, length - 16384)
    return parse_composer(Atspi.Text.get_text(terminal, start, length),
                          Atspi.Text.get_caret_offset(terminal) - start, expected_input)


class LiveObserver:
    def __init__(self, target: Target, backend_pid: int, tty: str, codex_dir: Path):
        self.target, self.backend_pid, self.tty, self.codex_dir = target, backend_pid, tty, codex_dir
        self.window = window_pin(target.window_id)
        self.backend = process_identity(backend_pid)
        self.binding, _ = terminal_context(target.window_id)
        self.baseline_goal: str | None = None
        self.outage_goal: str | None = None
        self.previous_online: bool | None = None
        self.pause_seen = False
        self.protected_goals: set[str] = set()
        self.current_goal_id: str | None = None
        self.goal_epoch = 0
        self.connectivity = ConnectivitySchedule()

    def reset_cycle(self) -> None:
        self.baseline_goal = self.outage_goal = None
        self.previous_online = None
        self.pause_seen = False
        if not hasattr(self, "protected_goals"):
            self.protected_goals = set()
            self.current_goal_id = None
            self.goal_epoch = 0
        self.goal_epoch += 1
        self.connectivity = ConnectivitySchedule()

    def track_goal(self, goal: Goal, online: bool | None = None) -> None:
        if goal.goal_id != self.current_goal_id:
            self.current_goal_id = goal.goal_id
            self.baseline_goal = self.outage_goal = None
            self.previous_online = None
            self.goal_epoch += 1
        if goal.status not in ("active", "blocked") or (goal.token_budget is not None and goal.tokens_used >= goal.token_budget):
            self.protected_goals.add(goal.goal_id)
        self.pause_seen = goal.goal_id in self.protected_goals
        if online is True and goal.status == "active" and not self.pause_seen and self.baseline_goal != goal.goal_id:
            self.baseline_goal = goal.goal_id
            self.outage_goal = None
            self.previous_online = None
            self.goal_epoch += 1

    def identity_ok(self) -> bool:
        if process_identity(self.target.tui_pid) != (self.target.start_ticks, self.target.executable):
            return False
        if process_identity(self.backend_pid) != self.backend:
            return False
        if self.backend[1] != self.target.executable:
            return False
        if window_pin(self.target.window_id) != self.window:
            return False
        if str((Path("/proc") / str(self.target.tui_pid) / "fd/0").resolve()) != self.tty:
            return False
        stat = (Path("/proc") / str(self.target.tui_pid) / "stat").read_text()
        fields = stat[stat.rfind(")") + 2:].split()
        if fields[2] != fields[5]:  # process group must be the TTY foreground group
            return False
        fds = Path("/proc") / str(self.backend_pid) / "fd"
        names = [str(fd.resolve()) for fd in fds.iterdir()]
        # Pin existing backend to this exact thread without reading its data.
        rollouts = [name for name in names if "rollout-" in name and name.endswith(".jsonl")]
        return (any(self.target.thread_id in name for name in rollouts)
                and any(self.target.thread_id in name and "lock" in name for name in names))

    def readiness(self, expected_input: str = "", require_idle: bool = True) -> Readiness:
        try:
            if not self.identity_ok():
                return Readiness()
            goal = read_goal(self.target.thread_id, self.codex_dir)
            self.track_goal(goal)
            composer = visible_composer(self.target.window_id, expected_input, self.binding)
            desktop_idle = desktop_idle_ms() >= 30000 if require_idle else True
            budget = goal.token_budget is None or goal.tokens_used < goal.token_budget
            stall_kind, turn_id = resumable_turn(self.codex_dir, self.target.thread_id)
            if stall_kind == "active_idle" and goal.status != "active":
                stall_kind = None
            if stall_kind and self.baseline_goal == goal.goal_id and not self.pause_seen:
                self.outage_goal = goal.goal_id
            return Readiness(
                target=self.target, route_verified=True, draft_empty=composer.empty,
                idle=composer.idle and desktop_idle, no_modal=composer.no_modal,
                no_explicit_pause=not self.pause_seen and goal.status in ("active", "blocked"),
                budget_available=budget, recovery_owned=self.outage_goal is not None,
                same_goal=goal.goal_id == self.outage_goal,
                goal_needs_resume=stall_kind is not None and composer.idle
                and goal.status in ("active", "blocked"),
                queue_empty=goal.queue_count == 0 and not goal.deferred,
                command_pending=composer.command_pending,
                composer_idle=composer.idle, desktop_idle=desktop_idle,
                goal_id=goal.goal_id, stall_kind=stall_kind,
                incident_id=(goal.goal_id, turn_id) if turn_id else None,
            )
        except Exception:
            return Readiness()

    def observe(self) -> Observation:
        # UI probes remain frequent; offline connectivity checks are throttled.
        if self.connectivity.due(time.monotonic()):
            self.connectivity.record(internet_online(), time.monotonic())
        online = self.connectivity.online
        try:
            goal = read_goal(self.target.thread_id, self.codex_dir)
            self.track_goal(goal, online)
            if online is False and self.previous_online is True:
                self.outage_goal = self.baseline_goal if goal.goal_id == self.baseline_goal else None
            if online is None and self.outage_goal is None:
                self.baseline_goal = None
            self.previous_online = online
        except Exception:
            # A failed observation cannot establish readiness or change goal ownership.
            pass
        readiness = self.readiness()
        return Observation(online, readiness, time.monotonic(), self.goal_epoch)


class X11Actuator:
    """Inject only the literal command after fresh checks. No input is erased."""

    def __init__(self, fresh_readiness: Callable[..., Readiness], permitted: Callable[[], bool],
                 runner: Callable[[list[str]], str] = command,
                 clock: Callable[[], float] = time.monotonic,
                 sleeper: Callable[[float], None] = time.sleep):
        # Injected callbacks also let the owner test this adapter with an owned
        # dummy terminal. Production passes LiveObserver.readiness.
        self.fresh_readiness, self.permitted, self.runner = fresh_readiness, permitted, runner
        self.clock, self.sleeper = clock, sleeper

    def resume(self, target: Target, readiness: Readiness) -> str:
        if not self.permitted() or readiness.blocker(target):
            return "Deferred: disabled or not ready"
        qualified = (readiness.goal_id, readiness.incident_id, readiness.stall_kind)
        def same_qualification(fresh: Readiness) -> bool:
            return (fresh.goal_id, fresh.incident_id, fresh.stall_kind) == qualified

        old_focus = self.runner(["xdotool", "getactivewindow"])
        old_title = self.runner(["xdotool", "getwindowname", old_focus])
        fresh = self.fresh_readiness()
        if not self.permitted() or fresh.blocker(target) or not same_qualification(fresh):
            return "Deferred: target no longer ready"
        if not self.permitted():
            return "OFF"
        self.runner(["wmctrl", "-ia", target.window_id])
        fresh = self.fresh_readiness()
        if not self.permitted() or fresh.blocker(target) or not same_qualification(fresh):
            return "Deferred: readiness changed after activation"
        if normalized_xid(self.runner(["xdotool", "getactivewindow"])) != normalized_xid(target.window_id):
            return "Deferred: target did not activate"
        if not self.permitted():
            return "OFF"
        self.runner(["xdotool", "type", "--delay", "0", "--", "/goal resume"])
        # After typing, accept only the complete command we own. Never clear
        # altered input or press Return on an unexpected composer.
        deadline = self.clock() + 1
        while True:
            if not self.permitted():
                return "OFF: command left unsubmitted"
            fresh = self.fresh_readiness(expected_input="/goal resume", require_idle=False)
            if not self.permitted():
                return "OFF: command left unsubmitted"
            if normalized_xid(self.runner(["xdotool", "getactivewindow"])) != normalized_xid(target.window_id):
                return "Deferred: command left unsubmitted; focus changed"
            other_blocker = replace(fresh, draft_empty=True).blocker(target)
            if fresh.goal_id != readiness.goal_id:
                return "Deferred: command left unsubmitted; goal changed"
            if not same_qualification(fresh):
                return "Deferred: command left unsubmitted; incident changed"
            if other_blocker:
                return "Deferred: command left unsubmitted; " + other_blocker
            if fresh.draft_empty is True:
                break
            if not fresh.command_pending:
                return "Deferred: command left unsubmitted; Blocked: draft empty"
            if self.clock() >= deadline:
                return "Deferred: command reflection timed out; Blocked: draft empty"
            self.sleeper(min(0.05, max(0, deadline - self.clock())))
        if not self.permitted():
            return "OFF: command left unsubmitted"
        self.runner(["xdotool", "key", "Return"])
        # Restore only a still-existing old window, and only if target focus
        # remains ours. A focus change belongs to the user.
        if self.permitted() and normalized_xid(self.runner(["xdotool", "getactivewindow"])) == normalized_xid(target.window_id):
            try:
                current_old_title = self.runner(["xdotool", "getwindowname", old_focus])
                if self.permitted() and current_old_title == old_title:
                    self.runner(["wmctrl", "-ia", old_focus])
            except Exception:
                pass
        return "Sent /goal resume. Continuation is not yet verified."

def run_ui(target: Target, observer: LiveObserver) -> None:
    import tkinter as tk

    root = tk.Tk()
    root.title("Codex reconnect")
    root.configure(bg="#15191f")
    root.attributes("-topmost", True)
    root.resizable(False, False)
    cycle = ReconnectCycle(max_sample_gap=12)
    diagnostics = TransitionDiagnostics(Path.home() / ".local/state/codex-reconnect-toggle/transitions.jsonl")
    status = tk.StringVar(value="OFF")
    result_queue: queue.Queue = queue.Queue()
    generation = 0
    inflight = False
    effect_busy = False
    closed = False
    next_poll = 0.0

    class AsyncActuator:
        def resume(self, target: Target, readiness: Readiness) -> str:
            nonlocal effect_busy
            token = generation
            effect_busy = True
            def effect() -> None:
                permitted = lambda: not closed and cycle.enabled and token == generation
                adapter = X11Actuator(observer.readiness, permitted)
                try:
                    result = adapter.resume(target, readiness)
                except Exception:
                    result = "Deferred: X11 adapter failed; check target input"
                event = "action_sent_unverified" if result.startswith("Sent /goal resume") else (
                    "action_failed" if "adapter failed" in result else "action_deferred")
                diagnostics({"event": event, "phase": cycle.phase, "pending": False})
                result_queue.put(("effect", token, (result, readiness)))
            threading.Thread(target=effect, daemon=True).start()
            return "Checking target before resume"

    controller = Controller(target, cycle, AsyncActuator(), ready_seconds=3, trace=diagnostics)
    tk.Label(root, text="Codex reconnect", bg="#15191f", fg="#f1f3f5",
             font=("Sans", 12, "bold")).pack(padx=16, pady=(12, 6))
    tk.Label(root, textvariable=status, bg="#15191f", fg="#c1c7d0",
             wraplength=310, justify="left").pack(padx=16, pady=8)

    def toggle() -> None:
        nonlocal generation, next_poll
        generation += 1
        cycle.enable(not cycle.enabled)
        controller.pending_since = controller.ready_since = None
        # Reset only with no worker running; an old worker cannot authorize a
        # new generation. Reset again before that generation's first sample.
        button.configure(text="ON" if cycle.enabled else "OFF",
                         bg="#236342" if cycle.enabled else "#343c49")
        next_poll = 0
        status.set("ON. Waiting for an observed outage" if cycle.enabled else "OFF")
        diagnostics({"event": "on" if cycle.enabled else "off", "phase": cycle.phase, "pending": False})

    button = tk.Button(root, text="OFF", command=toggle, bg="#343c49", fg="white",
                       activebackground="#4c5667", activeforeground="white", width=14)
    button.pack(padx=16, pady=(4, 12))
    observer_generation = -1

    def collect_observation(token: int) -> None:
        try:
            observation = observer.observe()
        except Exception:
            observation = Observation(None, Readiness())
        result_queue.put(("observation", token, observation))

    def tick() -> None:
        nonlocal inflight, effect_busy, next_poll, observer_generation
        if closed:
            return
        try:
            while True:
                kind, token, payload = result_queue.get_nowait()
                if kind == "effect":
                    effect_busy = False
                    if cycle.enabled and token == generation:
                        result, requested_readiness = payload
                        controller.effect_result(result, requested_readiness, time.monotonic())
                        status.set("ON. " + result)
                else:
                    inflight = False
                    if cycle.enabled and token == generation:
                        controller.accept(payload, time.monotonic())
                        status.set("ON. " + controller.label)
        except queue.Empty:
            pass
        now = time.monotonic()
        if cycle.enabled and not inflight and not effect_busy and now >= next_poll:
            if observer_generation != generation:
                observer.reset_cycle()
                observer_generation = generation
            inflight = True
            next_poll = now + 2
            threading.Thread(target=collect_observation, args=(generation,), daemon=True).start()
        root.after(100, tick)

    def close() -> None:
        nonlocal generation, closed
        closed = True
        generation += 1
        cycle.enable(False)
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", close)
    root.after(0, tick)
    root.mainloop()


def run_fixture() -> None:
    """Owned keyboard fixture. It has no Codex, network or goal connection."""
    import tkinter as tk

    root = tk.Tk()
    root.title("Codex reconnect fixture")
    root.configure(bg="#15191f")
    root.geometry("540x270")
    root.resizable(False, False)
    editor = tk.Text(root, width=42, height=4, bg="#222831", fg="white")
    editor.pack(padx=12, pady=12)
    message = tk.StringVar(value="Owned fixture. No command is executed.")
    tk.Label(root, textvariable=message, bg="#15191f", fg="white", wraplength=500,
             height=4, width=65).pack(padx=12, pady=8)
    permitted = threading.Event()
    closed = False
    request_queue: queue.Queue = queue.Queue()
    target: Target | None = None

    def validate(expected_input: str = "", **unused) -> Readiness:
        # Worker asks the Tk owner to inspect its own buffer. No real terminal
        # text or goal state is accessed by this fixture callback.
        reply: queue.Queue = queue.Queue(maxsize=1)
        request_queue.put(("readiness", expected_input, reply))
        try:
            return reply.get(timeout=2)
        except queue.Empty:
            return Readiness()

    def pump() -> None:
        if closed:
            return
        try:
            while True:
                kind, expected, reply = request_queue.get_nowait()
                if kind == "result":
                    receipt = "Fixture received exact command + Enter. " if message.get().startswith(
                        "Fixture received exact command + Enter") else ""
                    message.set(receipt + expected)
                    continue
                value = editor.get("1.0", "end-1c")
                fields = {name: True for name in Readiness.__dataclass_fields__ if name != "target"}
                fields["draft_empty"] = value == expected
                fields["command_pending"] = bool(expected and value != expected and expected.startswith(value))
                reply.put(Readiness(target=target, **fields))
        except queue.Empty:
            pass
        root.after(50, pump)

    def submitted(event) -> str:
        value = editor.get("1.0", "end-1c")
        message.set("Fixture received exact command + Enter" if value == "/goal resume"
                    else "Fixture received unexpected input")
        return "break"

    editor.bind("<Return>", submitted)

    def test() -> None:
        nonlocal target
        if permitted.is_set():
            return
        root.update_idletasks()
        message.set("Checking owned fixture...")
        try:
            xid = client_window_id(root.winfo_id())
            ticks, executable = process_identity(os.getpid())
        except Exception as exc:
            message.set("Fixture setup failed: " + type(exc).__name__)
            return
        target = Target("owned-fixture", str(xid), os.getpid(), ticks, executable)
        permitted.set()
        editor.focus_set()
        def effect() -> None:
            try:
                adapter = X11Actuator(validate, permitted.is_set)
                result = adapter.resume(target, validate())
            except Exception as exc:
                result = "Fixture adapter failed: " + type(exc).__name__
            finally:
                request_queue.put(("result", result, None))
                permitted.clear()
        threading.Thread(target=effect, daemon=True).start()

    tk.Button(root, text="Test owned fixture", command=test, bg="#343c49", fg="white").pack(pady=8)

    def close() -> None:
        nonlocal closed
        closed = True
        permitted.clear()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", close)
    root.after(0, pump)
    root.mainloop()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", action="store_true", help="Open an owned dummy keyboard fixture")
    parser.add_argument("--thread-id")
    parser.add_argument("--window-id")
    parser.add_argument("--tui-pid", type=int)
    parser.add_argument("--backend-pid", type=int)
    parser.add_argument("--tty")
    parser.add_argument("--qualify-target", action="store_true",
                        help="Confirm this XID contains the supplied Codex thread and TTY")
    parser.add_argument("--codex-dir", type=Path, default=Path.home() / ".codex")
    args = parser.parse_args()
    if args.fixture:
        run_fixture()
        return
    if not all((args.thread_id, args.window_id, args.tui_pid, args.backend_pid, args.tty)):
        parser.error("Supply thread-id, window-id, tui-pid, backend-pid and tty")
    try:
        ticks, executable = process_identity(args.tui_pid)
    except (OSError, IndexError) as exc:
        parser.error("Cannot read target process identity: " + type(exc).__name__)
    if not args.qualify_target:
        parser.error("Manually verify target window/thread/TTY, then pass --qualify-target")
    target = Target(args.thread_id, args.window_id, args.tui_pid, ticks, executable)
    try:
        observer = LiveObserver(target, args.backend_pid, args.tty, args.codex_dir.resolve())
        if not observer.identity_ok():
            parser.error("Target identity does not match supplied binding")
    except (OSError, ValueError, subprocess.SubprocessError):
        parser.error("Cannot verify target identity")
    run_ui(target, observer)


if __name__ == "__main__":
    main()
