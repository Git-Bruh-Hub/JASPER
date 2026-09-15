from __future__ import annotations

import sys

from PySide6.QtCore import QThread
from PySide6.QtWidgets import QApplication

from app.core.logging_setup import setup_logging
from app.ui.main_window import MainWindow
from app.ui.worker import JasperWorker


def main() -> int:
    setup_logging()
    app = QApplication(sys.argv)
    app.setApplicationName("JASPER")
    app.setApplicationDisplayName("JASPER")
    app.setQuitOnLastWindowClosed(False)

    thread = QThread()
    worker = JasperWorker()
    worker.moveToThread(thread)
    thread.start()

    window = MainWindow(worker, thread)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
