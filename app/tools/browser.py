"""app/tools/browser.py -- DOM Browser Automation for JASPER.

Provides fast, deterministic DOM navigation and accessibility snapshot inspection
using Playwright Chromium. Designed for autonomous agents to inspect interactive
elements, click buttons, fill forms, and read web content without hallucinations.

Thread-safe: All Playwright operations run on a dedicated background thread pool
to avoid asyncio loop collisions and ensure clean synchronous tool dispatch.
"""

from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable

_LOG = logging.getLogger("jasper.tools.browser")


def get_default_headless() -> bool:
    """Return False (headed / visible browser) unless JASPER_BROWSER_HEADLESS=true."""
    return os.environ.get("JASPER_BROWSER_HEADLESS", "false").lower() in ("true", "1", "yes")


@dataclass
class InteractiveElement:
    index: int
    tag: str
    element_type: str
    text: str
    selector: str
    is_search_result: bool = False


class BrowserController:
    """Manages an active Playwright browser session for JASPER agents."""

    def __init__(self, headless: bool | None = None) -> None:
        self.headless = get_default_headless() if headless is None else headless
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="jasper_browser")
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None
        self._elements: dict[int, InteractiveElement] = {}

    def _run_in_pool(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        future = self._pool.submit(func, *args, **kwargs)
        return future.result(timeout=45)

    @property
    def is_active(self) -> bool:
        return self._run_in_pool(self._is_active_impl)

    def _is_active_impl(self) -> bool:
        return self._page is not None and not self._page.is_closed()

    def _ensure_browser_impl(self) -> Any:
        if self._page is None or self._page.is_closed():
            from playwright.sync_api import sync_playwright

            self._playwright = sync_playwright().start()
            _LOG.info("Launching Playwright Chromium (headless=%s)", self.headless)
            self._browser = self._playwright.chromium.launch(
                headless=self.headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--start-maximized",
                ],
            )
            self._context = self._browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            )
            self._page = self._context.new_page()
            self._page.set_default_timeout(20000)
        return self._page

    def search(self, query: str) -> dict[str, Any]:
        """Search the web using DuckDuckGo and return search results snapshot."""
        import urllib.parse
        encoded = urllib.parse.quote_plus(query)
        return self.navigate(f"https://duckduckgo.com/?q={encoded}")

    def navigate(self, url: str) -> dict[str, Any]:
        """Navigate to a URL and return a clean interactive DOM snapshot."""
        return self._run_in_pool(self._navigate_impl, url)

    def _navigate_impl(self, url: str) -> dict[str, Any]:
        if not url.startswith(("http://", "https://", "data:", "file://")):
            url = "https://" + url

        page = self._ensure_browser_impl()
        _LOG.info("Navigating to %s", url)
        response = page.goto(url, wait_until="domcontentloaded")
        status = response.status if response else 200

        snapshot = self._get_dom_snapshot_impl()
        return {
            "url": page.url,
            "title": page.title(),
            "status_code": status,
            "interactive_count": len(self._elements),
            "snapshot": snapshot,
        }

    def get_dom_snapshot(self) -> str:
        """Extract interactive elements and return an indexed LLM-friendly snapshot."""
        return self._run_in_pool(self._get_dom_snapshot_impl)

    def _get_dom_snapshot_impl(self) -> str:
        page = self._ensure_browser_impl()

        raw_elements = page.evaluate(
            """() => {
            const results = [];
            const selectors = [
                'button',
                'a[href]',
                'input:not([type="hidden"])',
                'textarea',
                'select',
                '[role="button"]',
                '[role="link"]',
                '[role="searchbox"]',
                '[contenteditable="true"]'
            ].join(',');

            const nodes = document.querySelectorAll(selectors);
            let idx = 1;

            for (const el of nodes) {
                const style = window.getComputedStyle(el);
                if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
                    continue;
                }
                const rect = el.getBoundingClientRect();
                if (rect.width <= 1 && rect.height <= 1) {
                    continue;
                }

                el.setAttribute('data-jasper-id', String(idx));

                const tag = el.tagName.toLowerCase();
                const type = el.getAttribute('type') || '';
                const placeholder = el.getAttribute('placeholder') || '';
                const ariaLabel = el.getAttribute('aria-label') || '';
                const rawText = (el.innerText || el.value || placeholder || ariaLabel || '').trim();
                const text = rawText.replace(/\\s+/g, ' ').slice(0, 60);

                let isSearchResult = false;
                if (tag === 'a' && (
                    el.closest('article, [data-testid="result"], .result, .g, li.b_algo, .search-result') ||
                    el.querySelector('h2, h3') ||
                    el.closest('h2, h3')
                )) {
                    isSearchResult = true;
                }

                results.push({
                    index: idx,
                    tag: tag,
                    element_type: type,
                    text: text,
                    selector: `[data-jasper-id="${idx}"]`,
                    is_search_result: isSearchResult
                });
                idx++;
            }
            return results;
        }"""
        )

        self._elements = {
            item["index"]: InteractiveElement(
                index=item["index"],
                tag=item["tag"],
                element_type=item["element_type"],
                text=item["text"],
                selector=item["selector"],
                is_search_result=item.get("is_search_result", False),
            )
            for item in raw_elements
        }

        lines = [
            f"Page Title: {page.title()}",
            f"Current URL: {page.url}",
            f"Found {len(self._elements)} interactive element(s):",
            "--------------------------------------------------",
        ]

        for el in self._elements.values():
            type_info = f" type='{el.element_type}'" if el.element_type else ""
            res_info = " [Search Result]" if el.is_search_result else ""
            label_info = f" '{el.text}'" if el.text else ""
            lines.append(f"[{el.index}] <{el.tag}{type_info}>{res_info}{label_info}")

        return "\n".join(lines)

    def click(self, index: int) -> dict[str, Any]:
        """Click on an indexed interactive element."""
        return self._run_in_pool(self._click_impl, index)

    def _click_impl(self, index: int) -> dict[str, Any]:
        page = self._ensure_browser_impl()

        if not self._elements:
            self._get_dom_snapshot_impl()

        if index not in self._elements:
            raise KeyError(
                f"Element [{index}] not found. Available elements: {list(self._elements.keys())[:20]}"
            )

        el = self._elements[index]
        _LOG.info("Clicking element [%d]: %s (%s)", index, el.tag, el.text)

        target = page.locator(el.selector)
        target.scroll_into_view_if_needed()
        target.click()
        try:
            page.wait_for_load_state("domcontentloaded", timeout=5000)
        except Exception:
            pass

        snapshot = self._get_dom_snapshot_impl()
        return {
            "status": "clicked",
            "element_index": index,
            "target": f"<{el.tag}> '{el.text}'",
            "new_url": page.url,
            "new_title": page.title(),
            "snapshot": snapshot,
        }

    def type_text(
        self, index: int, text: str, press_enter: bool = False
    ) -> dict[str, Any]:
        """Fill text into an indexed input field with intelligent element auto-routing."""
        return self._run_in_pool(self._type_text_impl, index, text, press_enter)

    def _type_text_impl(
        self, index: int, text: str, press_enter: bool = False
    ) -> dict[str, Any]:
        page = self._ensure_browser_impl()

        if not self._elements:
            self._get_dom_snapshot_impl()

        target_index = index
        el = self._elements.get(index)

        # Smart element check: is the requested element actually an editable input/textarea?
        is_editable = el is not None and (
            el.tag in ("input", "textarea")
            or (el.tag == "div" and "search" in el.selector.lower())
        )

        if not is_editable:
            # Look for best matching input/textarea on the page (e.g. search fields)
            search_candidates = [
                e for e in self._elements.values()
                if e.tag in ("input", "textarea")
                and (
                    "search" in e.text.lower()
                    or e.element_type == "search"
                    or "search" in e.selector.lower()
                )
            ]
            general_candidates = [
                e for e in self._elements.values()
                if e.tag in ("input", "textarea")
            ]
            fallback = (search_candidates or general_candidates or [None])[0]

            if fallback is not None:
                _LOG.warning(
                    "Element [%d] is not an editable input (<%s> '%s'). Auto-routing to editable element [%d] (<%s> '%s')",
                    index,
                    el.tag if el else "none",
                    el.text if el else "",
                    fallback.index,
                    fallback.tag,
                    fallback.text,
                )
                target_index = fallback.index
                el = fallback
            elif el is None:
                raise KeyError(
                    f"Element [{index}] not found. Available elements: {list(self._elements.keys())[:20]}"
                )

        _LOG.info("Typing into element [%d] (<%s> '%s'): %s", target_index, el.tag, el.text, text)

        target = page.locator(el.selector)
        target.scroll_into_view_if_needed()
        target.fill(text)

        # Auto-press enter if requested or if it's a search field / single search textarea
        should_press_enter = press_enter or ("search" in el.text.lower() or el.element_type == "search" or el.tag == "textarea")
        if should_press_enter:
            target.press("Enter")
            try:
                page.wait_for_load_state("domcontentloaded", timeout=5000)
            except Exception:
                pass

        snapshot = self._get_dom_snapshot_impl()
        return {
            "status": "typed",
            "element_index": target_index,
            "target": f"<{el.tag}> '{el.text}'",
            "value": text,
            "pressed_enter": should_press_enter,
            "new_url": page.url,
            "new_title": page.title(),
            "snapshot": snapshot,
        }

    def read_text(self) -> dict[str, Any]:
        """Extract readable text content from the current page."""
        return self._run_in_pool(self._read_text_impl)

    def _read_text_impl(self) -> dict[str, Any]:
        page = self._ensure_browser_impl()
        text = page.evaluate("() => document.body.innerText || ''")
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        return {
            "url": page.url,
            "title": page.title(),
            "text": "\n".join(lines[:300]),
        }

    def close(self) -> dict[str, str]:
        """Close the browser session and free resources."""
        return self._run_in_pool(self._close_impl)

    def _close_impl(self) -> dict[str, str]:
        if self._browser:
            try:
                self._browser.close()
            except Exception as e:
                _LOG.warning("Error closing browser: %s", e)
        if self._playwright:
            try:
                self._playwright.stop()
            except Exception as e:
                _LOG.warning("Error stopping playwright: %s", e)

        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._elements.clear()
        return {"status": "closed"}


