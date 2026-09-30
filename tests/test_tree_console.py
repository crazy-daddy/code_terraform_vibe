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
        self.assertEqual(self.lines(), [("debug", "┏━ get_demands\n┃   iron gross=6\n┃   glass gross=2\nafter")])

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
        log.end()
        log.debug("y")
        log.end()
        log.flush()
        self.assertEqual(self.lines(), [("debug", "┏━ outer\n┃   ┏━ inner\n┃   ┃   x\n┃   y")])

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
        self.assertEqual(self.lines(), [("debug", "┏━ dbg"), ("info", "┃   ┏━ Info block"), ("info", "┃   ┗━ done")])

    def test_reset_drops_open_debug_blocks(self):
        log = self.make()
        log.start("leaks", level="debug")
        tree_console.reset_all()
        log.debug("after")
        log.flush()
        self.assertEqual(self.lines(), [("debug", "after")])


if __name__ == "__main__":
    unittest.main()
