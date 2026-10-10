"""Reconnect tests use synthetic observations and never access a Codex session."""

from dataclasses import replace
import importlib.util
from pathlib import Path
import sys
import tempfile
import json
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "codex_reconnect_toggle", Path(__file__).parents[1] / "scripts/codex_reconnect_toggle.py")
mod = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = mod
SPEC.loader.exec_module(mod)

TARGET = mod.Target("fixture-thread", "fixture-window", 12345, "42", "/fixture/codex")


def ready():
    return mod.Readiness(target=TARGET, **{
        field: True for field in mod.Readiness.__dataclass_fields__ if field not in ("target", "stall_kind", "incident_id")})


class MockActuator:
    def __init__(self):
        self.calls = []

    def resume(self, target, readiness):
        self.calls.append((target, readiness))
        return "Fixture resume accepted"


class ReconnectTests(unittest.TestCase):
    def cycle(self, **kwargs):
        cycle = mod.ReconnectCycle(outage_seconds=2, recovery_seconds=2,
                                   cooldown_seconds=10, **kwargs)
        cycle.enable(True)
        return cycle

    def recovery(self, cycle, offset=0):
        return [cycle.sample(online, offset + t) for t, online in
                [(0, False), (1, False), (2, False), (3, True), (4, True), (5, True)]]

    def test_off_default_and_coldstart_online(self):
        cycle = mod.ReconnectCycle()
        self.assertFalse(cycle.sample(False, 0))
        cycle.enable(True)
        self.assertFalse(any(cycle.sample(True, t) for t in range(20)))

    def test_debounce_and_one_attempt(self):
        cycle = self.cycle()
        self.assertEqual(self.recovery(cycle), [False] * 5 + [True])
        self.assertFalse(any(cycle.sample(True, t) for t in range(6, 15)))

    def test_short_outage_does_not_arm(self):
        cycle = self.cycle()
        self.assertFalse(cycle.sample(False, 0))
        self.assertFalse(any(cycle.sample(True, t) for t in range(1, 8)))

    def test_unknown_interrupts_recovery(self):
        cycle = self.cycle()
        for t, online in [(0, False), (2, False), (3, True), (4, None), (5, True), (7, True)]:
            self.assertFalse(cycle.sample(online, t))

    def test_recovery_flap_requires_new_stability(self):
        cycle = self.cycle()
        for t, online in [(0, False), (2, False), (3, True), (4, False), (5, True), (7, True)]:
            self.assertFalse(cycle.sample(online, t))

    def test_long_sampling_gap_discards_outage(self):
        cycle = self.cycle()
        cycle.sample(False, 0)
        cycle.sample(False, 2)
        self.assertFalse(cycle.sample(True, 30))
        self.assertFalse(cycle.sample(True, 32))

    def test_cooldown_cannot_be_bypassed_with_toggle(self):
        cycle = self.cycle()
        self.assertTrue(self.recovery(cycle)[-1])
        cycle.enable(False)
        cycle.enable(True)
        self.assertFalse(self.recovery(cycle, 6)[-1])
        self.assertTrue(self.recovery(cycle, 12)[-1])

    def test_disable_cancels_pending_recovery(self):
        cycle = self.cycle()
        cycle.sample(False, 0)
        cycle.sample(False, 2)
        cycle.sample(True, 3)
        cycle.enable(False)
        cycle.sample(True, 4)
        cycle.enable(True)
        self.assertFalse(cycle.sample(True, 5))

    def controller_recovery(self, readiness, stale=False):
        actuator = MockActuator()
        controller = mod.Controller(TARGET, self.cycle(), actuator)
        for t, online in [(0, False), (2, False), (3, True), (5, True)]:
            controller.accept(mod.Observation(online, readiness, t - 4 if stale else t), t)
        return controller, actuator

    def test_mock_resume_after_verified_guards(self):
        controller, actuator = self.controller_recovery(ready())
        self.assertEqual(len(actuator.calls), 1)
        self.assertEqual(controller.label, "Fixture resume accepted")
        controller.accept(mod.Observation(True, ready(), 6), 6)
        self.assertEqual(len(actuator.calls), 1)

    def test_each_unknown_or_false_guard_blocks(self):
        for field in mod.Readiness.__dataclass_fields__:
            if field in ("target", "command_pending", "composer_idle", "desktop_idle", "goal_id", "stall_kind", "incident_id"):
                continue
            for value in (False, None):
                with self.subTest(field=field, value=value):
                    controller, actuator = self.controller_recovery(replace(ready(), **{field: value}))
                    self.assertEqual(actuator.calls, [])
                    self.assertIn("Blocked", controller.label)

    def test_all_target_identity_fields_are_pinned(self):
        for field in TARGET.__dataclass_fields__:
            value = TARGET.tui_pid + 1 if field == "tui_pid" else "changed"
            _, actuator = self.controller_recovery(replace(ready(), target=replace(TARGET, **{field: value})))
            self.assertEqual(actuator.calls, [])

    def test_stale_observations_never_dispatch(self):
        _, actuator = self.controller_recovery(ready(), stale=True)
        self.assertEqual(actuator.calls, [])

    def test_faulted_actuator_consumes_cycle(self):
        actuator = MockActuator()
        def fail(*args):
            actuator.calls.append(args)
            raise RuntimeError("fixture")
        actuator.resume = fail
        controller = mod.Controller(TARGET, self.cycle(), actuator)
        for t, online in [(0, False), (2, False), (3, True), (5, True), (6, True)]:
            controller.accept(mod.Observation(online, ready(), t), t)
        self.assertEqual(len(actuator.calls), 1)

    def test_internet_probe_both_success_mixed_and_failures(self):
        for outputs, expected in [(["204", "200"], True), (["204", "500"], None),
                                  (["500", "500"], False)]:
            with patch.object(mod, "command", side_effect=outputs) as call:
                self.assertIs(mod.internet_online(), expected)
                for args in call.call_args_list:
                    self.assertIn("--max-time", args.args[0])
                    self.assertIn("--noproxy", args.args[0])
        with patch.object(mod, "command", side_effect=OSError):
            self.assertFalse(mod.internet_online())

    def test_invalid_time_and_duration_rejected(self):
        with self.assertRaises(ValueError):
            mod.ReconnectCycle(outage_seconds=float("nan"))
        cycle = self.cycle()
        cycle.sample(True, 2)
        with self.assertRaises(ValueError):
            cycle.sample(False, 1)

    def test_ready_deferred_recovery_stays_pending_then_dispatches(self):
        controller, actuator = self.controller_recovery(replace(ready(), draft_empty=False))
        self.assertEqual(actuator.calls, [])
        self.assertIn("Recovery pending", controller.label)
        controller.accept(mod.Observation(True, ready(), 6), 6)
        self.assertEqual(len(actuator.calls), 1)
        controller.accept(mod.Observation(True, ready(), 7), 7)
        self.assertEqual(len(actuator.calls), 1)

    def test_deferred_recovery_expires_without_effect(self):
        controller, actuator = self.controller_recovery(replace(ready(), idle=False))
        controller.pending_seconds = 120
        for t in range(6, 129):
            controller.accept(mod.Observation(True, replace(ready(), idle=False), t), t)
        controller.accept(mod.Observation(True, ready(), 129), 129)
        self.assertEqual(actuator.calls, [])

    def test_deferred_recovery_off_cancellation(self):
        controller, actuator = self.controller_recovery(replace(ready(), idle=False))
        controller.cycle.enable(False)
        controller.accept(mod.Observation(True, ready(), 6), 6)
        controller.cycle.enable(True)
        controller.accept(mod.Observation(True, ready(), 7), 7)
        self.assertEqual(actuator.calls, [])

    def test_stable_readiness_required(self):
        actuator = MockActuator()
        controller = mod.Controller(TARGET, self.cycle(), actuator, ready_seconds=3)
        for t, online in [(0, False), (2, False), (3, True), (5, True), (6, True)]:
            controller.accept(mod.Observation(online, ready(), t), t)
        self.assertEqual(actuator.calls, [])
        controller.accept(mod.Observation(True, ready(), 8), 8)
        self.assertEqual(len(actuator.calls), 1)


