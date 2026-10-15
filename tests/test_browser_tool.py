"""tests/test_browser_tool.py -- Unit and integration tests for DOM Browser Automation."""

from __future__ import annotations

import pytest

from app.tools.browser import (
    BrowserController,
    browser_close,
    get_browser_controller,
)


@pytest.fixture
def browser():
    """Ensure clean headless browser controller for testing."""
    controller = BrowserController(headless=True)
    yield controller
    controller.close()


class TestBrowserController:
    def test_navigate_and_snapshot_interactive_elements(self, browser: BrowserController):
        html = (
            "data:text/html,"
            "<html><head><title>JASPER Test Page</title></head><body>"
            "<h1>Header</h1>"
            "<a href='https://example.com'>Visit Link</a>"
            "<input type='text' placeholder='Enter username' />"
            "<button id='submit-btn'>Run Simulation</button>"
            "</body></html>"
        )
        result = browser.navigate(html)

        assert result["title"] == "JASPER Test Page"
        assert result["interactive_count"] >= 3
        snapshot = result["snapshot"]
        assert "Visit Link" in snapshot
        assert "Enter username" in snapshot
        assert "Run Simulation" in snapshot

    def test_type_and_click_dom_interaction(self, browser: BrowserController):
        html = (
            "data:text/html,"
            "<html><head><title>Form Test</title></head><body>"
            "<input id='val-input' placeholder='Input here' />"
            "<button id='act-btn' onclick=\""
            "document.getElementById('res').innerText = 'Processed: ' + document.getElementById('val-input').value;"
            "\">Process</button>"
            "<p id='res'>Waiting</p>"
            "</body></html>"
        )
        browser.navigate(html)

        type_res = browser.type_text(index=1, text="JASPER_AI")
        assert type_res["status"] == "typed"

        click_res = browser.click(index=2)
        assert click_res["status"] == "clicked"

        read_res = browser.read_text()
        assert "Processed: JASPER_AI" in read_res["text"]

    def test_click_invalid_index_raises_keyerror(self, browser: BrowserController):
        html = "data:text/html,<html><body><button>One</button></body></html>"
        browser.navigate(html)

        with pytest.raises(KeyError, match="Element \\[999\\] not found"):
            browser.click(index=999)

    def test_browser_close_and_reopen(self, browser: BrowserController):
        html = "data:text/html,<html><title>Page 1</title><body></body></html>"
        browser.navigate(html)
        assert browser.is_active is True

        close_res = browser.close()
        assert close_res["status"] == "closed"
        assert browser.is_active is False

        # Reopening works
        browser.navigate(html)
        assert browser.is_active is True
