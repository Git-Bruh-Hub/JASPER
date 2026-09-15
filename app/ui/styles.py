APP_STYLE = r"""
QMainWindow, QWidget {
    background: #181818;
    color: #f1f1f1;
    font-family: "Segoe UI";
    font-size: 10pt;
}

QFrame#topBar {
    background: #1f1f1f;
    border-bottom: 1px solid #333333;
}

QLabel#brand {
    color: #ffffff;
    font-size: 12pt;
    font-weight: 600;
}

QLabel#statusTitle {
    color: #bdbdbd;
    font-size: 9pt;
}

QLabel#activeStatus {
    color: #8ee6a1;
    font-weight: 600;
}

QFrame#sidebar {
    background: #1b1b1b;
    border-right: 1px solid #303030;
}

QLabel#sidebarTitle {
    color: #929292;
    font-size: 8pt;
    font-weight: 600;
    letter-spacing: 1px;
}

QPushButton.navButton {
    text-align: left;
    background: transparent;
    border: none;
    border-radius: 6px;
    color: #c8c8c8;
    padding: 9px 10px;
}

QPushButton.navButton:hover {
    background: #262626;
    color: #ffffff;
}

QPushButton.navButton:checked {
    background: #2b2b2b;
    color: #ffffff;
}

QFrame#contentFrame {
    background: #181818;
}

QLabel#workspaceTitle {
    color: #ffffff;
    font-size: 11pt;
    font-weight: 600;
}

QLabel#workspaceHint {
    color: #898989;
    font-size: 9pt;
}

QTextBrowser#conversation {
    background: #181818;
    border: none;
    padding: 6px;
    selection-background-color: #3a3a3a;
}

QLabel#thinkingIndicator {
    color: #8c8c8c;
    font-size: 9pt;
    padding: 2px 4px 3px 4px;
}

QFrame.messageCard {
    background: #202020;
    border: 1px solid #303030;
    border-radius: 8px;
}

QLabel.messageSpeaker {
    color: #aaaaaa;
    font-size: 8pt;
    font-weight: 600;
}

QLabel.messageBody {
    color: #eeeeee;
    font-size: 10pt;
}

QFrame#composer {
    background: #1f1f1f;
    border: 1px solid #363636;
    border-radius: 9px;
}

QLineEdit#input {
    background: transparent;
    border: none;
    color: #eeeeee;
    padding: 8px;
    selection-background-color: #454545;
}

QPushButton#micButton, QPushButton#sendButton {
    background: #2a2a2a;
    border: 1px solid #404040;
    border-radius: 6px;
    color: #eeeeee;
    padding: 7px 11px;
}

QPushButton#micButton:hover, QPushButton#sendButton:hover {
    background: #333333;
}

QPushButton#micButton:disabled, QPushButton#sendButton:disabled {
    color: #666666;
}

QFrame#activityFrame {
    background: #1d1d1d;
    border: 1px solid #303030;
    border-radius: 8px;
}

QLabel#activityTitle {
    color: #d8d8d8;
    font-weight: 600;
}

QLabel.activityItem {
    color: #bcbcbc;
    padding: 2px 0;
}

QLabel#pageTitle {
    color: #ffffff;
    font-size: 18pt;
    font-weight: 600;
}

QLabel#pageBody {
    color: #929292;
    font-size: 10pt;
}

QFrame#statusBar {
    background: #151515;
    border-top: 1px solid #2d2d2d;
}

QLabel.statusChip {
    color: #a9a9a9;
    font-size: 8pt;
}
"""