class VisibleComposerTests(unittest.TestCase):
    def text(self, suffix="Ask Codex to do anything", before="■ Network connection failed\n", tail="\n? for shortcuts\n"):
        return before + "› " + suffix + tail, len(before) + 2

    def test_visible_empty_placeholder_candidate(self):
        text, caret = self.text()
        composer = mod.parse_composer(text, caret)
        self.assertTrue(composer.empty and composer.idle and composer.no_modal and composer.interruption)

    def test_draft_whitespace_multiline_clipped_and_unknown_footer_reject(self):
        cases = [("my draft", "\n"), ("", "\n"), (" ", "\n"),
                 ("Ask Codex to do anything", "\nsecond draft row\n"),
                 ("Ask Codex to do anything", "\nunknown footer\n")]
        for suffix, tail in cases:
            with self.subTest(suffix=suffix, tail=tail):
                self.assertFalse(mod.parse_composer(*self.text(suffix, tail=tail)).empty)

    def test_busy_approval_attachment_and_wrong_caret_reject(self):
        for marker in ["Working (esc to interrupt)", "Approve this command?", "image attached"]:
            text, caret = self.text(before="■ Network failed\n" + marker + "\n")
            parsed = mod.parse_composer(text, caret)
            self.assertFalse(parsed.idle and parsed.no_modal)
        text, caret = self.text()
        self.assertFalse(mod.parse_composer(text, caret + 3).empty)

    def test_network_word_in_old_prose_does_not_authorize(self):
        self.assertFalse(mod.parse_composer(*self.text(before="Discussion of network design\n")).interruption)

    def test_typed_command_requires_exact_buffer_and_end_caret(self):
        text, caret = self.text("/goal resume")
        self.assertTrue(mod.parse_composer(text, caret + len("/goal resume"), "/goal resume").empty)
        self.assertFalse(mod.parse_composer(text, caret, "/goal resume").empty)
        text, caret = self.text("/goal resume EXTRA")
        self.assertFalse(mod.parse_composer(text, caret + len("/goal resume EXTRA"), "/goal resume").empty)
        for changed in ["/goal resume ", "/goal resume\t", "/goal resume  "]:
            text, caret = self.text(changed)
            self.assertFalse(mod.parse_composer(text, caret + len(changed), "/goal resume").empty)

    def test_activity_spinner_does_not_change_stable_title(self):
        self.assertEqual(mod.stable_title("⠋ Codex session"), mod.stable_title("⠙ Codex session"))
        self.assertNotEqual(mod.stable_title("⠋ Codex session"), mod.stable_title("⠋ Different session"))

    def test_uppercase_gpt_footer_keeps_input_comparison_exact(self):
        footer = "\nGPT-6-Astra extra high · /fixture/project\n"
        text, caret = self.text(tail=footer)
        parsed = mod.parse_composer(text, caret)
        self.assertTrue(parsed.empty and parsed.idle and parsed.no_modal and parsed.interruption)
        text, caret = self.text("/goal resume", tail=footer)
        self.assertTrue(mod.parse_composer(text, caret + len("/goal resume"), "/goal resume").empty)
        text, caret = self.text("/GOAL resume", tail=footer)
        self.assertFalse(mod.parse_composer(text, caret + len("/GOAL resume"), "/goal resume").empty)

    def test_exhausted_retry_history_does_not_hide_terminal_failure(self):
        text, caret = self.text(before="Reconnecting... 5/5\n■ stream disconnected before completion: error sending request\n")
        parsed = mod.parse_composer(text, caret)
        self.assertTrue(parsed.empty and parsed.idle and parsed.no_modal and parsed.interruption)

    def test_current_busy_below_old_error_still_blocks(self):
        for busy in ["Working (esc to interrupt)", "Reconnecting... 1/5", "Thinking..."]:
            text, caret = self.text(before="■ stream disconnected before completion: error sending request\n" + busy + "\n")
            self.assertFalse(mod.parse_composer(text, caret).idle)
        text, caret = self.text(before="Working (esc to interrupt)\n■ stream disconnected before completion: error sending request\n")
        self.assertTrue(mod.parse_composer(text, caret).idle)

    def test_nonerror_prose_cannot_finish_a_busy_retry(self):
        text, caret = self.text(before="Reconnecting... 5/5\nDiscussion of network connection failed errors\n")
        parsed = mod.parse_composer(text, caret)
        self.assertFalse(parsed.idle or parsed.interruption)

    def test_recovery_pipeline_after_retry_history_then_later_new_run_busy(self):
        actuator = MockActuator()
        cycle = mod.ReconnectCycle(outage_seconds=2, recovery_seconds=2, cooldown_seconds=10)
        cycle.enable(True)
        controller = mod.Controller(TARGET, cycle, actuator)
        text = "Reconnecting... 5/5\n■ stream disconnected before completion: error sending request\n› Ask Codex to do anything\nGPT-6-Astra extra high · /fixture/project\n"
        terminal = mod.parse_composer(text, text.index("›") + 2)
        qualified = replace(ready(), idle=terminal.idle, draft_empty=terminal.empty,
                            no_modal=terminal.no_modal, goal_needs_resume=terminal.interruption)
        for t, online in [(0, False), (2, False), (3, True), (5, True)]:
            controller.accept(mod.Observation(online, qualified, t), t)
        self.assertEqual(len(actuator.calls), 1)
        text = "■ stream disconnected before completion: error sending request\nWorking (esc to interrupt)\n› Ask Codex to do anything\nGPT-6-Astra extra high · /fixture/project\n"
        new_run = mod.parse_composer(text, text.index("›") + 2)
        self.assertFalse(new_run.idle)
        for t, online in [(12, False), (14, False), (15, True), (17, True)]:
            controller.accept(mod.Observation(online, replace(qualified, idle=new_run.idle), t), t)
        self.assertEqual(len(actuator.calls), 1)


