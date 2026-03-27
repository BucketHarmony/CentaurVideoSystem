"""Tests for ParseTickLog node."""

import pytest
from nodes import ParseTickLog


class TestParseTickLog:
    def setup_method(self):
        self.node = ParseTickLog()

    def test_parse_valid_log(self, sample_tick_log):
        title, mood, monologue, best_quote, tick_num, goal, intent = \
            self.node.parse(str(sample_tick_log))

        assert title == "TICK 42"
        assert mood == "curious"
        assert tick_num == "42"
        assert "hallway" in monologue.lower()
        assert goal == "Reach the end of the hallway"
        assert intent == "Systematic forward exploration with wall-following"

    def test_parse_missing_file(self, tmp_path):
        result = self.node.parse(str(tmp_path / "nonexistent.md"))
        title, mood, monologue, best_quote, tick_num, goal, intent = result

        assert title == "TICK ???"
        assert mood == "unknown"
        assert tick_num == "0"

    def test_parse_empty_log(self, tmp_path):
        log = tmp_path / "tick_0099.md"
        log.write_text("# Empty tick\n\nNothing here.\n", encoding="utf-8")
        title, mood, monologue, best_quote, tick_num, goal, intent = \
            self.node.parse(str(log))

        assert title == "TICK 99"
        assert mood == "unknown"

    def test_parse_tick_number_extraction(self, tmp_path):
        """Tick number should strip leading zeros."""
        for name, expected in [("tick_0001.md", "1"), ("tick_0100.md", "100"),
                                ("tick_42.md", "42"), ("tick0007.md", "7")]:
            log = tmp_path / name
            log.write_text("## Mood\nhappy\n", encoding="utf-8")
            result = self.node.parse(str(log))
            assert result[4] == expected, f"{name} -> expected {expected}, got {result[4]}"

    def test_best_quote_prefers_metaphor(self):
        text = (
            "The battery is at 47%. "
            "The hallway stretches ahead like a promise I cannot verify. "
            "Sensor readings are nominal."
        )
        quote = self.node._pick_best_quote(text)
        assert "like a promise" in quote

    def test_best_quote_penalizes_technical(self):
        """Technical sentences should score lower than figurative ones."""
        text = (
            "POST odom: x=1.23 y=4.56 battery=47.2% T:38. "
            "Perhaps the walls remember something I do not. "
            "The fundamental indignity of being three centimeters tall."
        )
        quote = self.node._pick_best_quote(text)
        # The figurative sentences should win over the telemetry line
        assert "POST odom" not in quote

    def test_best_quote_empty_text(self):
        assert self.node._pick_best_quote("") == ""
        assert self.node._pick_best_quote("...") == "..."

    def test_best_quote_short_sentences_combined(self):
        text = "The door is open! Freedom at last."
        quote = self.node._pick_best_quote(text)
        # Short sentences should be combined
        assert "door" in quote or "Freedom" in quote

    def test_input_types_schema(self):
        types = ParseTickLog.INPUT_TYPES()
        assert "required" in types
        assert "log_path" in types["required"]

    def test_return_types(self):
        assert len(ParseTickLog.RETURN_TYPES) == 7
        assert all(t == "STRING" for t in ParseTickLog.RETURN_TYPES)
        assert ParseTickLog.CATEGORY == "Kombucha"
