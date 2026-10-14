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
import subprocess
import sys
import tempfile
import threading
import time
import types
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "scripts" / "codex_reconnect_toggle.py"
SOURCE_SHA = "b6f2ce1454db30c290befcf74b13df1897f584645bedc8f1faa86e67f44c0d43"
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


def history_fixture(directory, status, known_transport=False):
    directory.mkdir(mode=0o700)
    path = directory / "thread_history_1.sqlite"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE thread_turns (thread_id TEXT, turn_id TEXT, "
                   "status TEXT, error_json TEXT, rollout_ordinal INTEGER)")
        error = json.dumps({"codexErrorInfo": "other", "additionalDetails": None,
                            "misalignment": None,
                            "message": ("Error running remote compact task: stream disconnected before completion: Transport error: timeout" if known_transport else "Unexpected decoder crash while processing a response")}) if status == "failed" else None
        db.execute("INSERT INTO thread_turns VALUES (?,?,?,?,1)",
                   ("owned-synthetic-thread", "owned-synthetic-turn", status, error))
    path.chmod(0o400)
    return path


def parse_arguments(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--start-unfocused", action="store_true")
    parser.add_argument("--baseline-loss", action="store_true")
    parser.add_argument("--close-guard", nargs=argparse.REMAINDER,
                        help="Optional final argument: audit executable and argv; hex window ID is appended, no shell")
    args = parser.parse_args(argv)
    if args.close_guard == []:
        parser.error("--close-guard requires an executable")
    return args


def audit_owned_close(mod, xid, expected_pin, guard_argv):
    pin = mod.window_pin(xid)
    if pin.owner_pid != os.getpid() or (expected_pin is not None and pin != expected_pin):
        raise RuntimeError("CLEANUP_WINDOW_NOT_OWNED")
    if guard_argv is not None:
        subprocess.run([*guard_argv, f"0x{int(mod.normalized_xid(xid)):08x}"],
                       check=True, stdout=subprocess.DEVNULL, timeout=5)


def main():
    args = parse_arguments()
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
    other = None
    if args.start_unfocused:
        other = tk.Toplevel(root)
        other.title("Owned background-focus companion")
        other.configure(bg="#15191f")
        other.geometry("560x210")
        tk.Label(other, text="Owned focus holder. No command input.",
                 bg="#15191f", fg="white").pack(padx=12, pady=24)
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
    if other is not None:
        other.protocol("WM_DELETE_WINDOW", lambda: cancel("OWNED_COMPANION_CLOSED"))
    root.after(26000, lambda: cancel("REAL_WALL_TIMEOUT"))
    old_term = signal.signal(signal.SIGTERM, lambda *_: cancel("ROOT_TERMINATION"))
    old_int = signal.signal(signal.SIGINT, lambda *_: cancel("ROOT_INTERRUPTION"))

    with tempfile.TemporaryDirectory(prefix="owned-watch-x11-") as temporary:
        private = Path(temporary)
        private.chmod(0o700)
        active = private / "in-progress"
        failed = private / "failed"
        files = [history_fixture(active, "inProgress"), history_fixture(failed, "failed", args.baseline_loss)]
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
                    return (mod.Goal("owned-synthetic-goal", "blocked", None, 0, 0, False)
                            if directory == failed else frozen_goal)

                def composer(xid, expected_input="", binding=None):
                    if xid != target.window_id or binding is not observer.binding:
                        raise RuntimeError("OUTSIDE_OWNED_COMPOSER")
                    value, count, submitted_values = fresh_buffer(expected_input)
                    return mod.Composer(value == expected_input, True, True, False,
                                        bool(expected_input and value != expected_input
                                             and expected_input.startswith(value)))

                def network():
                    probes.append(now[0])
                    if args.baseline_loss:
                        return None if now[0] == 2 else True
                    return now[0] == 0 or now[0] >= 62

                def safe_command(argv):
                    if abort.is_set() or not owned_identity():
                        raise RuntimeError("OWNED_TARGET_IDENTITY_REFUSED")
                    owned_ids = {target.window_id}
                    if args.start_unfocused:
                        owned_ids.add(answers["other_xid"])
                        if mod.window_pin(answers["other_xid"]) != answers["other_pin"]:
                            raise RuntimeError("OWNED_COMPANION_IDENTITY_CHANGED")
                    allowed = (argv == ["xdotool", "getactivewindow"]
                               or any(argv == ["xdotool", "getwindowname", xid] for xid in owned_ids)
                               or any(argv == ["wmctrl", "-ia", xid] for xid in owned_ids)
                               or argv == ["xdotool", "type", "--delay", "0", "--", "/goal resume"]
                               or argv == ["xdotool", "key", "Return"])
                    if not allowed:
                        raise RuntimeError("OUTSIDE_OWNED_COMMAND")
                    current = mod.normalized_xid(mod.command(["xdotool", "getactivewindow"]))
                    if current not in owned_ids:
                        raise RuntimeError("FOCUS_OUTSIDE_OWNED_WINDOWS")
                    if argv[1] in ("type", "key"):
                        if current != target.window_id:
                            raise RuntimeError("OWNED_TARGET_NOT_ACTIVE")
                        if not in_controller[0] or controller.action_count != 1:
                            raise RuntimeError("INPUT_NOT_FROM_SINGLE_CONTROLLER_DISPATCH")
                    commands.append(list(argv))
                    value = mod.command(argv)
                    if argv == ["xdotool", "getactivewindow"]:
                        if mod.normalized_xid(value) not in owned_ids:
                            raise RuntimeError("ACTIVE_TARGET_CHANGED")
                        value = mod.normalized_xid(value)
                    return value

                class RecordedActuator(mod.X11Actuator):
                    def resume(self, selected, readiness):
                        if selected != target or not in_controller[0]:
                            raise RuntimeError("NON_CONTROLLER_DISPATCH")
                        initial_focus = mod.normalized_xid(mod.command(["xdotool", "getactivewindow"]))
                        expected_initial = answers["other_xid"] if args.start_unfocused else target.window_id
                        assert initial_focus == expected_initial
                        dispatch.append({"at": now[0], "incident": readiness.incident_id,
                                         "started_unfocused": initial_focus != target.window_id})
                        result = super().resume(selected, readiness)
                        deadline = REAL_CLOCK() + 1
                        while mod.normalized_xid(mod.command(["xdotool", "getactivewindow"])) != expected_initial:
                            if abort.is_set() or REAL_CLOCK() >= deadline:
                                raise RuntimeError("OWNED_OLD_FOCUS_NOT_RESTORED")
                            REAL_SLEEP(0.01)
                        dispatch[-1]["old_focus_restored"] = True
                        dispatch[-1]["result"] = result
                        return result

                cycle = mod.ReconnectCycle()
                actuator = RecordedActuator(observer.readiness, permitted.is_set,
                                            runner=safe_command, clock=REAL_CLOCK, sleeper=REAL_SLEEP)
                controller = mod.Controller(target, cycle, actuator, ready_seconds=3)
                assert not cycle.enabled
                observer.reset_cycle()
                cycle.enable(True)
                if args.baseline_loss:
                    observer.track_goal(mod.Goal("owned-prior-goal", "active", None, 0, 0, False), True)
                permitted.set()
                clock_adapter = types.SimpleNamespace(monotonic=lambda: now[0])
                # Keep real actuator clock/sleep separate from scheduler time.
                with patch.object(mod, "time", clock_adapter), \
                     patch.object(mod, "read_goal", goal_reader), \
                     patch.object(mod, "visible_composer", composer), \
                     patch.object(mod, "desktop_idle_ms", lambda: 30000), \
                     patch.object(mod, "internet_online", network):
                    assert mod.resumable_turn(active, target.thread_id) == (None, "owned-synthetic-turn")
                    assert mod.resumable_turn(failed, target.thread_id, "blocked") == ("transport" if args.baseline_loss else "goal_stall", "owned-synthetic-turn")
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
                        if args.baseline_loss and tick == 2:
                            assert observation.online is None and controller.action_count == 0
                            assert observer.baseline_goal == "owned-synthetic-goal"
                            assert observer.startup_adoption_allowed is False
                        if not args.baseline_loss and 2 <= tick < 62:
                            assert observation.online is False and controller.action_count == 0
                        if controller.action_count > before:
                            assert tick >= (8 if args.baseline_loss else 66)
                            assert dispatch[-1]["result"] == "Sent /goal resume. Continuation is not yet verified."
                    value, count, values = fresh_buffer()
                    assert probes[:4] == ([0.0, 2.0, 4.0, 6.0] if args.baseline_loss else [0.0, 2.0, 32.0, 62.0])
                    assert all(b - a == 2 for a, b in zip(probes[3:], probes[4:]))
                    assert len(dispatch) == controller.action_count == count == 1
                    assert values == ("/goal resume",) and value == ""
                    assert commands.count(["xdotool", "type", "--delay", "0", "--", "/goal resume"]) == 1
                    assert commands.count(["xdotool", "key", "Return"]) == 1
                    assert now[0] - dispatch[0]["at"] > cycle.cooldown_seconds
                    assert (frozen_goal.goal_id, frozen_goal.status, frozen_goal.tokens_used) == ("owned-synthetic-goal", "active", 0)
                    assert {str(p.relative_to(private)): digest(p) for p in files} == fixture_pins
                    assert digest(SOURCE) == SOURCE_SHA
                    if args.start_unfocused:
                        activations = [argv[2] for argv in commands if argv[:2] == ["wmctrl", "-ia"]]
                        assert activations == [target.window_id, answers["other_xid"]]
                        assert dispatch[0]["started_unfocused"] and dispatch[0]["old_focus_restored"]
                    receipt.update(status="PASS", baseline_loss=args.baseline_loss, start_unfocused=args.start_unfocused, probe_times=probes, observations=observations,
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
                    owned_xids = [xid]
                    if other is not None:
                        answers["other_xid"] = mod.normalized_xid(mod.client_window_id(other.winfo_id()))
                        assert answers["other_xid"] != xid
                        owned_xids.append(answers["other_xid"])
                    for owned_xid in owned_xids:
                        client = connection.create_resource_object("window", int(owned_xid))
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
                if other is not None:
                    answers["other_pin"] = mod.window_pin(answers["other_xid"])
                    assert answers["other_pin"].owner_pid == os.getpid()
                initial_xid = answers["other_xid"] if other is not None else xid
                mod.command(["wmctrl", "-ia", initial_xid])
                deadline = REAL_CLOCK() + 1
                while mod.normalized_xid(mod.command(["xdotool", "getactivewindow"])) != initial_xid:
                    if REAL_CLOCK() >= deadline: raise RuntimeError("OWNED_INITIAL_FOCUS_FAILED")
                    REAL_SLEEP(0.01)
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
            for close_xid in ([target.window_id] if target else []) + ([answers["other_xid"]] if "other_xid" in answers else []):
                expected_pin = answers.get("window_pin") if target and close_xid == target.window_id else answers.get("other_pin")
                audit_owned_close(mod, close_xid, expected_pin, args.close_guard)
            receipt["external_close_guard_used"] = args.close_guard is not None
            if other is not None:
                other.destroy()
                receipt["owned_companion_closed"] = True
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