class X11AdapterTests(unittest.TestCase):
    def adapter(self, readies=None, disable_after=None, active="100"):
        target = replace(TARGET, window_id="100")
        values = iter(readies or [replace(ready(), target=target)] * 3)
        calls = []
        enabled = [True]
        def runner(args):
            calls.append(args)
            if disable_after is not None and len(calls) == disable_after:
                enabled[0] = False
            if args[1] == "getactivewindow":
                return active
            return "fixture"
        adapter = mod.X11Actuator(lambda **kwargs: next(values), lambda: enabled[0], runner)
        return adapter, target, calls

    def test_real_effect_sequence_uses_literal_command_and_return(self):
        adapter, target, calls = self.adapter()
        result = adapter.resume(target, replace(ready(), target=target))
        self.assertIn("Sent /goal resume", result)
        self.assertIn(["wmctrl", "-ia", target.window_id], calls)
        self.assertIn(["xdotool", "type", "--delay", "0", "--", "/goal resume"], calls)
        self.assertIn(["xdotool", "key", "Return"], calls)
        self.assertFalse(any("Escape" in command or "ctrl+a" in command for command in calls))

    def test_changed_draft_after_focus_has_no_typing(self):
        target = replace(TARGET, window_id="100")
        adapter, target, calls = self.adapter([
            replace(ready(), target=target), replace(ready(), target=target, draft_empty=False)])
        adapter.resume(target, replace(ready(), target=target))
        self.assertFalse(any("type" in command or "key" in command for command in calls))

    def test_off_after_activation_has_no_typing(self):
        adapter, target, calls = self.adapter(disable_after=3)
        adapter.resume(target, replace(ready(), target=target))
        self.assertFalse(any("type" in command or "key" in command for command in calls))

    def test_off_after_typing_never_presses_return(self):
        adapter, target, calls = self.adapter(disable_after=5)
        result = adapter.resume(target, replace(ready(), target=target))
        self.assertIn("unsubmitted", result)
        self.assertFalse(any("key" in command for command in calls))

    def test_focus_mismatch_never_types(self):
        adapter, target, calls = self.adapter(active="200")
        adapter.resume(target, replace(ready(), target=target))
        self.assertFalse(any("type" in command or "key" in command for command in calls))

    def test_paused_before_outage_never_binds_recovery(self):
        observer = object.__new__(mod.LiveObserver)
        observer.target, observer.codex_dir = TARGET, Path("/fixture")
        observer.reset_cycle()
        active = mod.Goal("goal-id", "active", None, 0, 0, False)
        with patch.object(mod, "internet_online", side_effect=[True, False, True]), \
                patch.object(mod, "read_goal", side_effect=[replace(active, status="paused"), active, active]), \
                patch.object(observer, "readiness", return_value=mod.Readiness()):
            for _ in range(3):
                observer.connectivity.next_check = 0
                observer.observe()
        self.assertIsNone(observer.outage_goal)
        self.assertTrue(observer.pause_seen)

    def test_no_outage_baseline_on_cold_start_offline(self):
        observer = object.__new__(mod.LiveObserver)
        observer.target, observer.codex_dir = TARGET, Path("/fixture")
        observer.reset_cycle()
        active = mod.Goal("goal-id", "active", None, 0, 0, False)
        with patch.object(mod, "internet_online", side_effect=[False, False, True]), \
                patch.object(mod, "read_goal", return_value=active), \
                patch.object(observer, "readiness", return_value=mod.Readiness()):
            for _ in range(3):
                observer.connectivity.next_check = 0
                observer.observe()
        self.assertIsNone(observer.outage_goal)

    def test_live_readiness_rejects_pause_limit_complete_and_busy(self):
        observer = object.__new__(mod.LiveObserver)
        observer.target, observer.codex_dir = TARGET, Path("/fixture")
        observer.binding = mod.TerminalBinding(":fixture", "/window", "/frame", "/tab", "/terminal")
        observer.outage_goal, observer.pause_seen = "goal-id", False
        observer.baseline_goal = None
        observer.current_goal_id, observer.protected_goals, observer.goal_epoch = "goal-id", set(), 0
        for status in ["paused", "budget_limited", "usage_limited", "complete"]:
            observer.pause_seen = False
            observer.protected_goals.clear()
            with self.subTest(status=status), \
                    patch.object(observer, "identity_ok", return_value=True), \
                    patch.object(mod, "read_goal", return_value=mod.Goal("goal-id", status, None, 0, 0, False)), \
                    patch.object(mod, "visible_composer", return_value=mod.Composer(True, True, True, True)), \
                    patch.object(mod, "resumable_turn", return_value=("transport", "fixture-turn")), \
                    patch.object(mod, "desktop_idle_ms", return_value=30001):
                self.assertIsNotNone(observer.readiness().blocker(TARGET))
        observer.pause_seen = False
        observer.protected_goals.clear()
        with patch.object(observer, "identity_ok", return_value=True), \
                patch.object(mod, "read_goal", return_value=mod.Goal("goal-id", "active", 10, 10, 0, False)), \
                patch.object(mod, "visible_composer", return_value=mod.Composer(True, False, True, True)), \
                patch.object(mod, "resumable_turn", return_value=("transport", "fixture-turn")), \
                    patch.object(mod, "desktop_idle_ms", return_value=30001):
            self.assertIsNotNone(observer.readiness().blocker(TARGET))

    def test_only_recovery_owned_blocked_transport_goal_is_eligible(self):
        observer = object.__new__(mod.LiveObserver)
        observer.target, observer.codex_dir = TARGET, Path("/fixture")
        observer.binding = mod.TerminalBinding(":fixture", "/window", "/frame", "/tab", "/terminal")
        observer.outage_goal, observer.pause_seen = "goal-id", False
        observer.baseline_goal = None
        observer.current_goal_id, observer.protected_goals, observer.goal_epoch = "goal-id", set(), 0
        goal = mod.Goal("goal-id", "blocked", None, 0, 0, False)
        with patch.object(observer, "identity_ok", return_value=True), \
                patch.object(mod, "read_goal", return_value=goal), \
                patch.object(mod, "resumable_turn", return_value=("transport", "fixture-turn")), \
                    patch.object(mod, "desktop_idle_ms", return_value=30001):
            with patch.object(mod, "visible_composer", return_value=mod.Composer(True, True, True, True)):
                self.assertIsNone(observer.readiness().blocker(TARGET))
                observer.outage_goal = None
                self.assertIsNotNone(observer.readiness().blocker(TARGET))
            observer.outage_goal = "goal-id"
            with patch.object(mod, "visible_composer", return_value=mod.Composer(True, True, True, False)), \
                    patch.object(mod, "resumable_turn", return_value=(None, "fixture-turn")):
                self.assertIsNotNone(observer.readiness().blocker(TARGET))

    def test_single_tab_actions_reject_switchable_or_unknown_windows(self):
        actions = {name: (False, "", []) for name in
                   ("tabs-menu", "tab-switch-left", "tab-switch-right", "tab-detach")}
        actions["active-tab"] = (False, "i", [0])
        self.assertTrue(mod.single_tab_actions(actions))
        for name in actions:
            changed = dict(actions)
            changed[name] = (True, "", [0])
            self.assertFalse(mod.single_tab_actions(changed))
        changed = dict(actions)
        changed["active-tab"] = (False, "i", [1])
        self.assertFalse(mod.single_tab_actions(changed))
        self.assertFalse(mod.single_tab_actions({}))

    def test_replaced_original_widget_blocks_composer(self):
        binding = mod.TerminalBinding(":fixture", "/window", "/frame", "/tab", "/terminal")
        for field in binding.__dataclass_fields__:
            with self.subTest(field=field), patch.object(
                    mod, "terminal_context", return_value=(replace(binding, **{field: "changed"}), object())):
                with self.assertRaises(ValueError):
                    mod.visible_composer("100", expected_binding=binding)

    def test_gi_text_interface_bypasses_accessible_get_text_collision(self):
        binding = mod.TerminalBinding(":fixture", "/window", "/frame", "/tab", "/terminal")
        text = "■ Network connection failed\n› Ask Codex to do anything\n? for shortcuts\n"
        caret = text.index("›") + 2
        class Accessible:
            def get_text(self):
                raise AssertionError("Wrong Accessible.get_text method")
        class TextInterface:
            @staticmethod
            def get_character_count(accessible):
                return len(text)
            @staticmethod
            def get_text(accessible, start, end):
                return text[start:end]
            @staticmethod
            def get_caret_offset(accessible):
                return caret
        atspi = type("Atspi", (), {"Text": TextInterface})
        with patch.object(mod, "terminal_context", return_value=(binding, Accessible())), \
                patch.object(mod, "gi_modules", return_value=(atspi, None, None)):
            result = mod.visible_composer("100", expected_binding=binding)
        self.assertTrue(result.empty and result.idle and result.interruption)

    def test_idle_unavailable_fails_closed_and_optional_fallback_works(self):
        with patch.object(mod, "gi_modules", side_effect=ImportError), \
                patch.object(mod.shutil, "which", return_value=None):
            with self.assertRaises(ValueError):
                mod.desktop_idle_ms()
        with patch.object(mod, "gi_modules", side_effect=ImportError), \
                patch.object(mod.shutil, "which", return_value="/fixture/xprintidle"), \
                patch.object(mod, "command", return_value="30001"):
            self.assertEqual(mod.desktop_idle_ms(), 30001)

    def reflected_adapter(self, after_typing):
        target = replace(TARGET, window_id="100")
        verified = replace(ready(), target=target, command_pending=False)
        calls, clock = [], [0.0]
        observations = iter([verified, verified] + after_typing)
        last = after_typing[-1]
        def fresh(**kwargs):
            return next(observations, last)
        def runner(args):
            calls.append(args)
            return "100" if args[1] == "getactivewindow" else "fixture"
        def sleep(seconds):
            clock[0] += seconds
        adapter = mod.X11Actuator(fresh, lambda: True, runner, lambda: clock[0], sleep)
        return adapter, target, verified, calls, clock

    def test_partial_reflection_waits_once_without_retyping(self):
        target = replace(TARGET, window_id="100")
        complete = replace(ready(), target=target, command_pending=False)
        pending = replace(complete, draft_empty=False, command_pending=True)
        adapter, target, verified, calls, clock = self.reflected_adapter([pending, complete])
        self.assertIn("Sent /goal resume", adapter.resume(target, verified))
        self.assertEqual(sum("type" in call for call in calls), 1)
        self.assertEqual(sum("key" in call for call in calls), 1)
        self.assertEqual(clock[0], 0.05)

    def test_pending_reflection_times_out_without_enter(self):
        target = replace(TARGET, window_id="100")
        pending = replace(ready(), target=target, draft_empty=False, command_pending=True)
        adapter, target, verified, calls, clock = self.reflected_adapter([pending])
        self.assertIn("timed out", adapter.resume(target, verified))
        self.assertLessEqual(clock[0], 1)
        self.assertFalse(any("key" in call for call in calls))

        self.assertEqual(sum("type" in call for call in calls), 1)

    def test_unexpected_input_never_waits_for_later_matching_input(self):
        target = replace(TARGET, window_id="100")
        complete = replace(ready(), target=target, command_pending=False)
        changed = replace(complete, draft_empty=False)
        adapter, target, verified, calls, clock = self.reflected_adapter([changed, complete])
        self.assertIn("Blocked: draft empty", adapter.resume(target, verified))
        self.assertEqual(clock[0], 0)
        self.assertFalse(any("key" in call for call in calls))

    def test_reflection_does_not_bypass_another_guard(self):
        target = replace(TARGET, window_id="100")
        pending = replace(ready(), target=target, draft_empty=False, command_pending=True, no_modal=False)
        adapter, target, verified, calls, clock = self.reflected_adapter([pending])
        self.assertIn("Blocked: no modal", adapter.resume(target, verified))
        self.assertEqual(clock[0], 0)
        self.assertFalse(any("key" in call for call in calls))


