"""Stub tests for lib/tree_console.py debug buffering and its ordering with swallowed()."""
import unittest

import tree_console
from harness import StubTestCase, swallow
from tree_console import TreeConsole


STAMP = "12:00:00 "


class ConsoleCase(StubTestCase):
    def make(self, **kwargs):
        return TreeConsole(console=self.world.console, module="buffer_test", **kwargs)

    def lines(self):
        """Console lines with the per-line game-time stamp removed."""
        return [(level, "\n".join(line.removeprefix(STAMP) for line in msg.split("\n")))
                for level, msg in self.world.console.lines]


class BufferingTests(ConsoleCase):
    def test_consecutive_debug_lines_become_one_message(self):
        log = self.make()
        log.debug("a")
        log.debug("b")
        log.debug("c")
        self.assertEqual(self.lines(), [])
        log.flush()
        self.assertEqual(self.lines(), [("debug", "a\nb\nc")])

    def test_info_flushes_pending_debug_first_and_keeps_order(self):
        log = self.make()
        log.debug("why 1")
        log.debug("why 2")
        log.print("outcome")
        log.debug("why 3")
        log.flush()
        self.assertEqual(self.lines(), [("debug", "why 1\nwhy 2"), ("info", "outcome"), ("debug", "why 3")])

    def test_warn_and_error_are_immediate(self):
        log = self.make()
        log.debug("before")
        log.level("warn").print("careful")
        self.assertEqual(self.lines(), [("debug", "before"), ("warn", "careful")])

    def test_outermost_end_flushes_and_lines_keep_their_indent(self):
        log = self.make()
        log.start("Outer")
        log.start("Inner")
        log.debug("deep")
        log.end("Inner done")
        log.debug("shallow")
        self.assertEqual([lv for lv, _ in self.lines()], ["info", "info", "debug", "info"])
        log.end("Outer done")
        self.assertEqual(self.lines()[-2:], [("debug", "┃   shallow"), ("info", "┗━ Outer done")])

    def test_reset_all_drops_indent_leaked_by_an_open_block(self):
        log = self.make()
        other = self.make()
        log.start("Leaks")
        other.start("Also leaks")
        tree_console.reset_all()
        log.print("after")
        other.print("after")
        self.assertEqual(self.lines()[-2:], [("info", "after"), ("info", "after")])

    def test_channel_change_splits_the_run(self):
        log = self.make()
        log.debug("x", channel="one")
        log.debug("y", channel="two")
        log.flush()
        self.assertEqual(len(self.lines()), 2)

    def test_trace_is_a_no_op_unless_verbose(self):
        log = self.make()
        log.trace("noise")
        log.flush()
        self.assertEqual(self.lines(), [])
        log.verbose = True
        log.trace("noise")
        log.flush()
        self.assertEqual(self.lines(), [("debug", "noise")])

    def test_module_level_trace_enables_trace(self):
        self.world.notebook.set(tree_console.LOG_LEVELS_KEY, {"buffer_test": "trace"})
        log = self.make()
        log.trace("noise")
        log.flush()
        self.assertEqual(self.lines(), [("debug", "noise")])

    def test_info_level_drops_debug_lines_and_blocks(self):
        self.world.notebook.set(tree_console.LOG_LEVELS_KEY, {"*": "info"})
        log = self.make()
        log.start("Plan", level="debug")
        log.debug("why")
        log.end("done")
        log.print("outcome")
        log.flush()
        self.assertEqual(self.lines(), [("info", "outcome")])

    def test_warn_level_drops_info_block_but_keeps_warn_inside(self):
        self.world.notebook.set(tree_console.LOG_LEVELS_KEY, {"*": "warn"})
        log = self.make()
        log.start("Trip")
        log.print("leg")
        log.level("warn").print("low battery")
        log.end("done")
        self.assertEqual(self.lines(), [("warn", "low battery")])

    def test_missing_levels_dict_is_seeded_with_debug(self):
        self.make()
        self.assertEqual(self.world.notebook.get(tree_console.LOG_LEVELS_KEY), {"*": "debug"})

    def test_existing_levels_dict_is_kept(self):
        self.world.notebook.set(tree_console.LOG_LEVELS_KEY, {"power": "trace"})
        self.make()
        self.assertEqual(self.world.notebook.get(tree_console.LOG_LEVELS_KEY), {"power": "trace"})

    def test_module_entry_beats_the_wildcard(self):
        self.world.notebook.set(tree_console.LOG_LEVELS_KEY, {"*": "info", "buffer_test": "debug"})
        log = self.make()
        log.debug("why")
        log.flush()
        self.assertEqual(self.lines(), [("debug", "why")])

    def test_size_cap_flushes_before_overflow(self):
        log = self.make()
        cap = tree_console._buffer_cap()
        chunk = "z" * (cap // 3)
        for _ in range(7):
            log.debug(chunk)
        log.flush()
        self.assertGreater(len(self.lines()), 1)
        for _, message in self.lines():
            self.assertLessEqual(len(message), cap)

    def test_single_oversized_line_is_truncated_to_the_cap(self):
        log = self.make()
        cap = tree_console._buffer_cap()
        log.debug("q" * (cap * 3))
        log.flush()
        self.assertLessEqual(len(self.lines()[0][1]), cap)

    def test_cap_is_read_from_the_overflow_message(self):
        limit_msg = "string length 200,000 exceeds the current limit of 100,000. This is already the highest budget."
        self.assertEqual(tree_console._cap_from_error(limit_msg), 20000)
        default_msg = "string length 200,000 exceeds the current limit of 10,000. Raise this limit in Settings."
        self.assertEqual(tree_console._cap_from_error(default_msg), 5000)
        self.assertEqual(tree_console._cap_from_error("no numbers here"), tree_console.FALLBACK_BUFFER_CHARS)

    def test_unbuffered_instance_prints_immediately(self):
        log = self.make(buffered=False)
        log.debug("now")
        self.assertEqual(self.lines(), [("debug", "now")])

    def test_shared_buffer_keeps_order_across_instances(self):
        first = self.make()
        second = TreeConsole(console=self.world.console, module="other")
        first.debug("one")
        second.debug("two")
        first.flush()
        self.assertEqual(self.lines(), [("debug", "one\ntwo")])

    def test_swallowed_flushes_pending_lines_before_it_prints(self):
        log = self.make()
        log.debug("earlier")
        swallow.swallowed("test.where", ValueError("boom"))
        self.assertEqual(self.lines()[0], ("debug", "earlier"))
        self.assertIn("[swallowed] test.where", self.lines()[1][1])


class BlockTests(ConsoleCase):
    def test_every_buffered_line_carries_its_own_timestamp(self):
        log = self.make()
        log.debug("a")
        log.debug("b")
        log.flush()
        self.assertEqual(self.world.console.lines, [("debug", f"{STAMP}a\n{STAMP}b")])

    def test_debug_block_indents_its_lines_under_one_header(self):
        log = self.make()
        log.start("get_demands", level="debug")
        log.debug("iron gross=6")
        log.debug("glass gross=2")
        log.end()
        log.debug("after")
        log.flush()
        self.assertEqual(self.lines(), [("debug", "┏━ get_demands\n┃   iron gross=6\n┃   glass gross=2\n┗━ END get_demands\nafter")])

    def test_idle_debug_block_prints_nothing(self):
        log = self.make()
        log.start("quiet", level="debug")
        log.trace("gated off")
        log.end()
        log.flush()
        self.assertEqual(self.lines(), [])

    def test_nested_debug_blocks_show_outer_header_first_and_only_once(self):
        log = self.make()
        log.start("outer", level="debug")
        log.start("inner", level="debug")
        log.debug("x")
        log.debug("x2")
        log.end()
        log.debug("y")
        log.end()
        log.flush()
        self.assertEqual(self.lines(), [("debug", "┏━ outer\n┃   ┏━ inner\n┃   ┃   x\n┃   ┃   x2\n┃   ┗━ END inner\n┃   y\n┗━ END outer")])

    def test_debug_block_end_with_message_writes_a_closing_line(self):
        log = self.make()
        log.start("job", level="debug")
        log.debug("step")
        log.end("done")
        log.flush()
        self.assertEqual(self.lines(), [("debug", "┏━ job\n┃   step\n┗━ done")])

    def test_debug_block_does_not_flush_buffer_at_outermost_end(self):
        log = self.make()
        log.start("one", level="debug")
        log.debug("a")
        log.end()
        log.start("two", level="debug")
        log.debug("b")
        log.end()
        self.assertEqual(self.lines(), [])
        log.flush()
        self.assertEqual(len(self.lines()), 1)

    def test_info_block_inside_debug_block_shows_debug_header_first(self):
        log = self.make()
        log.start("dbg", level="debug")
        log.start("Info block")
        log.end("done")
        log.end()
        log.flush()
        self.assertEqual(self.lines(), [("debug", "┏━ dbg"), ("info", "┃   ┏━ Info block"), ("info", "┃   ┗━ done"), ("debug", "┗━ END dbg")])

    def test_one_line_debug_block_collapses_to_a_single_line(self):
        log = self.make()
        log.start("get_demands", level="debug")
        log.debug("iron gross=6")
        log.end()
        log.flush()
        self.assertEqual(self.lines(), [("debug", "get_demands: iron gross=6")])

    def test_collapsed_line_keeps_entry_stamp_and_shows_elapsed_time(self):
        log = self.make()
        console = self.world.console
        log.start("job", level="debug")
        log.debug("only")
        console.time_of_day = "12:04:05"
        log.end()
        log.flush()
        self.assertEqual(console.lines, [("debug", "12:00:00 job: only (+4m05s)")])

    def test_short_elapsed_time_is_in_seconds_and_wraps_past_midnight(self):
        log = self.make()
        console = self.world.console
        console.time_of_day = "23:59:50"
        log.start("job", level="debug")
        log.debug("only")
        console.time_of_day = "00:00:05"
        log.end()
        log.flush()
        self.assertEqual(console.lines, [("debug", "23:59:50 job: only (+15s)")])

    def test_second_line_expands_the_held_first_line(self):
        log = self.make()
        log.start("job", level="debug")
        log.debug("one")
        log.debug("two")
        log.end()
        log.flush()
        self.assertEqual(self.lines(), [("debug", "┏━ job\n┃   one\n┃   two\n┗━ END job")])

    def test_header_is_stamped_with_the_held_lines_entry_time(self):
        log = self.make()
        console = self.world.console
        log.start("job", level="debug")
        log.debug("one")
        console.time_of_day = "12:00:30"
        log.debug("two")
        log.flush()
        self.assertEqual(console.lines, [("debug", "12:00:00 ┏━ job\n12:00:00 ┃   one\n12:00:30 ┃   two")])

    def test_nested_block_expands_the_held_line_before_it(self):
        log = self.make()
        log.start("outer", level="debug")
        log.debug("before")
        log.start("inner", level="debug")
        log.debug("inside")
        log.end()
        log.end()
        log.flush()
        self.assertEqual(self.lines(), [("debug", "┏━ outer\n┃   before\n┃   inner: inside\n┗━ END outer")])

    def test_collapsed_block_inside_a_block_is_indented(self):
        log = self.make()
        log.start("outer", level="debug")
        log.start("inner", level="debug")
        log.debug("inside")
        log.end()
        log.debug("after")
        log.end()
        log.flush()
        self.assertEqual(self.lines(), [("debug", "┏━ outer\n┃   inner: inside\n┃   after\n┗━ END outer")])

    def test_held_line_is_written_when_another_console_logs(self):
        log = self.make()
        other = TreeConsole(console=self.world.console, module="other")
        log.start("job", level="debug")
        log.debug("held")
        other.print("elsewhere")
        self.assertEqual(self.lines(), [("debug", "┏━ job\n┃   held"), ("info", "elsewhere")])

    def test_flush_and_reset_do_not_lose_a_held_line(self):
        log = self.make()
        log.start("job", level="debug")
        log.debug("held")
        log.flush()
        self.assertEqual(self.lines(), [("debug", "┏━ job\n┃   held")])
        log.reset()
        log.start("again", level="debug")
        log.debug("kept")
        tree_console.reset_all()
        log.flush()
        self.assertEqual(self.lines()[-1], ("debug", "┏━ again\n┃   kept"))

    def test_held_info_line_collapses_at_its_own_level(self):
        log = self.make()
        log.start("job", level="debug")
        log.print("Sent 3x iron")
        log.end()
        self.assertEqual(self.world.console.lines, [("info", f"{STAMP}job: Sent 3x iron")])

    def test_end_with_message_expands_a_held_line(self):
        log = self.make()
        log.start("job", level="debug")
        log.debug("one")
        log.end("done")
        log.flush()
        self.assertEqual(self.lines(), [("debug", "┏━ job\n┃   one\n┗━ done")])

    def test_warn_and_error_lines_are_not_indented(self):
        log = self.make()
        log.start("Block")
        log.level("warn").print("careful")
        log.level("error").print("broken")
        log.print("fine")
        log.end("done")
        self.assertEqual(self.lines(), [("info", "┏━ Block"), ("warn", "careful"), ("error", "broken"),
                                        ("info", "┃   fine"), ("info", "┗━ done")])

    def test_warn_end_line_keeps_its_close_marker(self):
        log = self.make()
        log.start("Block")
        log.level("warn").end("failed")
        self.assertEqual(self.lines()[-1], ("warn", "┗━ failed"))

    def test_reset_drops_open_debug_blocks(self):
        log = self.make()
        log.start("leaks", level="debug")
        tree_console.reset_all()
        log.debug("after")
        log.flush()
        self.assertEqual(self.lines(), [("debug", "after")])


class WrappedBlockTests(ConsoleCase):
    def test_run_returns_the_result_and_closes_the_block(self):
        log = self.make()

        def work():
            log.debug("a")
            log.debug("b")
            return 7

        self.assertEqual(log.run("job", work), 7)
        log.flush()
        self.assertEqual(self.lines(), [("debug", "┏━ job\n┃   a\n┃   b\n┗━ END job")])

    def test_run_block_with_one_line_collapses(self):
        log = self.make()
        log.run("job", lambda: log.debug("only"))
        log.flush()
        self.assertEqual(self.lines(), [("debug", "job: only")])

    def test_exception_closes_the_block_with_a_marker_and_is_raised_again(self):
        log = self.make()

        def work():
            log.debug("before")
            raise ValueError("bad input")

        with self.assertRaises(ValueError):
            log.run("job", work)
        log.debug("after")
        log.flush()
        self.assertEqual(self.lines(), [("debug", "┏━ job\n┃   before\n┗━ END job !! ValueError: bad input\nafter")])

    def test_exception_in_an_idle_block_still_shows_the_path(self):
        log = self.make()
        log.start("outer", level="debug")

        def work():
            raise KeyError("x")

        with self.assertRaises(KeyError):
            log.run("job", work)
        log.end()
        log.flush()
        self.assertEqual(self.lines(), [("debug", "┏━ outer\n┃   ┏━ job\n┃   ┗━ END job !! KeyError: 'x'\n┗━ END outer")])

    def test_exception_closes_blocks_left_open_inside(self):
        log = self.make()

        def work():
            log.start("inner", level="debug")
            log.debug("deep")
            raise ValueError("boom")

        with self.assertRaises(ValueError):
            log.run("job", work)
        log.flush()
        self.assertEqual(self.lines(), [("debug", "┏━ job\n┃   ┏━ inner\n┃   ┃   deep\n┃   ┗━ END inner !! ValueError: boom\n"
                                                  "┗━ END job !! ValueError: boom")])
        self.assertEqual(log._blocks, [])

    def test_info_run_writes_header_immediately(self):
        log = self.make()
        log.run("cycle", lambda: None, level="info")
        self.assertEqual(self.lines(), [("info", "┏━ cycle"), ("info", "┗━ END cycle")])

    def test_block_decorator_uses_the_function_name_and_keeps_it(self):
        log = self.make()

        @log.block()
        def plan(n):
            log.debug(f"n={n}")
            log.debug("done")
            return n * 2

        self.assertEqual(plan(3), 6)
        self.assertEqual(plan.__name__, "plan")
        log.flush()
        self.assertEqual(self.lines(), [("debug", "┏━ plan\n┃   n=3\n┃   done\n┗━ END plan")])

    def test_method_block_reads_self_log_and_label_callable(self):
        from tree_console import method_block
        test = self

        class Controller:
            name = "smelter_1"

            def __init__(self):
                self.log = test.make()

            @method_block(lambda self, target: f"[{self.name}] solve {target}")
            def solve(self, target):
                if target > 1:
                    self.log.debug("too high")
                    return "skip"
                return "ok"

        controller = Controller()
        self.assertEqual(controller.solve(2), "skip")
        self.assertEqual(controller.solve(1), "ok")
        log = controller.log
        log.flush()
        self.assertEqual(self.lines(), [("debug", "[smelter_1] solve 2: too high")])

    def test_method_block_without_log_runs_unwrapped(self):
        from tree_console import method_block

        class Bare:
            @method_block()
            def work(self):
                return 5

        self.assertEqual(Bare().work(), 5)


if __name__ == "__main__":
    unittest.main()
