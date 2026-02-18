"""Smoke tests for display.py using a headless (off-screen) pygame surface.

These tests don't open a window – they verify that drawing routines run
without exceptions and produce the expected output on an in-memory surface.
"""

import datetime
import os
import sys
import unittest

# Force headless SDL (no window, no sound) before importing pygame
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pygame
import api
import config
from display import DepartureBoard


class TestDepartureBoardSmoke(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        pygame.init()
        cls.board = DepartureBoard(fullscreen=False)

    @classmethod
    def tearDownClass(cls):
        cls.board.quit()

    def test_draw_with_mock_data(self):
        """Board should draw without raising an exception."""
        self.board.update_departures(api.mock_departures())
        self.board.draw()   # Should not raise

    def test_draw_empty_departures(self):
        """Board should handle an empty departures list gracefully."""
        self.board.update_departures([])
        self.board.draw()

    def test_draw_with_error(self):
        """Error overlay should render without crashing."""
        self.board.update_departures(api.mock_departures())
        self.board.set_error("Test error message")
        self.board.draw()

    def test_draw_with_cancelled_departure(self):
        now = datetime.datetime.now(tz=datetime.timezone.utc)
        dep = api.Departure(
            stop_name="Test", line_number="20", destination="Skøyen",
            aimed_time=now + datetime.timedelta(minutes=5),
            expected_time=now + datetime.timedelta(minutes=5),
            realtime=False, cancelled=True, transport_mode="bus",
            line_colour="E60000", line_text_colour="FFFFFF",
        )
        self.board.update_departures([dep])
        self.board.draw()

    def test_last_updated_set_after_update(self):
        self.board.update_departures(api.mock_departures())
        self.assertIsNotNone(self.board.last_updated)

    def test_error_cleared_on_update(self):
        self.board.set_error("some error")
        self.board.update_departures(api.mock_departures())
        self.assertIsNone(self.board.error_message)


if __name__ == "__main__":
    unittest.main()