class TransitionDiagnosticTests(unittest.TestCase):
    def test_identical_state_has_one_timestamped_entry_and_change_has_next(self):
        with tempfile.TemporaryDirectory() as task_temp:
            path = Path(task_temp) / "transitions.jsonl"
            logger = mod.TransitionDiagnostics(path)
            state = {"event": "sample", "phase": "watching", "online": True,
                     "reason": "composer_busy", "composer_idle": False}
            logger(state)
            logger(dict(state))
            rows = [json.loads(row) for row in path.read_text().splitlines()]
            self.assertEqual(len(rows), 1)
            self.assertIn("elapsed_seconds", rows[0])
            self.assertNotIn("elapsed_seconds", state)
            logger(dict(state, online=False))
            rows = [json.loads(row) for row in path.read_text().splitlines()]
            self.assertEqual(len(rows), 2)
            self.assertIs(rows[0]["online"], True)
            self.assertIs(rows[1]["online"], False)
            self.assertIn("elapsed_seconds", rows[1])

    def test_reports_composer_and_desktop_idle_separately(self):
        self.assertEqual(replace(ready(), idle=False, composer_idle=False, desktop_idle=True).reason_code(TARGET), "composer_busy")
        self.assertEqual(replace(ready(), idle=False, composer_idle=False, desktop_idle=True).blocker(TARGET), "Waiting: Codex is working")
        self.assertEqual(replace(ready(), idle=False, composer_idle=True, desktop_idle=False).reason_code(TARGET), "desktop_recent_input")

    def test_trace_distinguishes_gap_unknown_and_expired_pending(self):
        events = []
        cycle = mod.ReconnectCycle(outage_seconds=2, recovery_seconds=2, max_sample_gap=5)
        cycle.enable(True)
        controller = mod.Controller(TARGET, cycle, MockActuator(), pending_seconds=5, trace=events.append)
        blocked = replace(ready(), idle=False, composer_idle=False, desktop_idle=True)
        for t, online in [(0, False), (2, False), (3, True), (5, True), (7, True), (9, True), (11, True)]:
            controller.accept(mod.Observation(online, blocked, t), t)
        self.assertTrue(any(event["event"] == "pending_expired" for event in events))
        controller.accept(mod.Observation(None, blocked, 12), 12)
        self.assertIsNone(events[-1]["online"])
        controller.accept(mod.Observation(True, blocked, 30), 30)
        self.assertTrue(events[-1]["sample_gap"])
        controller.accept(mod.Observation(True, blocked, 25), 31)
        self.assertTrue(events[-1]["stale_observation"])

    def test_rotates_deduplicates_and_rejects_unrecognized_text(self):
        with tempfile.TemporaryDirectory() as task_temp:
            path = Path(task_temp) / "transitions.jsonl"
            logger = mod.TransitionDiagnostics(path, max_bytes=1024)
            for i in range(100):
                state = {"event": "sample", "phase": "watching", "online": bool(i % 2),
                         "reason": "composer_busy", "composer_idle": False,
                         "secret": "synthetic unrecognized text", "target": "synthetic thread"}
                logger(state)
                logger(state)
            files = list(Path(task_temp).iterdir())
            self.assertEqual(len(files), 2)
            for file in files:
                self.assertLessEqual(file.stat().st_size, 1024)
                data = file.read_text()
                self.assertNotIn("synthetic", data)
                for row in data.splitlines():
                    parsed = json.loads(row)
                    self.assertEqual(parsed["reason"], "composer_busy")


