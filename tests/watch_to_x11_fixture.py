"""Owned synthetic watcher-to-X11 integration, executed only by its owner."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import queue
import signal
import sqlite3
import sys
import tempfile
import threading
import time
import types
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "scripts/codex_reconnect_toggle.py"
SOURCE_SHA = "85af79224558d04816d5d094bfd9ffaff955ea8295bcd9bdb46d71ab53bf9b93"
REAL_CLOCK = time.monotonic
REAL_SLEEP = time.sleep


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_production():
    if digest(SOURCE) != SOURCE_SHA:
        raise RuntimeError("PRODUCTION_PIN_CHANGED")
    spec = importlib.util.spec_from_file_location("owned_watcher_fixture_module", SOURCE)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def history_fixture(directory, status):
    directory.mkdir(mode=0o700)
    path = directory / "thread_history_1.sqlite"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE thread_turns (thread_id TEXT, turn_id TEXT, "
                   "status TEXT, error_json TEXT, rollout_ordinal INTEGER)")
        error = json.dumps({"codexErrorInfo": "serverOverloaded", "misalignment": None}) if status == "failed" else None
        db.execute("INSERT INTO thread_turns VALUES (?,?,?,?,1)",
                   ("owned-synthetic-thread", "owned-synthetic-turn", status, error))
    path.chmod(0o400)
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    if args.receipt.exists():
        raise RuntimeError("RECEIPT_ALREADY_EXISTS")
    mod = load_production()
    import tkinter as tk

    started = REAL_CLOCK()
    abort = threading.Event()
    permitted = threading.Event()
    requests = queue.Queue(maxsize=4)
    answers = {}
    receipt = {"schema": "OWNED_WATCHER_X11_FIXTURE_V1", "status": "FAIL",
               "production_sha256": SOURCE_SHA,
               "limits": ["Synthetic fixture only, not natural automatic recovery",
                          "No run_ui generation/queue or GNOME/TTY qualification",
                          "No provider, live Codex DB, native goal or actual continuation proof"]}
    root = tk.Tk()
    root.title("Owned watcher-to-X11 fixture")
    root.configure(bg="#15191f")
    root.geometry("560x210")
    editor = tk.Text(root, width=46, height=3, bg="#222831", fg="white")
    editor.pack(padx=12, pady=12)
    tk.Label(root, text="Synthetic private watcher fixture. No command is executed.",
             bg="#15191f", fg="white").pack()
    returns = []
    target = None
    worker = None

    def submitted(event):
        value = editor.get("1.0", "end-1c")
        returns.append(value)
        editor.delete("1.0", "end")
        return "break"

    editor.bind("<Return>", submitted)

    def fresh_buffer(expected=""):
        response = queue.Queue(maxsize=1)
        requests.put(("buffer", expected, response), timeout=1)
        return response.get(timeout=1)

    def pump():
        try:
            while True:
                kind, expected, response = requests.get_nowait()
                if kind != "buffer":
                    raise RuntimeError("UNKNOWN_FIXTURE_REQUEST")
                value = editor.get("1.0", "end-1c")
                response.put((value, len(returns), tuple(returns)))
        except queue.Empty:
            pass
        if not abort.is_set():
            root.after(10, pump)

    def cancel(reason):
        receipt.setdefault("failure", reason)
        permitted.clear()
        abort.set()
        root.quit()

    root.protocol("WM_DELETE_WINDOW", lambda: cancel("OWNED_WINDOW_CLOSED"))
    root.after(26000, lambda: cancel("REAL_WALL_TIMEOUT"))
    old_term = signal.signal(signal.SIGTERM, lambda *_: cancel("ROOT_TERMINATION"))
    old_int = signal.signal(signal.SIGINT, lambda *_: cancel("ROOT_INTERRUPTION"))

    with tempfile.TemporaryDirectory(prefix="owned-watch-x11-") as temporary:
        private = Path(temporary)
        private.chmod(0o700)
        active = private / "in-progress"
        failed = private / "failed"
        files = [history_fixture(active, "inProgress"), history_fixture(failed, "failed")]
        fixture_pins = {str(p.relative_to(private)): digest(p) for p in files}
        frozen_goal = mod.Goal("owned-synthetic-goal", "active", None, 0, 0, False)

        def run_worker():
            now = [0.0]
            probes = []
            observations = []
            commands = []
            dispatch = []
            in_controller = [False]
            controller = None
            try:
                observer = object.__new__(mod.LiveObserver)
                observer.target = target
                observer.codex_dir = active
                observer.binding = object()
                observer.protected_goals = set()
                observer.current_goal_id = None
                observer.goal_epoch = 0
                observer.reset_cycle()

                def owned_identity():
                    return (not abort.is_set()
                            and mod.process_identity(os.getpid()) == (target.start_ticks, target.executable)
                            and mod.window_pin(target.window_id) == answers["window_pin"]
                            and answers["window_pin"].owner_pid == os.getpid())

                observer.identity_ok = owned_identity

                def goal_reader(thread_id, directory):
                    if thread_id != target.thread_id or directory not in (active, failed):
                        raise RuntimeError("OUTSIDE_PRIVATE_HISTORY")
                    return frozen_goal

                def composer(xid, expected_input="", binding=None):
                    if xid != target.window_id or binding is not observer.binding:
                        raise RuntimeError("OUTSIDE_OWNED_COMPOSER")
                    value, count, submitted_values = fresh_buffer(expected_input)
                    return mod.Composer(value == expected_input, True, True, False,
                                        bool(expected_input and value != expected_input
                                             and expected_input.startswith(value)))

                def network():
                    probes.append(now[0])
                    return now[0] == 0 or now[0] >= 62

                def safe_command(argv):
                    if abort.is_set() or not owned_identity():
                        raise RuntimeError("OWNED_TARGET_IDENTITY_REFUSED")
                    allowed = (argv == ["xdotool", "getactivewindow"]
                               or argv == ["xdotool", "getwindowname", target.window_id]
                               or argv == ["wmctrl", "-ia", target.window_id]
                               or argv == ["xdotool", "type", "--delay", "0", "--", "/goal resume"]
                               or argv == ["xdotool", "key", "Return"])
                    if not allowed:
                        raise RuntimeError("OUTSIDE_OWNED_COMMAND")
                    current = mod.normalized_xid(mod.command(["xdotool", "getactivewindow"]))
                    if current != target.window_id:
                        raise RuntimeError("OWNED_TARGET_NOT_ACTIVE")
                    if argv[1] in ("type", "key"):
                        if not in_controller[0] or controller.action_count != 1:
                            raise RuntimeError("INPUT_NOT_FROM_SINGLE_CONTROLLER_DISPATCH")
                    commands.append(list(argv))
                    value = mod.command(argv)
                    if argv == ["xdotool", "getactivewindow"]:
                        if mod.normalized_xid(value) != target.window_id:
                            raise RuntimeError("ACTIVE_TARGET_CHANGED")
                        # Return normalized own XID so actuator restoration is own-only.
                        value = target.window_id
                    return value

                class RecordedActuator(mod.X11Actuator):
                    def resume(self, selected, readiness):
                        if selected != target or not in_controller[0]:
                            raise RuntimeError("NON_CONTROLLER_DISPATCH")
                        dispatch.append({"at": now[0], "incident": readiness.incident_id})
                        result = super().resume(selected, readiness)
                        dispatch[-1]["result"] = result
                        return result

                cycle = mod.ReconnectCycle()
                actuator = RecordedActuator(observer.readiness, permitted.is_set,
                                            runner=safe_command, clock=REAL_CLOCK, sleeper=REAL_SLEEP)
                controller = mod.Controller(target, cycle, actuator, ready_seconds=3)
                assert not cycle.enabled
                observer.reset_cycle()
                cycle.enable(True)
                permitted.set()
                clock_adapter = types.SimpleNamespace(monotonic=lambda: now[0])
                # Keep real actuator clock/sleep separate from scheduler time.
                with patch.object(mod, "time", clock_adapter), \
                     patch.object(mod, "read_goal", goal_reader), \
                     patch.object(mod, "visible_composer", composer), \
                     patch.object(mod, "desktop_idle_ms", lambda: 30000), \
                     patch.object(mod, "internet_online", network):
                    assert mod.resumable_turn(active, target.thread_id) == (None, "owned-synthetic-turn")
                    assert mod.resumable_turn(failed, target.thread_id) == ("transport", "owned-synthetic-turn")
                    for tick in range(0, 144, 2):
                        if abort.is_set() or REAL_CLOCK() - started > 25:
                            raise RuntimeError("REAL_WALL_TIMEOUT")
                        now[0] = float(tick)
                        if tick == 2:
                            observer.codex_dir = failed
                        observation = observer.observe()
                        before = controller.action_count
                        in_controller[0] = True
                        try:
                            controller.accept(observation, now[0])
                        finally:
                            in_controller[0] = False
                        observations.append({"at": tick, "online": observation.online,
                                             "stall": observation.readiness.stall_kind,
                                             "incident": observation.readiness.incident_id,
                                             "gate": observation.readiness.reason_code(target),
                                             "phase": cycle.phase,
                                             "pending": controller.pending_since is not None,
                                             "actions": controller.action_count, "label": controller.label})
                        if tick == 0:
                            assert observation.readiness.stall_kind is None and controller.action_count == 0
                        if 2 <= tick < 62:
                            assert observation.online is False and controller.action_count == 0
                        if controller.action_count > before:
                            assert tick >= 66
                            assert dispatch[-1]["result"] == "Sent /goal resume. Continuation is not yet verified."
                    value, count, values = fresh_buffer()
                    assert probes[:4] == [0.0, 2.0, 32.0, 62.0]
                    assert all(b - a == 2 for a, b in zip(probes[3:], probes[4:]))
                    assert len(dispatch) == controller.action_count == count == 1
                    assert values == ("/goal resume",) and value == ""
                    assert commands.count(["xdotool", "type", "--delay", "0", "--", "/goal resume"]) == 1
                    assert commands.count(["xdotool", "key", "Return"]) == 1
                    assert now[0] - dispatch[0]["at"] > cycle.cooldown_seconds
                    assert (frozen_goal.goal_id, frozen_goal.status, frozen_goal.tokens_used) == ("owned-synthetic-goal", "active", 0)
                    assert {str(p.relative_to(private)): digest(p) for p in files} == fixture_pins
                    assert digest(SOURCE) == SOURCE_SHA
                    receipt.update(status="PASS", probe_times=probes, observations=observations,
                                   dispatch=dispatch, controller_action_count=1, returns=1,
                                   received=list(values), commands=commands,
                                   private_history_unchanged=True, synthetic_goal_unchanged=True,
                                   fixture_history_pins=fixture_pins,
                                   production_readiness_and_resumable_turn_unreplaced=True)
            except BaseException as error:
                receipt["failure"] = {"category": type(error).__name__, "message": str(error)[:300]}
            finally:
                permitted.clear()
                if controller is not None:
                    controller.cycle.enable(False)
                answers["worker_done"] = True

        def start():
            nonlocal target, worker
            try:
                root.update_idletasks()
                xid = mod.normalized_xid(mod.client_window_id(root.winfo_id()))
                ticks, executable = mod.process_identity(os.getpid())
                target = mod.Target("owned-synthetic-thread", xid, os.getpid(), ticks, executable)
                # Set only this fixture client's PID property to its real owner.
                from Xlib import Xatom, display
                connection = display.Display()
                try:
                    client = connection.create_resource_object("window", int(xid))
                    client.change_property(connection.intern_atom("_NET_WM_PID"),
                                           Xatom.CARDINAL, 32, [os.getpid()])
                    connection.sync()
                finally:
                    connection.close()
                answers["window_pin"] = mod.window_pin(xid)
                if answers["window_pin"].owner_pid != os.getpid():
                    raise RuntimeError("WINDOW_NOT_OWNED")
                editor.focus_set()
                # Initial activation is exclusively this newly created fixture.
                mod.command(["wmctrl", "-ia", xid])
                receipt["target"] = {"xid": xid, "pid": os.getpid(), "start_ticks": ticks,
                                     "window_title": answers["window_pin"].title}
                worker = threading.Thread(target=run_worker, name="owned-watcher-worker", daemon=True)
                worker.start()
            except BaseException as error:
                receipt["failure"] = {"category": type(error).__name__, "message": str(error)[:300]}
                root.quit()

        def check_done():
            if answers.get("worker_done"):
                root.quit()
            elif not abort.is_set():
                root.after(20, check_done)

        root.after(10, pump)
        root.after(300, start)
        root.after(320, check_done)
        try:
            root.mainloop()
        finally:
            permitted.clear()
            abort.set()
            if worker is not None:
                worker.join(timeout=2)
                if worker.is_alive():
                    receipt.update(status="FAIL", failure="WORKER_DID_NOT_STOP")
            root.destroy()
            signal.signal(signal.SIGTERM, old_term)
            signal.signal(signal.SIGINT, old_int)
    receipt["real_wall_seconds"] = REAL_CLOCK() - started
    receipt["owned_window_closed"] = True
    receipt["worker_joined"] = worker is not None and not worker.is_alive()
    if "failure" in receipt:
        receipt["status"] = "FAIL"
    with args.receipt.open("x") as stream:
        json.dump(receipt, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps({"status": receipt["status"], "receipt": str(args.receipt),
                      "sha256": digest(args.receipt)}))
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
