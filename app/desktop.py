from __future__ import annotations

import sys

from PySide6.QtCore import QThread
from PySide6.QtWidgets import QApplication

from app.agents.desktop_wiring import build_desktop_autonomy
from app.core.logging_setup import setup_logging
from app.ui.main_window import MainWindow
from app.ui.worker import JasperWorker


def main() -> int:
    setup_logging()
    app = QApplication(sys.argv)
    app.setApplicationName("JASPER")
    app.setApplicationDisplayName("JASPER")
    app.setQuitOnLastWindowClosed(False)

    from pathlib import Path
    from PySide6.QtGui import QIcon
    icon_path = Path("assets/jasper_icon.png")
    if not icon_path.exists():
        icon_path = Path(__file__).resolve().parent.parent / "assets" / "jasper_icon.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    thread = QThread()
    worker = JasperWorker()
    build_desktop_autonomy(worker)
    worker.moveToThread(thread)
    thread.start()

    window = MainWindow(worker, thread)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