class GoalLatchTests(unittest.TestCase):
    def observer(self):
        observer = object.__new__(mod.LiveObserver)
        observer.reset_cycle()
        return observer

    def goal(self, identifier, status="active"):
        return mod.Goal(identifier, status, None, 0, 0, False)

    def test_new_online_goal_rearms_completion_without_action(self):
        observer = self.observer()
        observer.track_goal(self.goal("old", "complete"), True)
        observer.outage_goal = "old"
        observer.track_goal(self.goal("new"), True)
        self.assertFalse(observer.pause_seen)
        self.assertEqual(observer.baseline_goal, "new")
        self.assertIsNone(observer.outage_goal)
        self.assertIn("old", observer.protected_goals)
        epoch = observer.goal_epoch
        observer.track_goal(self.goal("new"), True)
        self.assertEqual(observer.goal_epoch, epoch)

    def test_same_goal_protection_survives_active_and_cycle_reset(self):
        for status in ["paused", "budget_limited", "usage_limited", "complete"]:
            observer = self.observer()
            observer.track_goal(self.goal("old", status), True)
            observer.track_goal(self.goal("old"), True)
            self.assertTrue(observer.pause_seen)
            self.assertIsNone(observer.baseline_goal)
            observer.reset_cycle()
            observer.track_goal(self.goal("old"), True)
            self.assertTrue(observer.pause_seen)

    def test_offline_or_unknown_change_cannot_inherit_recovery(self):
        for online in [False, None]:
            observer = self.observer()
            observer.track_goal(self.goal("old"), True)
            observer.outage_goal = "old"
            observer.track_goal(self.goal("new"), online)
            self.assertIsNone(observer.baseline_goal)
            self.assertIsNone(observer.outage_goal)
            epoch = observer.goal_epoch
            observer.track_goal(self.goal("new"), True)
            self.assertEqual(observer.baseline_goal, "new")
            self.assertGreater(observer.goal_epoch, epoch)

    def test_new_epoch_cancels_pending_preserves_cooldown_and_requires_future_outage(self):
        cycle = mod.ReconnectCycle(outage_seconds=2, recovery_seconds=2, cooldown_seconds=10)
        cycle.enable(True)
        actuator = MockActuator()
        controller = mod.Controller(TARGET, cycle, actuator)
        blocked = replace(ready(), draft_empty=False)
        for t, online in [(0, False), (2, False), (3, True), (5, True)]:
            controller.accept(mod.Observation(online, blocked, t, 1), t)
        self.assertIsNotNone(controller.pending_since)
        controller.accept(mod.Observation(True, ready(), 6, 2), 6)
        self.assertIsNone(controller.pending_since)
        self.assertEqual(cycle.last_attempt, 5)
        self.assertEqual(actuator.calls, [])
        for t in [7, 8]:
            controller.accept(mod.Observation(True, ready(), t, 2), t)
        self.assertEqual(actuator.calls, [])
        for t, online in [(16, False), (18, False), (19, True), (21, True), (22, True)]:
            controller.accept(mod.Observation(online, ready(), t, 2), t)
        self.assertEqual(len(actuator.calls), 1)

    def test_goal_change_after_typing_leaves_command_unsubmitted(self):
        target = replace(TARGET, window_id="100")
        before = replace(ready(), target=target, goal_id="old")
        after = replace(before, goal_id="new")
        values = iter([before, before, after])
        calls = []
        def runner(args):
            calls.append(args)
            return "100" if args[1] == "getactivewindow" else "fixture"
        actuator = mod.X11Actuator(lambda **kwargs: next(values), lambda: True, runner)
        result = actuator.resume(target, before)
        self.assertIn("goal changed", result)
        self.assertEqual(sum("type" in args for args in calls), 1)
        self.assertFalse(any("key" in args for args in calls))


