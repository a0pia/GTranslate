import time
from PyQt6.QtWidgets import QWidget, QLabel
from PyQt6.QtCore import Qt


class TranslationLabel(QWidget):
    """
    A single floating translation label.
    Uses macOS NSStatusWindowLevel (25) so it appears above game windows.
    Stays visible for `hold_ms` milliseconds even after text changes.
    """

    def __init__(self):
        super().__init__(None)  # top-level window, no parent
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool |
            Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        self.label = QLabel(self)
        self.label.setWordWrap(True)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._shown_at  = -999999.0   # never shown yet
        self._hold_ms   = 4000
        self._level_set = False       # NSWindow level boosted?

    # ── macOS window level boost ──────────────────────────────────────────────
    def _boost_level(self):
        """Raise NSWindow to NSStatusWindowLevel (25) on first show."""
        if self._level_set:
            return
        try:
            import objc
            from AppKit import NSStatusWindowLevel
            ns_view = objc.objc_object(c_void_p=int(self.winId()))
            ns_win  = ns_view.window()
            if ns_win:
                ns_win.setLevel_(NSStatusWindowLevel)
                # Also make it appear on all Spaces
                ns_win.setCollectionBehavior_(
                    1 << 2   # NSWindowCollectionBehaviorCanJoinAllSpaces = 1<<2
                )
            self._level_set = True
        except Exception as e:
            print(f"[overlay] window level boost failed: {e}")

    # ── Style ─────────────────────────────────────────────────────────────────
    def _apply_style(self, font_size: int):
        self.label.setStyleSheet(f"""
            QLabel {{
                color: #ffffff;
                background-color: rgba(8, 8, 24, 230);
                border: 1px solid rgba(100, 160, 255, 110);
                border-radius: 7px;
                padding: 4px 10px;
                font-family: 'SF Pro Display', 'Helvetica Neue', Arial, sans-serif;
                font-size: {font_size}px;
                font-weight: 600;
            }}
        """)

    # ── Public API ────────────────────────────────────────────────────────────
    def set_hold_ms(self, ms: int):
        self._hold_ms = ms

    def update_label(self, text: str, x: int, y: int, w: int, h: int):
        font_size = max(13, min(int(h * 0.52), 26))
        self._apply_style(font_size)
        self.label.setText(text)
        self.label.setFixedSize(w, h)
        self.resize(w, h)
        self.move(x, y)
        self._shown_at = time.monotonic()
        self.show()
        self.raise_()
        self._boost_level()   # sets NSStatusWindowLevel once

    def try_hide(self):
        """Hide only if hold duration has elapsed."""
        if (time.monotonic() - self._shown_at) * 1000 >= self._hold_ms:
            self.hide()


# ── Overlay manager ───────────────────────────────────────────────────────────
class FullScreenOverlay:
    """
    Pool of TranslationLabel widgets.
    New translations replace old ones; old labels stay visible until hold_ms elapses.
    """

    def __init__(self, hold_ms: int = 4000):
        self._labels: list[TranslationLabel] = []
        self._hold_ms = hold_ms

    def set_hold_ms(self, ms: int):
        self._hold_ms = ms
        for lbl in self._labels:
            lbl.set_hold_ms(ms)

    def update_translations(self, translations: list[dict]):
        """
        translations: list of {x, y, w, h, text}
        Always updates — no stability check that would silently drop updates.
        """
        # Grow pool if needed
        while len(self._labels) < len(translations):
            lbl = TranslationLabel()
            lbl.set_hold_ms(self._hold_ms)
            self._labels.append(lbl)

        # Update active labels
        for i, item in enumerate(translations):
            self._labels[i].update_label(
                item['text'],
                item['x'], item['y'],
                item['w'], item['h']
            )

        # Hide extra labels only after hold time
        for i in range(len(translations), len(self._labels)):
            self._labels[i].try_hide()

    def hide_all(self):
        for lbl in self._labels:
            lbl.hide()
