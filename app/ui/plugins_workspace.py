"""app/ui/plugins_workspace.py -- Real Plugins & Skills workspace listing actual tools and agent skills."""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

_LOG = logging.getLogger("jasper.ui.plugins_workspace")


class PluginsWorkspace(QWidget):
    """Workspace for exploring and using installed tools, plugins, and agent skills."""

    use_item_requested = Signal(str, str)  # (item_name, prompt_to_run)
    plugin_toggled = Signal(str, bool)

    REAL_PLUGINS = [
        {
            "id": "desktop_take_screenshot",
            "name": "Desktop Screen Vision",
            "category": "Vision",
            "icon": "👁️",
            "installed": True,
            "badge": "Core Tool",
            "description": "Captures multi-monitor virtual desktop, active windows, or snips arbitrary regions for vision analysis.",
            "suggestion": "Use for UI verification, inspecting errors in third-party apps, or checking background status.",
            "prompt": "/screen check my desktop and explain what is currently displayed",
        },
        {
            "id": "browser_search",
            "name": "DuckDuckGo Web Search",
            "category": "Web",
            "icon": "🔍",
            "installed": True,
            "badge": "Core Tool",
            "description": "Performs web searches and retrieves real-time search result snapshots without rate limits.",
            "suggestion": "Use when researching latest library releases, verifying facts, or finding official documentation.",
            "prompt": "Search the web for the latest updates on Python 3.12 and PySide6",
        },
        {
            "id": "browser_navigate",
            "name": "Playwright Web Browser",
            "category": "Web Automation",
            "icon": "🌐",
            "installed": True,
            "badge": "Core Tool",
            "description": "Headless browser automation to navigate to URLs, extract readable text, and inspect DOM snapshots.",
            "suggestion": "Use to read articles, scrape documentation pages, or test web endpoints.",
            "prompt": "Navigate to https://docs.python.org and summarize the top news",
        },
        {
            "id": "browser_click_type",
            "name": "Web Form & UI Automation",
            "category": "Web Automation",
            "icon": "🖱️",
            "installed": True,
            "badge": "Requires Approval",
            "description": "Clicks interactive elements and fills form inputs on open web pages with human approval protection.",
            "suggestion": "Use when interacting with web forms, dashboards, or navigating multi-page web applications.",
            "prompt": "Inspect the open browser page and click the primary navigation link",
        },
        {
            "id": "filesystem_tools",
            "name": "Workspace Filesystem Tools",
            "category": "Filesystem",
            "icon": "📁",
            "installed": True,
            "badge": "Core Tool",
            "description": "Safely reads and writes project files within allowed workspace directories.",
            "suggestion": "Use to generate code files, read project configuration, or create documentation.",
            "prompt": "List the files in the workspace and inspect recent project changes",
        },
        {
            "id": "edit_file_chunk",
            "name": "Surgical Code & Text Editor",
            "category": "Filesystem",
            "icon": "✂️",
            "installed": True,
            "badge": "Requires Approval",
            "description": "Performs exact search-and-replace chunk edits on workspace files without full file rewrites.",
            "suggestion": "Use for targeted bug fixes, updating configuration blocks, or modifying functions.",
            "prompt": "Surgically edit the target block in the workspace file",
        },
        {
            "id": "run_terminal_command",
            "name": "Scoped Terminal & Shell Runner",
            "category": "Execution",
            "icon": "💻",
            "installed": True,
            "badge": "Requires Approval",
            "description": "Executes shell commands with strict timeout limits and captures stdout/stderr. Guarded by approval gates.",
            "suggestion": "Use for running test suites, checking git status, or executing build scripts.",
            "prompt": "Run pytest on the test suite and summarize the results",
        },
        {
            "id": "delta_screen_watcher",
            "name": "Delta-Screen Companion Watcher",
            "category": "Vision",
            "icon": "👁️",
            "installed": True,
            "badge": "Proactive Vision",
            "description": "Monitors desktop changes using low-overhead perceptual diffs and alerts you when builds, downloads, or errors occur.",
            "suggestion": "Use when running long background tasks so JASPER notifies you the instant something finishes or fails.",
            "prompt": "/watch notify me when the build or test completes",
        },
        {
            "id": "system_diagnostics",
            "name": "System & Hardware Diagnostics",
            "category": "System",
            "icon": "⚡",
            "installed": True,
            "badge": "Core Tool",
            "description": "Monitors GPU VRAM, system memory, CPU core load, and Ollama model status.",
            "suggestion": "Use when diagnosing high memory usage or verifying Ollama GPU acceleration.",
            "prompt": "Report current GPU VRAM, system RAM, and Ollama status",
        },
    ]


    REAL_SKILLS = [
        {
            "id": "ui-ux-pro-max",
            "name": "UI/UX Pro Max",
            "category": "Design & UX",
            "icon": "✨",
            "description": "UI design intelligence: 50 styles, 21 color palettes, modern dark mode, and sleek micro-animations.",
            "suggestion": "Use when redesigning or polishing PySide6 or web interfaces to give them a premium, professional look.",
            "prompt": "/ui-ux-pro-max Refine the UI layout with modern dark mode styling and clean typography",
        },
        {
            "id": "frontend-ui-engineering",
            "name": "Frontend UI Engineering",
            "category": "UI Engineering",
            "icon": "🎨",
            "description": "Builds accessible, responsive, production-quality user interfaces with strong architectural consistency.",
            "suggestion": "Use when creating new widgets, fixing layout bugs, or establishing UI design tokens.",
            "prompt": "/frontend-ui-engineering Build a modern responsive dashboard widget",
        },
        {
            "id": "ui-design-system",
            "name": "UI Design System",
            "category": "Design Tokens",
            "icon": "📐",
            "description": "Toolkit for senior UI designers: design token generation, component specifications, and style guide consistency.",
            "suggestion": "Use to ensure colors, borders, and spacing tokens follow a single source of truth.",
            "prompt": "/ui-design-system Audit the project design tokens and component styling",
        },
        {
            "id": "python-pro",
            "name": "Python Pro",
            "category": "Backend",
            "icon": "🐍",
            "description": "Master Python 3.12+ features, async programming, type hinting, and high-performance practices.",
            "suggestion": "Use when optimizing async execution, writing typed data models, or refactoring backend logic.",
            "prompt": "/python-pro Optimize the orchestrator async worker loop and type hints",
        },
        {
            "id": "python-testing-patterns",
            "name": "Python Testing Patterns",
            "category": "QA & Testing",
            "icon": "🧪",
            "description": "Comprehensive pytest strategies, mock fixtures, regression safety, and test-driven development.",
            "suggestion": "Use when writing regression tests or improving test suite coverage.",
            "prompt": "/python-testing-patterns Write comprehensive pytest fixtures and test cases",
        },
        {
            "id": "autonomous-agent-patterns",
            "name": "Autonomous Agent Patterns",
            "category": "Agents",
            "icon": "🛡️",
            "description": "Design patterns for coding agents, permission barriers, tool execution loops, and human-in-the-loop approvals.",
            "suggestion": "Use when building safe tool handlers, approval gates, or autonomous workflows.",
            "prompt": "/autonomous-agent-patterns Review permission boundaries and approval gates",
        },
        {
            "id": "ai-agents-architect",
            "name": "AI Agents Architect",
            "category": "Architecture",
            "icon": "🤖",
            "description": "Expert in multi-agent orchestration, tool integration, persistent memory, and planner strategies.",
            "suggestion": "Use when designing multi-agent coordination or complex planner trees.",
            "prompt": "/ai-agents-architect Design a multi-agent planner for code generation",
        },
        {
            "id": "senior-prompt-engineer",
            "name": "Senior Prompt Engineer",
            "category": "Prompting",
            "icon": "🧠",
            "description": "LLM optimization, structured JSON outputs, few-shot patterns, chain-of-thought, and prompt guardrails.",
            "suggestion": "Use when optimizing Ollama model prompt templates or eliminating hallucinated tool outputs.",
            "prompt": "/senior-prompt-engineer Optimize system prompt for structured reasoning",
        },
        {
            "id": "git-workflow-and-versioning",
            "name": "Git Workflow & Versioning",
            "category": "DevOps",
            "icon": "🌿",
            "description": "Structured git practices, atomic commits, branch protection, pull requests, and semantic versioning.",
            "suggestion": "Use when preparing commits, reviewing diffs, or cutting clean release branches.",
            "prompt": "/git-workflow-and-versioning Review working tree diff and stage atomic commits",
        },
        {
            "id": "graphify",
            "name": "Graphify Codebase Knowledge",
            "category": "Navigation",
            "icon": "🕸️",
            "description": "AST knowledge graph mapping code relationships, imports, and architectural dependencies.",
            "suggestion": "Use for codebase navigation and exploring relationships between modules.",
            "prompt": "graphify query 'What are the main UI components in the project?'",
        },
    ]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("pluginsWorkspace")
        self._active_tab = "plugins"
        self._card_widgets: list[tuple[QWidget, str]] = []
        self._build_ui()

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(32, 28, 32, 28)
        root_layout.setSpacing(18)

        # --- Top Tab Bar Switcher & Actions ---
        top_bar = QHBoxLayout()
        top_bar.setSpacing(12)

        tab_container = QFrame()
        tab_container.setStyleSheet(
            "QFrame { background: #212124; border: 1px solid #333338; border-radius: 18px; padding: 2px; }"
        )
        tab_layout = QHBoxLayout(tab_container)
        tab_layout.setContentsMargins(3, 3, 3, 3)
        tab_layout.setSpacing(4)

        self.btn_tab_plugins = QPushButton("Installed Tools & Plugins")
        self.btn_tab_plugins.setCheckable(True)
        self.btn_tab_plugins.setChecked(True)
        self._style_tab_btn(self.btn_tab_plugins, active=True)
        self.btn_tab_plugins.clicked.connect(lambda: self._switch_tab("plugins"))
        tab_layout.addWidget(self.btn_tab_plugins)

        self.btn_tab_skills = QPushButton("Agent Skills")
        self.btn_tab_skills.setCheckable(True)
        self.btn_tab_skills.setChecked(False)
        self._style_tab_btn(self.btn_tab_skills, active=False)
        self.btn_tab_skills.clicked.connect(lambda: self._switch_tab("skills"))
        tab_layout.addWidget(self.btn_tab_skills)
        top_bar.addWidget(tab_container)

        top_bar.addStretch(1)

        btn_info = QPushButton("💡 How to Use")
        btn_info.setStyleSheet(
            "QPushButton { background: #212124; border: 1px solid #333338; border-radius: 8px; color: #d4d4d8; padding: 6px 14px; font-size: 9pt; }"
            "QPushButton:hover { background: #2a2a2e; color: #ffffff; }"
        )
        btn_info.clicked.connect(self._show_info_modal)
        top_bar.addWidget(btn_info)
        root_layout.addLayout(top_bar)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent; border: none;")

        self.content_container = QWidget()
        self.content_layout = QVBoxLayout(self.content_container)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(20)

        # Header Section
        self.title_lbl = QLabel("Installed Tools & Plugins")
        self.title_lbl.setStyleSheet("font-size: 24pt; font-weight: 700; color: #ffffff;")
        self.content_layout.addWidget(self.title_lbl)

        self.subtitle_lbl = QLabel("Active tools in JASPER's registry. Click '⚡ Use in Chat' to invoke any tool or skill.")
        self.subtitle_lbl.setStyleSheet("font-size: 11pt; color: #a1a1aa;")
        self.content_layout.addWidget(self.subtitle_lbl)

        # Search Bar
        self.search_input = QLineEdit()
        self.search_input.setObjectName("pluginSearch")
        self.search_input.setPlaceholderText("🔍  Search installed tools and plugins...")
        self.search_input.setStyleSheet(
            "QLineEdit {"
            "  background: #212124;"
            "  border: 1px solid #333338;"
            "  border-radius: 10px;"
            "  color: #f4f4f5;"
            "  font-size: 10.5pt;"
            "  padding: 10px 14px;"
            "}"
            "QLineEdit:focus { border: 1px solid #8ee6a1; }"
        )
        self.search_input.textChanged.connect(self._filter_items)
        self.content_layout.addWidget(self.search_input)

        # Views container
        self.views_stack = QVBoxLayout()
        self.views_stack.setSpacing(14)
        self.content_layout.addLayout(self.views_stack)

        self._render_plugins_view()

        self.content_layout.addStretch(1)
        scroll.setWidget(self.content_container)
        root_layout.addWidget(scroll)

    def _style_tab_btn(self, btn: QPushButton, active: bool) -> None:
        if active:
            btn.setStyleSheet(
                "QPushButton { background: #34343a; color: #ffffff; font-weight: 600; border-radius: 14px; padding: 6px 18px; font-size: 9.5pt; border: none; }"
            )
        else:
            btn.setStyleSheet(
                "QPushButton { background: transparent; color: #a1a1aa; font-weight: 500; border-radius: 14px; padding: 6px 18px; font-size: 9.5pt; border: none; }"
                "QPushButton:hover { color: #f4f4f5; }"
            )

    def _switch_tab(self, tab: str) -> None:
        self._active_tab = tab
        self.btn_tab_plugins.setChecked(tab == "plugins")
        self.btn_tab_skills.setChecked(tab == "skills")
        if tab == "plugins":
            self._style_tab_btn(self.btn_tab_plugins, active=True)
            self._style_tab_btn(self.btn_tab_skills, active=False)
            self.title_lbl.setText("Installed Tools & Plugins")
            self.subtitle_lbl.setText("Real registered tools in JASPER. Click '⚡ Use in Chat' to immediately invoke any tool.")
            self.search_input.setPlaceholderText("🔍  Search installed tools and plugins...")
            self._render_plugins_view()
        else:
            self._style_tab_btn(self.btn_tab_plugins, active=False)
            self._style_tab_btn(self.btn_tab_skills, active=True)
            self.title_lbl.setText("Installed Agent Skills")
            self.subtitle_lbl.setText("Active skills in .agents/skills. Click '⚡ Use in Chat' to apply a skill to your task.")
            self.search_input.setPlaceholderText("🔍  Search agent skills...")
            self._render_skills_view()
        self._filter_items(self.search_input.text())

    def _clear_views_stack(self) -> None:
        while self.views_stack.count() > 0:
            item = self.views_stack.takeAt(0)
            widget = item.widget()
            layout = item.layout()
            if widget:
                widget.deleteLater()
            elif layout:
                while layout.count() > 0:
                    child = layout.takeAt(0)
                    if child.widget():
                        child.widget().deleteLater()
        self._card_widgets.clear()

    def _render_plugins_view(self) -> None:
        self._clear_views_stack()

        for item in self.REAL_PLUGINS:
            card = self._create_card(item, is_skill=False)
            self.views_stack.addWidget(card)
            search_text = f"{item['id']} {item['name']} {item['description']} {item['category']} {item['suggestion']}".lower()
            self._card_widgets.append((card, search_text))

    def _render_skills_view(self) -> None:
        self._clear_views_stack()

        for item in self.REAL_SKILLS:
            card = self._create_card(item, is_skill=True)
            self.views_stack.addWidget(card)
            search_text = f"{item['id']} {item['name']} {item['description']} {item['category']} {item['suggestion']}".lower()
            self._card_widgets.append((card, search_text))

    def _create_card(self, item: dict[str, Any], is_skill: bool) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            "QFrame {"
            "  background: #1c1c1f;"
            "  border: 1px solid #2e2e34;"
            "  border-radius: 12px;"
            "  padding: 14px;"
            "}"
            "QFrame:hover {"
            "  background: #242429;"
            "  border: 1px solid #3f3f48;"
            "}"
        )
        layout = QHBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(16)

        icon_lbl = QLabel(item["icon"])
        icon_lbl.setFixedSize(40, 40)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet("background: #27272e; border-radius: 10px; font-size: 16pt;")
        layout.addWidget(icon_lbl)

        info = QVBoxLayout()
        info.setSpacing(4)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)

        name_lbl = QLabel(item["name"])
        name_lbl.setStyleSheet("font-size: 11pt; font-weight: 600; color: #ffffff;")
        title_row.addWidget(name_lbl)

        badge_txt = item.get("badge") or item.get("category", "")
        badge_lbl = QLabel(badge_txt)
        badge_lbl.setStyleSheet(
            "background: #27272e; color: #8ee6a1; font-size: 8pt; font-weight: 600; padding: 2px 7px; border-radius: 4px;"
        )
        title_row.addWidget(badge_lbl)
        title_row.addStretch(1)
        info.addLayout(title_row)

        desc_lbl = QLabel(item["description"])
        desc_lbl.setStyleSheet("font-size: 9pt; color: #a1a1aa;")
        desc_lbl.setWordWrap(True)
        info.addWidget(desc_lbl)

        sugg_lbl = QLabel(f"💡 <b>Suggestion:</b> {item.get('suggestion', '')}")
        sugg_lbl.setStyleSheet("font-size: 8.5pt; color: #71717a;")
        sugg_lbl.setWordWrap(True)
        info.addWidget(sugg_lbl)

        layout.addLayout(info, 1)

        # Action: "⚡ Use in Chat"
        btn_use = QPushButton("⚡ Use in Chat")
        btn_use.setStyleSheet(
            "QPushButton {"
            "  background: #27272e;"
            "  color: #ffffff;"
            "  border: 1px solid #3f3f48;"
            "  border-radius: 8px;"
            "  padding: 8px 16px;"
            "  font-size: 9pt;"
            "  font-weight: 600;"
            "}"
            "QPushButton:hover { background: #3f3f48; color: #8ee6a1; }"
        )
        prompt = item.get("prompt", f"Use {item['name']} to help me.")
        btn_use.clicked.connect(lambda _, it=item, p=prompt: self._on_use_clicked(it, p))
        layout.addWidget(btn_use)

        return card

    def _on_use_clicked(self, item: dict[str, Any], prompt: str) -> None:
        self.use_item_requested.emit(item["name"], prompt)

    @Slot(str)
    def _filter_items(self, query: str) -> None:
        q = query.strip().lower()
        for widget, text in self._card_widgets:
            widget.setVisible(q in text if q else True)

    def _show_info_modal(self) -> None:
        QMessageBox.information(
            self,
            "Using Plugins and Skills",
            "Every tool and skill listed here is actively loaded in JASPER.\n\n"
            "• Click '⚡ Use in Chat' on any card to immediately switch to Chat and pre-fill the command.\n"
            "• Core tools (screenshots, web search, filesystem) are automatically available to the agent during conversation.\n"
            "• Agent skills guide specialized engineering workflows (design, testing, Python, architecture)."
        )