class StallRecoveryTests(unittest.TestCase):
    def controller(self, **kwargs):
        cycle = mod.ReconnectCycle(outage_seconds=2, recovery_seconds=2, cooldown_seconds=60, max_sample_gap=12)
        cycle.enable(True)
        actuator = MockActuator()
        return mod.Controller(TARGET, cycle, actuator, **kwargs), actuator

    def sample(self, controller, now, online=True, readiness=None):
        controller.accept(mod.Observation(online, ready() if readiness is None else readiness, now), now)

    def test_actual_delayed_idle_retains_recovery_beyond_120_seconds(self):
        controller, actuator = self.controller()
        controller.cycle.max_sample_gap = 12
        for now, online in [(7978.7, False), (7984.8, False), (7989.7, True), (7997.4, True)]:
            self.sample(controller, now, online, replace(ready(), draft_empty=False))
        self.assertIsNotNone(controller.pending_since)
        self.sample(controller, 8117.8, readiness=replace(ready(), draft_empty=False))
        self.assertIsNotNone(controller.pending_since)
        self.sample(controller, 8206.2)
        self.assertEqual(len(actuator.calls), 1)
        self.sample(controller, 8208.2)
        self.assertEqual(len(actuator.calls), 1)

    def test_pending_unknown_offline_gap_and_explicit_pause(self):
        controller, actuator = self.controller()
        for now, online in [(0, False), (2, False), (3, True), (5, True)]:
            self.sample(controller, now, online, replace(ready(), draft_empty=False))
        for now, online in [(7, None), (40, False), (200, True)]:
            self.sample(controller, now, online, replace(ready(), draft_empty=False))
            self.assertIsNotNone(controller.pending_since)
        self.sample(controller, 202, readiness=replace(ready(), no_explicit_pause=False))
        self.assertIsNone(controller.pending_since)
        self.sample(controller, 204)
        self.assertFalse(actuator.calls)

    def test_online_transient_once_per_incident_and_cooldown(self):
        controller, actuator = self.controller(ready_seconds=3)
        transient = replace(ready(), stall_kind='transport', incident_id=('goal', 'turn'))
        for now in (0, 2, 4, 10, 100):
            self.sample(controller, now, readiness=transient)
        self.assertEqual(len(actuator.calls), 1)
        next_incident = replace(transient, incident_id=('goal', 'next'))
        self.sample(controller, 102, readiness=next_incident)
        self.sample(controller, 106, readiness=next_incident)
        self.assertEqual(len(actuator.calls), 2)
        third = replace(transient, incident_id=('goal', 'third'))
        for now in (108, 112):
            self.sample(controller, now, readiness=third)
        self.assertEqual(len(actuator.calls), 2)
        for now in (168,170,172):
            self.sample(controller, now, readiness=third)
        self.assertEqual(len(actuator.calls), 3)

    def test_active_idle_needs_30_seconds_and_busy_resets_debounce(self):
        controller, actuator = self.controller()
        idle = replace(ready(), stall_kind='active_idle', incident_id=('goal', 'completed'))
        for now in range(0,30,2):
            self.sample(controller, now, readiness=idle)
        self.assertFalse(actuator.calls)
        self.sample(controller, 30, readiness=replace(idle, idle=False))
        for now in range(32,62,2):
            self.sample(controller, now, readiness=idle)
        self.assertFalse(actuator.calls)
        self.sample(controller, 62, readiness=idle)
        self.assertEqual(len(actuator.calls), 1)
        self.sample(controller, 124, readiness=idle)
        self.assertEqual(len(actuator.calls), 1)

    def test_zero_input_effect_defer_requeues_but_partial_or_unknown_does_not(self):
        for result, retry in [("Deferred: target did not activate", True),
                              ("Deferred: command left unsubmitted; focus changed", False),
                              ("Deferred: X11 adapter failed; check target input", False)]:
            controller, actuator = self.controller()
            incident = replace(ready(), stall_kind='transport', incident_id=('goal','turn'))
            self.sample(controller, 0, readiness=incident)
            controller.effect_result(result, incident, 1)
            self.sample(controller, 2, readiness=incident)
            self.assertEqual(len(actuator.calls), 1)
            self.sample(controller, 62, readiness=incident)
            self.assertEqual(len(actuator.calls), 2 if retry else 1)

    def test_latest_overall_turn_typed_classes(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            with sqlite3.connect(path / 'thread_history_1.sqlite') as db:
                db.execute('CREATE TABLE thread_turns (thread_id TEXT, turn_id TEXT, status TEXT, error_json TEXT, rollout_ordinal INTEGER)')
                def row(status, info, misalignment=None):
                    db.execute('DELETE FROM thread_turns')
                    db.execute('INSERT INTO thread_turns VALUES (?,?,?,?,1)', ('thread','turn',status,json.dumps({'codexErrorInfo': info, 'misalignment': misalignment})))
                    db.commit()
                for info in ('serverOverloaded','flexUnavailable','internalServerError', {'responseStreamDisconnected': {'httpStatusCode':503}}):
                    row('failed', info)
                    self.assertEqual(mod.resumable_turn(path,'thread'), ('transport','turn'))
                for info in ('other','unauthorized','usageLimitExceeded','cyberPolicy', {'responseStreamDisconnected': {'httpStatusCode':429}}, {'httpConnectionFailed': {'httpStatusCode':401}}):
                    row('failed', info)
                    self.assertEqual(mod.resumable_turn(path,'thread'), (None,'turn'))
                row('failed','serverOverloaded',{})
                self.assertEqual(mod.resumable_turn(path,'thread'), (None,'turn'))
                row('failed','serverOverloaded')
                db.execute('INSERT INTO thread_turns VALUES (?,?,?,?,2)', ('thread','new','inProgress',None)); db.commit()
                self.assertEqual(mod.resumable_turn(path,'thread'), (None,'new'))
                row('interrupted','serverOverloaded')
                self.assertEqual(mod.resumable_turn(path,'thread'), (None,'turn'))
                row('completed', None)
                self.assertEqual(mod.resumable_turn(path,'thread'), ('active_idle','turn'))

    def test_other_stream_timeout_fallback_is_anchored_and_protected(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            with sqlite3.connect(path / 'thread_history_1.sqlite') as db:
                db.execute('CREATE TABLE thread_turns (thread_id TEXT, turn_id TEXT, status TEXT, error_json TEXT, rollout_ordinal INTEGER)')
                def check(message, expected=None, info='other', details=None, newer=False):
                    db.execute('DELETE FROM thread_turns')
                    error = {'codexErrorInfo':info, 'message':message, 'additionalDetails':details, 'misalignment':None}
                    db.execute('INSERT INTO thread_turns VALUES (?,?,?,?,1)', ('thread','turn','failed',json.dumps(error)))
                    if newer:db.execute('INSERT INTO thread_turns VALUES (?,?,?,?,2)', ('thread','running','inProgress',None))
                    db.commit()
                    self.assertEqual(mod.resumable_turn(path,'thread'),(expected,'running' if newer else 'turn'))
                recognized = 'Error running remote compact task: stream disconnected before completion: Transport error: timeout'
                check(recognized,'transport')
                for message in ('operation timed out', 'other failure', 'Historical note: '+recognized,
                                recognized.lower(), 'stream disconnected before completion: operation timed out',
                                'stream disconnected before completion: unknown failure',
                                recognized+'; unauthorized', recognized+'; policy refusal',
                                recognized+'; quota exceeded', recognized+'; HTTP 429',
                                recognized+'; user interrupted', recognized+'; context window exceeded',
                                recognized+'\nHTTP 403'):
                    check(message)
                check(recognized,info='unauthorized')
                check(recognized,details='unqualified details')
                check(recognized,newer=True)

    def test_production_observer_scheduler_and_controller_offline_30_second_cadence(self):
        observer = object.__new__(mod.LiveObserver)
        observer.target, observer.codex_dir = TARGET, Path('/fixture')
        observer.connectivity = mod.ConnectivitySchedule()
        observer.current_goal_id, observer.protected_goals, observer.goal_epoch = 'goal', set(), 0
        observer.baseline_goal, observer.outage_goal, observer.previous_online, observer.pause_seen = 'goal', None, True, False
        controller, actuator = self.controller()
        incident = replace(ready(), stall_kind='transport', incident_id=('goal','turn'))
        network_checks = []
        now = 0
        def network():
            network_checks.append(now)
            return now >= 60
        with patch.object(mod.time, 'monotonic', side_effect=lambda: now), patch.object(mod, 'internet_online', side_effect=network), patch.object(mod, 'read_goal', return_value=mod.Goal('goal','active',None,0,0,False)), patch.object(observer, 'readiness', return_value=incident):
            for now in range(0, 72, 2):
                controller.accept(observer.observe(), now)
        self.assertEqual(network_checks[:3], [0,30,60])
        self.assertEqual(len(actuator.calls), 1)


class IncidentBindingRegressionTests(unittest.TestCase):
    def controller(self):
        cycle = mod.ReconnectCycle(max_sample_gap=12)
        cycle.enable(True)
        actuator = MockActuator()
        return mod.Controller(TARGET, cycle, actuator, ready_seconds=3), actuator

    def sample(self, controller, now, incident, online=True, observed_at=None):
        controller.accept(mod.Observation(online, incident, now if observed_at is None else observed_at), now)

    def test_new_incident_and_kind_require_new_full_debounce(self):
        for change in ('incident', 'kind'):
            controller, actuator = self.controller()
            first = replace(ready(), goal_id='goal', stall_kind='active_idle', incident_id=('goal','A'))
            second = replace(first, incident_id=('goal','B')) if change == 'incident' else replace(first, stall_kind='transport')
            for now in range(0,28,2):
                self.sample(controller, now, first)
            self.sample(controller, 28, second)
            self.sample(controller, 30, second)
            self.assertFalse(actuator.calls, change)
            end = 58 if change == 'incident' else 32
            for now in range(32,end+1,2):
                self.sample(controller, now, second)
            self.assertEqual(len(actuator.calls), 1, change)

    def test_gap_stale_unknown_and_backwards_reset_ready_but_keep_pending(self):
        incident = replace(ready(), goal_id='goal', stall_kind='active_idle', incident_id=('goal','A'))
        for condition in ('gap','stale','unknown','backwards'):
            controller, actuator = self.controller()
            for now in range(0,28,2):
                self.sample(controller, now, incident)
            if condition == 'gap':
                start = 60
            else:
                start = 30
                if condition == 'stale':self.sample(controller,28,incident,observed_at=0)
                if condition == 'unknown':self.sample(controller,28,incident,online=None)
                if condition == 'backwards':self.sample(controller,24,incident)
            self.sample(controller,start,incident)
            self.assertFalse(actuator.calls,condition)
            self.assertIsNotNone(controller.pending_since,condition)
            for now in range(start+2,start+31,2):self.sample(controller,now,incident)
            self.assertEqual(len(actuator.calls),1,condition)

    def test_actuator_pins_incident_and_kind_before_type_and_enter(self):
        target = replace(TARGET, window_id='0x123')
        approved = replace(ready(), target=target, goal_id='goal', stall_kind='transport', incident_id=('goal','A'))
        for stage in ('activation','typing','enter'):
            for change in ('incident','kind'):
                calls=[]
                changed=replace(approved, incident_id=('goal','B')) if change=='incident' else replace(approved,stall_kind='active_idle')
                reads=0
                def fresh(**unused):
                    nonlocal reads
                    reads+=1
                    threshold={'activation':1,'typing':2,'enter':3}[stage]
                    return changed if reads>=threshold else approved
                def runner(args):
                    calls.append(args)
                    return '291' if 'getactivewindow' in args else 'fixture'
                result=mod.X11Actuator(fresh,lambda:True,runner).resume(target,approved)
                self.assertFalse(any('key' in args for args in calls),(stage,change))
                self.assertEqual(sum('type' in args for args in calls),1 if stage=='enter' else 0)
                if stage=='activation':self.assertFalse(any(args[0]=='wmctrl' for args in calls))
                self.assertTrue(result.startswith('Deferred:'),result)


class LiveMissRegressionTests(unittest.TestCase):
    def pipeline(self, before, message='request timed out', info='other',
                 turn_status='failed', goal_status='blocked', details=None, misalignment=None,
                 newer=False, protected=False, identity=True, prompt='Ask Codex to do anything',
                 token_budget=None, tokens_used=0):
        import sqlite3
        text=before+'› '+prompt+'\n? for shortcuts\n'
        composer=mod.parse_composer(text,text.index('›')+2)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            error={'codexErrorInfo':info,'message':message,'additionalDetails':details,'misalignment':misalignment}
            with sqlite3.connect(root/'goals_1.sqlite') as db:
                db.execute('CREATE TABLE thread_goals(thread_id,goal_id,status,token_budget,tokens_used)')
                db.execute('INSERT INTO thread_goals VALUES(?,?,?,?,?)',(TARGET.thread_id,'goal',goal_status,token_budget,tokens_used))
                db.execute('CREATE TABLE thread_goal_continuation_deferrals(thread_id)')
            with sqlite3.connect(root/'thread_history_1.sqlite') as db:
                db.execute('CREATE TABLE thread_turns(thread_id,turn_id,status,error_json,rollout_ordinal)')
                db.execute('INSERT INTO thread_turns VALUES(?,?,?,?,?)',(TARGET.thread_id,'turn',turn_status,json.dumps(error),1))
                if newer:
                    db.execute('INSERT INTO thread_turns VALUES(?,?,?,?,?)',(TARGET.thread_id,'new','inProgress',None,2))
            with sqlite3.connect(root/'queue_1.sqlite') as db:
                db.execute('CREATE TABLE queued_items(thread_id)')
            observer=object.__new__(mod.LiveObserver)
            observer.target,observer.codex_dir,observer.binding=TARGET,root,'fixture-binding'
            observer.reset_cycle()
            observer.current_goal_id,observer.baseline_goal='goal','goal'
            if protected:
                observer.protected_goals.add('goal')
            cycle=mod.ReconnectCycle();cycle.enable(True)
            actuator=MockActuator();controller=mod.Controller(TARGET,cycle,actuator,ready_seconds=3)
            with patch.object(observer,'identity_ok',return_value=identity),patch.object(mod,'visible_composer',return_value=composer),patch.object(mod,'desktop_idle_ms',return_value=40000),patch.object(mod,'internet_online',return_value=True),patch.object(mod.time,'monotonic') as clock:
                for now in range(0,12,2):
                    clock.return_value=now
                    controller.accept(observer.observe(),now)
            return len(actuator.calls),composer.idle

    def test_stale_interrupt_before_terminal_error_clears_through_real_pipeline(self):
        error='■ stream disconnected before completion: error sending request\n'
        calls,idle=self.pipeline('Working (esc to interrupt)\n'+error,info='serverOverloaded')
        self.assertTrue(idle)
        self.assertEqual(calls,1)
        for current in ('Working (esc to interrupt)','Reconnecting... 1/5','Thinking...'):
            calls,idle=self.pipeline(error+current+'\n',info='serverOverloaded')
            self.assertFalse(idle)
            self.assertEqual(calls,0)

    def test_exact_timeout_terminal_line_orders_use_joined_observer(self):
        error='■ request timed out\n'
        self.assertEqual(self.pipeline('Working (esc to interrupt)\n'+error), (1,True))
        self.assertEqual(self.pipeline(error+'Working (esc to interrupt)\n'), (0,False))
        for unknown in ('Discussion: request timed out\n', '■ request timed out; policy refusal\n'):
            self.assertEqual(self.pipeline('Working (esc to interrupt)\n'+unknown)[0],0)

    def test_bare_transport_timeout_recovers_through_real_pipeline(self):
        message='stream disconnected before completion: Transport error: timeout'
        error='■ '+message+'\n'
        self.assertEqual(self.pipeline('Working (esc to interrupt)\n'+error,
                                       message=message), (1,True))
        self.assertEqual(self.pipeline(error+'Working (esc to interrupt)\n',
                                       message=message), (0,False))

    def test_bare_transport_timeout_keeps_exact_match_and_protection(self):
        message='stream disconnected before completion: Transport error: timeout'
        error='■ '+message+'\n'
        for altered in ('Historical note: '+message, message.lower(), message+'\n',
                        message+'; unauthorized', message+'; policy refusal',
                        message+'; quota', message+'; user interrupted',
                        'operation timed out', 'unknown failure', None):
            with self.subTest(message=altered):
                self.assertEqual(self.pipeline(error,message=altered)[0],0)
        for changes in ({'info':'cyberPolicy'}, {'info':'unauthorized'}, {'info':None},
                        {'details':'extra diagnostic'}, {'details':{}}, {'misalignment':{}},
                        {'turn_status':'inProgress'}, {'turn_status':'interrupted'},
                        {'newer':True}, {'goal_status':'paused'}, {'goal_status':'complete'},
                        {'goal_status':'budget_limited'}, {'goal_status':'usage_limited'},
                        {'token_budget':10,'tokens_used':10}, {'protected':True},
                        {'identity':False}, {'prompt':'existing draft'}):
            with self.subTest(changes=changes):
                self.assertEqual(self.pipeline(error,message=message,**changes)[0],0)
        self.assertEqual(self.pipeline(error+'Approve this command?\n',message=message)[0],0)

    def test_exact_request_timeout_admits_but_protected_or_unknown_remain_blocked(self):
        error='■ stream disconnected before completion: error sending request\n'
        self.assertEqual(self.pipeline(error)[0],1)
        for changes in ({'message':'request timed out; HTTP 401'}, {'message':'unknown failure'},
                        {'message':'request timed out; policy refusal'}, {'message':'request timed out; quota'},
                        {'message':'request timed out; user interrupted'}, {'message':'Request timed out'},
                        {'info':'unauthorized'}, {'details':'unknown'}, {'misalignment':{}},
                        {'turn_status':'inProgress'}, {'turn_status':'interrupted'},
                        {'goal_status':'paused'}, {'goal_status':'complete'}):
            self.assertEqual(self.pipeline(error,**changes)[0],0,changes)
        self.assertEqual(self.pipeline(error+'Approve this command?\n')[0],0)


if __name__ == "__main__":
    unittest.main()
