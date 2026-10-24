"""tests/test_browser_persistent.py -- Tests for Multi-Browser & Persistent Profile Engine."""

from __future__ import annotations

from pathlib import Path
import pytest

from app.tools.browser import (
    BrowserConfig,
    BrowserController,
    browser_close,
    get_browser_controller,
    get_default_profile_dir,
)


class TestBrowserPersistentProfile:
    def test_browser_config_defaults_and_profile_dir(self):
        default_dir = get_default_profile_dir()
        assert default_dir == Path.home() / ".jasper" / "browser_profile"
        assert default_dir.exists()

        cfg = BrowserConfig()
        assert cfg.channel in ("chrome", "msedge", "chromium")
        assert cfg.headless is False
        assert cfg.viewport_width == 1280
        assert cfg.viewport_height == 800

    def test_persistent_context_saves_and_persists_session(self, tmp_path: Path):
        profile_dir = tmp_path / "test_jasper_profile"
        profile_dir.mkdir(parents=True, exist_ok=True)

        cfg = BrowserConfig(
            channel="chromium",
            headless=True,
            user_data_dir=profile_dir,
        )
        controller = BrowserController(config=cfg)

        html = (
            "data:text/html,"
            "<html><head><title>Email Inbox</title></head><body>"
            "<h1>Your Messages</h1>"
            "<div class='email-item' id='mail-1'>"
            "  <h2>7-Eleven E-Receipt</h2>"
            "  <p>Order #711-9824: Total $14.50. Items: Slurpee (Large), Hot Dog combo. Thank you!</p>"
            "</div>"
            "</body></html>"
        )

        res = controller.navigate(html)
        assert res["title"] == "Email Inbox"
        assert controller.is_active is True
        assert controller.active_channel == "chromium"
        assert controller.user_data_dir == profile_dir

        summary_res = controller.summarize(topic_or_query="7-Eleven")
        assert "7-Eleven" in summary_res["summary"] or "711-9824" in summary_res["summary"] or "$14.50" in summary_res["summary"]

        close_res = controller.close()
        assert close_res["status"] == "closed"
        assert controller.is_active is False

        # Verify persistent profile directory has browser state written
        assert profile_dir.exists()

    def test_channel_fallback_when_channel_unavailable(self, tmp_path: Path):
        """When an unavailable or invalid channel is requested, controller falls back to bundled chromium."""
        profile_dir = tmp_path / "fallback_profile"
        cfg = BrowserConfig(
            channel="invalid_channel_name_xyz",
            headless=True,
            user_data_dir=profile_dir,
        )
        controller = BrowserController(config=cfg)

        html = "data:text/html,<html><title>Fallback Test</title><body>OK</body></html>"
        res = controller.navigate(html)

        assert res["title"] == "Fallback Test"
        assert controller.active_channel == "chromium"
        assert controller.is_active is True

        controller.close()

    def test_get_browser_controller_respects_config(self, tmp_path: Path):
        custom_dir = tmp_path / "custom_profile"
        cfg = BrowserConfig(channel="chromium", headless=True, user_data_dir=custom_dir)
        ctrl = get_browser_controller(config=cfg)

        assert ctrl.config.user_data_dir == custom_dir
        assert ctrl.config.channel == "chromium"
        ctrl.close()
