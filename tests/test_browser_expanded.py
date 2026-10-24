"""tests/test_browser_expanded.py -- Unit tests for expanded browser tools (tabs & inbox)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.agents.desktop_wiring import register_desktop_tools
from app.tools.browser import (
    BrowserConfig,
    BrowserController,
    browser_close_tab,
    browser_list_tabs,
    browser_new_tab,
    browser_read_inbox,
    browser_switch_tab,
    get_browser_controller,
)
from app.tools.registry import Risk, ToolRegistry


def test_browser_tab_management_unit():
    ctrl = BrowserController()

    mock_page1 = MagicMock()
    mock_page1.title.return_value = "Tab 1 - Inbox"
    mock_page1.url = "https://mail.google.com"

    mock_page2 = MagicMock()
    mock_page2.title.return_value = "Tab 2 - 7-Eleven"
    mock_page2.url = "https://7-eleven.com"

    mock_context = MagicMock()
    mock_context.pages = [mock_page1, mock_page2]
    mock_context.new_page.return_value = mock_page2

    ctrl._context = mock_context
    ctrl._page = mock_page1

    with patch.object(ctrl, "_ensure_browser_impl", return_value=mock_page1):
        # 1. Test list_tabs
        tabs = ctrl._list_tabs_impl()
        assert len(tabs) == 2
        assert tabs[0]["title"] == "Tab 1 - Inbox"
        assert tabs[0]["is_active"] is True
        assert tabs[1]["is_active"] is False

        # 2. Test switch_tab
        with patch.object(ctrl, "_get_dom_snapshot_impl", return_value="[1] button"):
            switched = ctrl._switch_tab_impl(1)
            assert switched["tab_index"] == 1
            assert ctrl._page == mock_page2
            mock_page2.bring_to_front.assert_called_once()

        # 3. Test out of range switch_tab
        with pytest.raises(IndexError):
            ctrl._switch_tab_impl(99)

        # 4. Test close_tab
        ctrl._close_tab_impl(1)
        mock_page2.close.assert_called_once()


def test_browser_new_tab_unit():
    ctrl = BrowserController()
    mock_context = MagicMock()
    mock_new_page = MagicMock()
    mock_new_page.title.return_value = "New Tab"
    mock_new_page.url = "about:blank"
    mock_context.new_page.return_value = mock_new_page
    mock_context.pages = [mock_new_page]

    ctrl._context = mock_context
    with patch.object(ctrl, "_ensure_browser_impl", return_value=mock_new_page):
        res = ctrl._new_tab_impl("about:blank")
        assert res["status"] == "opened"
        assert ctrl._page == mock_new_page


def test_browser_read_inbox_filtering():
    ctrl = BrowserController()
    mock_page = MagicMock()
    mock_page.url = "https://mail.google.com/mail/u/0/#inbox"
    mock_page.title.return_value = "Gmail - Inbox"

    fake_emails = [
        {
            "id": 1,
            "sender": "7-Eleven Rewards",
            "subject": "Your receipt and exclusive discount",
            "snippet": "Thank you for shopping at 7-Eleven. Voucher code: 7E-992.",
            "date": "10:30 AM",
            "raw": "7-Eleven Rewards Your receipt and exclusive discount Voucher code 7E-992",
        },
        {
            "id": 2,
            "sender": "GitHub",
            "subject": "New sign-in from Chrome on Windows",
            "snippet": "We noticed a new sign-in to your GitHub account.",
            "date": "Yesterday",
            "raw": "GitHub New sign-in from Chrome on Windows",
        },
    ]

    mock_page.evaluate.return_value = fake_emails
    ctrl._page = mock_page

    with patch.object(ctrl, "_ensure_browser_impl", return_value=mock_page):
        # 1. Search for 7-Eleven
        result = ctrl._read_inbox_impl(filter_query="7-eleven")
        assert result["count"] == 1
        assert result["emails"][0]["sender"] == "7-Eleven Rewards"
        assert "7E-992" in result["emails"][0]["snippet"]

        # 2. Search for GitHub
        gh_result = ctrl._read_inbox_impl(filter_query="github")
        assert gh_result["count"] == 1
        assert gh_result["emails"][0]["sender"] == "GitHub"

        # 3. Search without filter (all emails)
        all_result = ctrl._read_inbox_impl(filter_query="")
        assert all_result["count"] == 2


def test_desktop_wiring_registers_new_tools():
    registry = ToolRegistry()
    register_desktop_tools(registry)

    registered_names = [t.name for t in registry.list()]
    assert "browser_read_inbox" in registered_names
    assert "browser_list_tabs" in registered_names
    assert "browser_new_tab" in registered_names
    assert "browser_switch_tab" in registered_names
    assert "browser_close_tab" in registered_names

    inbox_tool = registry.get("browser_read_inbox")
    assert inbox_tool.risk == Risk.READ
    assert "filter_query" in inbox_tool.parameters["properties"]