_CONTROLLER: BrowserController | None = None


def get_browser_controller(headless: bool | None = None) -> BrowserController:
    """Return the global BrowserController instance."""
    global _CONTROLLER
    if _CONTROLLER is None:
        _CONTROLLER = BrowserController(headless=headless)
    elif headless is not None and _CONTROLLER.headless != headless:
        # Recreate controller if headless preference changed
        _CONTROLLER.close()
        _CONTROLLER = BrowserController(headless=headless)
    return _CONTROLLER


def browser_search(query: str) -> dict[str, Any]:
    """Search the web using DuckDuckGo and return search results snapshot."""
    return get_browser_controller().search(query=str(query))


def browser_navigate(url: str) -> dict[str, Any]:
    """Navigate to a URL and inspect the page."""
    return get_browser_controller().navigate(url=url)


def browser_get_dom() -> str:
    """Get the current page's interactive element snapshot."""
    return get_browser_controller().get_dom_snapshot()


def browser_click(index: int) -> dict[str, Any]:
    """Click on an indexed interactive element on the current page."""
    return get_browser_controller().click(index=int(index))


def browser_type(index: int, text: str, press_enter: bool = False) -> dict[str, Any]:
    """Fill text into an indexed input field on the current page."""
    return get_browser_controller().type_text(
        index=int(index), text=str(text), press_enter=bool(press_enter)
    )


def browser_read_text() -> dict[str, Any]:
    """Read full text content from the current page."""
    return get_browser_controller().read_text()


def browser_close() -> dict[str, str]:
    """Close the current browser session."""
    return get_browser_controller().close()
