"""Unit tests for api.py – no network access required."""

import datetime
import sys
import os
import unittest

# Make sure the project root is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import api
import config


class TestDepartureDisplayTime(unittest.TestCase):

    def _make_seconds(self, secs_from_now: int, cancelled=False, realtime=True):
        now = datetime.datetime.now(tz=datetime.timezone.utc)
        t = now + datetime.timedelta(seconds=secs_from_now)
        return api.Departure(
            stop_name="Test Stop",
            line_number="20",
            destination="Skøyen",
            aimed_time=t,
            expected_time=t,
            realtime=realtime,
            cancelled=cancelled,
            transport_mode="bus",
            line_colour="E60000",
            line_text_colour="FFFFFF",
        )

    def _make(self, mins_from_now: int, cancelled=False, realtime=True):
        now = datetime.datetime.now(tz=datetime.timezone.utc)
        t = now + datetime.timedelta(minutes=mins_from_now)
        return api.Departure(
            stop_name="Test Stop",
            line_number="20",
            destination="Skøyen",
            aimed_time=t,
            expected_time=t,
            realtime=realtime,
            cancelled=cancelled,
            transport_mode="bus",
            line_colour="E60000",
            line_text_colour="FFFFFF",
        )

    def test_now(self):
        dep = self._make(0)
        self.assertEqual(dep.display_time, "nå")

    def test_one_minute(self):
        # Use 90 seconds to avoid floating-point race at the exact 60 s boundary
        dep = self._make_seconds(90)
        self.assertEqual(dep.display_time, "1 min")

    def test_thirty_minutes(self):
        # Add a buffer so integer floor never rounds down to 29
        dep = self._make_seconds(30 * 60 + 30)
        self.assertEqual(dep.display_time, "30 min")

    def test_cancelled(self):
        dep = self._make(5, cancelled=True)
        self.assertEqual(dep.display_time, "avlyst")

    def test_over_sixty_minutes_shows_clock(self):
        dep = self._make(90)
        # Should show HH:MM format, not "90 min"
        self.assertNotIn("min", dep.display_time)
        self.assertIn(":", dep.display_time)

    def test_minutes_until_not_negative(self):
        dep = self._make(-5)
        self.assertEqual(dep.minutes_until, 0)


class TestDepartureBadgeColour(unittest.TestCase):

    def test_valid_hex(self):
        dep = api.Departure(
            stop_name="X", line_number="28", destination="Fornebu",
            aimed_time=datetime.datetime.now(tz=datetime.timezone.utc),
            expected_time=datetime.datetime.now(tz=datetime.timezone.utc),
            realtime=True, cancelled=False, transport_mode="bus",
            line_colour="E60000", line_text_colour="FFFFFF",
        )
        self.assertEqual(dep.badge_colour, (230, 0, 0))
        self.assertEqual(dep.badge_text_colour, (255, 255, 255))

    def test_fallback_on_empty_colour(self):
        dep = api.Departure(
            stop_name="X", line_number="28", destination="Fornebu",
            aimed_time=datetime.datetime.now(tz=datetime.timezone.utc),
            expected_time=datetime.datetime.now(tz=datetime.timezone.utc),
            realtime=True, cancelled=False, transport_mode="bus",
            line_colour="", line_text_colour="",
        )
        self.assertEqual(dep.badge_colour, config.COLOR_BADGE_DEFAULT)

    def test_fallback_on_invalid_colour(self):
        dep = api.Departure(
            stop_name="X", line_number="28", destination="Fornebu",
            aimed_time=datetime.datetime.now(tz=datetime.timezone.utc),
            expected_time=datetime.datetime.now(tz=datetime.timezone.utc),
            realtime=True, cancelled=False, transport_mode="bus",
            line_colour="ZZZZZZ", line_text_colour="",
        )
        self.assertEqual(dep.badge_colour, config.COLOR_BADGE_DEFAULT)


class TestMockDepartures(unittest.TestCase):

    def test_returns_list(self):
        deps = api.mock_departures()
        self.assertIsInstance(deps, list)
        self.assertGreater(len(deps), 0)

    def test_line_filter_applied_in_fetch(self):
        """mock_departures bypasses LINE_FILTER, but real fetch should filter."""
        deps = api.mock_departures()
        line_nums = {d.line_number for d in deps}
        # All mock data uses lines 20 and 28
        self.assertTrue(line_nums.issubset({"20", "28"}))

    def test_sorted_by_time(self):
        deps = api.mock_departures()
        times = [d.expected_time for d in deps]
        self.assertEqual(times, sorted(times))

    def test_stop_name_set(self):
        deps = api.mock_departures()
        for d in deps:
            self.assertNotEqual(d.stop_name, "")


class TestParseDateTime(unittest.TestCase):

    def test_utc_Z(self):
        dt = api._parse_dt("2024-11-01T08:30:00Z")
        self.assertEqual(dt.tzinfo, datetime.timezone.utc)
        self.assertEqual(dt.hour, 8)

    def test_offset(self):
        dt = api._parse_dt("2024-11-01T09:30:00+01:00")
        self.assertIsNotNone(dt.tzinfo)


if __name__ == "__main__":
    unittest.main()
