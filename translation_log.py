import re
import time
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QPushButton, QLabel, QSizeGrip, QScrollBar
)
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QTextCursor, QColor, QTextCharFormat, QFont


class TranslationLogPanel(QWidget):
    """
    A floating, draggable, resizable panel that accumulates translated lines.
    New translations are appended at the bottom (like a subtitle log).
    Stays on top of all windows via NSStatusWindowLevel.
    """

    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        # Prevent window from hiding when app loses focus
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow)

        self._drag_pos   = None
        self._last_text  = ""    # display dedup (raw)
        self._last_norm  = ""    # display dedup (normalized)
        self._entry_count = 0
        self._level_set  = False
        self._is_pinned  = False
        self._win_name   = ""
        
        self.i18n = {
            "tr": {"title": "GTranslate Günlüğü", "pin": "Sabitle", "pinned": "Sabit", "clear": "Temizle"},
            "en": {"title": "GTranslate Log", "pin": "Pin", "pinned": "Pinned", "clear": "Clear"},
            "de": {"title": "GTranslate Log", "pin": "Fixieren", "pinned": "Fixiert", "clear": "Löschen"},
            "fr": {"title": "Journal GTranslate", "pin": "Épingler", "pinned": "Épinglé", "clear": "Effacer"},
            "it": {"title": "Log GTranslate", "pin": "Fissa", "pinned": "Fissato", "clear": "Cancella"}
        }
        self.current_lang = "tr"

        self._build_ui()

    # -- UI --------------------------------------------------------------------
    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self._container = QWidget()
        self._container.setObjectName("container")
        self._container.setStyleSheet("""
            QWidget#container {
                background-color: rgba(0, 0, 0, 230);
                border: none;
                border-radius: 12px;
            }
            QLabel#Title {
                color: #f1c40f;
                font-family: '.AppleSystemUIFont', 'SF Pro Display', sans-serif;
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 0.5px;
            }
            QPushButton {
                background: rgba(255, 255, 255, 0.03);
                color: #aaa;
                border: 1px solid rgba(241, 196, 15, 0.1);
                border-radius: 5px;
                font-size: 10px;
            }
            QPushButton:hover {
                background: rgba(241, 196, 15, 0.1);
                color: #f1c40f;
            }
            QPushButton:checked {
                background: #f1c40f;
                color: #000000;
            }
            QTextEdit {
                background: transparent;
                color: #ffffff;
                border: none;
                font-family: '.AppleSystemUIFont', 'SF Pro Text', sans-serif;
                font-size: 13px;
                line-height: 140%;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 4px;
            }
            QScrollBar::handle:vertical {
                background: rgba(241, 196, 15, 0.3);
                border-radius: 2px;
            }
        """)

        lay = QVBoxLayout(self._container)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        # -- Header (drag handle) ----------------------------------------------
        hdr = QHBoxLayout()
        self._title = QLabel("GTranslate Günlüğü")
        self._title.setObjectName("Title")
        hdr.addWidget(self._title)
        hdr.addStretch()

        self.btn_pin = QPushButton("...")
        self.btn_pin.setCheckable(True)
        self.btn_pin.setChecked(False) # Default unpinned
        self.btn_pin.setFixedSize(55, 24)
        self.btn_pin.toggled.connect(self._on_pin_toggled)
        hdr.addWidget(self.btn_pin)

        self.btn_clear = QPushButton("...")
        self.btn_clear.setFixedSize(55, 24)
        self.btn_clear.clicked.connect(self.clear_log)
        hdr.addWidget(self.btn_clear)
        lay.addLayout(hdr)

        # -- Text area ---------------------------------------------------------
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        lay.addWidget(self.text_edit)

        # -- Size grip ---------------------------------------------------------
        grip_row = QHBoxLayout()
        grip_row.addStretch()
        grip = QSizeGrip(self._container)
        grip.setFixedSize(12, 12)
        grip_row.addWidget(grip)
        lay.addLayout(grip_row)

        outer.addWidget(self._container)
        self.setMinimumSize(300, 140)
        self.resize(400, 280)

    # -- macOS window level ----------------------------------------------------
    def _boost_level(self):
        """Force the window to stay on top and join all spaces (PiP mode)."""
        try:
            import objc
            from ctypes import c_void_p
            from AppKit import NSStatusWindowLevel, NSNormalWindowLevel
            
            ns_view = objc.objc_object(c_void_p=int(self.winId()))
            ns_win  = ns_view.window()
            if ns_win:
                ns_win.setHidesOnDeactivate_(False)
                if self._is_pinned:
                    ns_win.setLevel_(NSStatusWindowLevel)
                    ns_win.setCollectionBehavior_(1 << 2)  # CanJoinAllSpaces
                else:
                    ns_win.setLevel_(NSNormalWindowLevel) # Level 0
                    ns_win.setCollectionBehavior_(0)
        except Exception as e:
            print(f"[log] level boost: {e}")

    def showEvent(self, e):
        super().showEvent(e)
        self._boost_level()

    # -- Public API ------------------------------------------------------------
    def add_translation(self, text: str, color: str = None):
        """Append a new translation line. Skips if identical or too similar to last entry."""
        text = text.strip()
        if not text:
            return

        # Normalize for comparison
        norm = re.sub(r'\s+', ' ', re.sub(r'[^\w\s]', '', text.lower())).strip()

        # Exact match
        if norm == self._last_norm:
            return

        # Fuzzy match - same content with slight OCR/translation variance
        if self._last_norm:
            wa = set(norm.split())
            wb = set(self._last_norm.split())
            if wa and wb:
                sim = len(wa & wb) / len(wa | wb)
                if sim >= 0.50:   # >=50% word overlap -> treat as duplicate
                    return

        self._last_norm = norm
        self._entry_count += 1

        cursor = self.text_edit.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        # Separator between entries
        if self._entry_count > 1:
            sep_fmt = QTextCharFormat()
            sep_fmt.setForeground(QColor(60, 80, 120))
            cursor.insertText("\n" + "-"*20 + "\n", sep_fmt)

        # Translation text
        txt_fmt = QTextCharFormat()
        
        # Use detected color or default
        qcolor = QColor(color) if color else QColor(220, 235, 255)
        txt_fmt.setForeground(qcolor)
        
        txt_fmt.setFont(QFont("SF Pro Display", 14))
        cursor.insertText(text, txt_fmt)

        # Auto-scroll to bottom
        sb = self.text_edit.verticalScrollBar()
        sb.setValue(sb.maximum())
        
        # Ensure PiP stays on top
        self._boost_level()

    def clear_log(self):
        self.text_edit.clear()
        self._last_text   = ""
        self._last_norm   = ""
        self._entry_count = 0

    def _on_pin_toggled(self, checked):
        self._is_pinned = checked
        self._boost_level()
        self.retranslate_ui(self.current_lang)
        self.show() # Required after flag change

    def set_pinned(self, pinned: bool):
        self._is_pinned = pinned
        self._boost_level()
        self.show()

    def update_title(self, text: str):
        self._win_name = text
        self.retranslate_ui(self.current_lang)

    def retranslate_ui(self, lang_code):
        self.current_lang = lang_code
        t = self.i18n.get(lang_code, self.i18n["en"])
        
        base_title = t["title"]
        if self._win_name:
            self._title.setText(f"{base_title} - {self._win_name}")
        else:
            self._title.setText(base_title)
            
        self.btn_clear.setText(t["clear"])
        
        if self.btn_pin.isChecked():
            self.btn_pin.setText(t["pinned"])
        else:
            self.btn_pin.setText(t["pin"])

    # -- Drag to move ----------------------------------------------------------
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self.btn_pin.isChecked():
            return # Fixed position when pinned
        if self._drag_pos and e.buttons() == Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, e):
        self._drag_pos = None
