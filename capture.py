import subprocess
import os
import tempfile
from PyQt6.QtWidgets import QWidget, QRubberBand, QApplication, QLabel
from PyQt6.QtCore import QRect, QSize, Qt, QPoint, QEventLoop
from PyQt6.QtGui import QPixmap, QScreen, QPainter, QColor, QFont


class RegionSelector(QWidget):
    """
    Full-screen region selector that first captures a screenshot,
    then displays it as the background so users can see all windows.
    This is the standard approach used by professional capture tools.
    """
    def __init__(self, screenshot_path: str):
        super().__init__()
        self.selected_region = None
        self.origin = QPoint()
        self._screenshot_path = screenshot_path

        # Frameless, always on top, full screen
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        # Load the screenshot as background
        self._pixmap = QPixmap(screenshot_path)

        # Rubber band for selection
        self.rubberBand = QRubberBand(QRubberBand.Shape.Rectangle, self)

    def start_selection(self):
        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(screen)
        self.show()
        self.raise_()
        self.activateWindow()

    def paintEvent(self, event):
        painter = QPainter(self)
        # Draw the frozen screenshot as background
        if not self._pixmap.isNull():
            painter.drawPixmap(0, 0, self.width(), self.height(), self._pixmap)
        # Draw a dark overlay so the selection stands out
        painter.fillRect(self.rect(), QColor(0, 0, 0, 80))
        # Draw instruction text
        painter.setPen(QColor(255, 255, 255, 200))
        font = QFont()
        font.setPointSize(13)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(
            self.rect(),
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter,
            "\n  Bolge Sec - surukle ve birak -> onaylanir  |  ESC: iptal"
        )

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.selected_region = None
            self.close()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.origin = event.pos()
            self.rubberBand.setGeometry(QRect(self.origin, QSize()))
            self.rubberBand.show()

    def mouseMoveEvent(self, event):
        if not self.origin.isNull():
            self.rubberBand.setGeometry(QRect(self.origin, event.pos()).normalized())

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.rubberBand.hide()
            rect = self.rubberBand.geometry()
            if rect.width() > 10 and rect.height() > 10:
                self.selected_region = {
                    "left": rect.x(),
                    "top": rect.y(),
                    "width": rect.width(),
                    "height": rect.height()
                }
            self.close()


class CaptureManager:
    """
    Manages screen region selection and capture.
    Uses Apple's /usr/sbin/screencapture binary for reliable
    permission handling in standalone .app bundles.
    """
    def __init__(self):
        self.region = None
        self._tmp_dir = tempfile.mkdtemp()

    def _take_fullscreen(self) -> str | None:
        """Takes a full screenshot using Apple's screencapture binary."""
        path = os.path.join(self._tmp_dir, "fullscreen.png")
        try:
            result = subprocess.run(
                ['/usr/sbin/screencapture', '-x', '-C', path],
                capture_output=True,
                timeout=5
            )
            if result.returncode == 0 and os.path.exists(path) and os.path.getsize(path) > 10000:
                return path
        except Exception as e:
            print(f"[CaptureManager] Fullscreen capture failed: {e}")
        return None

    def select_region(self):
        """
        Takes a screenshot first, then shows it as background for region selection.
        This ensures all application windows are visible during selection.
        """
        # Step 1: Capture full screen BEFORE showing overlay
        screenshot_path = self._take_fullscreen()

        if not screenshot_path:
            print("[CaptureManager] Could not take fullscreen screenshot for selector background.")
            # Fallback: plain dark selector
            screenshot_path = ""

        # Step 2: Show selector with screenshot as background
        selector = RegionSelector(screenshot_path) if screenshot_path else _FallbackSelector()
        loop = QEventLoop()
        selector.destroyed.connect(loop.quit)
        selector.start_selection()
        loop.exec()

        self.region = selector.selected_region
        return self.region

    def capture(self, output_path="capture.png") -> str | None:
        """
        Captures the selected region using Apple's screencapture binary.
        """
        if not self.region:
            print("No region selected!")
            return None

        x = self.region.get('left', 0)
        y = self.region.get('top', 0)
        w = self.region.get('width', 100)
        h = self.region.get('height', 100)

        abs_path = os.path.abspath(output_path)

        try:
            result = subprocess.run(
                [
                    '/usr/sbin/screencapture',
                    '-x',
                    '-R', f'{int(x)},{int(y)},{int(w)},{int(h)}',
                    abs_path
                ],
                capture_output=True,
                timeout=5
            )
            if result.returncode == 0 and os.path.exists(abs_path) and os.path.getsize(abs_path) > 100:
                return abs_path
            else:
                print(f"[CaptureManager] screencapture failed: rc={result.returncode}, stderr={result.stderr.decode()}")
                return None
        except Exception as e:
            print(f"[CaptureManager] Capture error: {e}")
            return None


class _FallbackSelector(QWidget):
    """Minimal fallback selector when screenshot background is unavailable."""
    def __init__(self):
        super().__init__()
        self.selected_region = None
        self.origin = QPoint()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setWindowOpacity(0.3)
        self.setStyleSheet("background-color: black;")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.rubberBand = QRubberBand(QRubberBand.Shape.Rectangle, self)

    def start_selection(self):
        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(screen)
        self.show()
        self.raise_()
        self.activateWindow()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.origin = event.pos()
            self.rubberBand.setGeometry(QRect(self.origin, QSize()))
            self.rubberBand.show()

    def mouseMoveEvent(self, event):
        if not self.origin.isNull():
            self.rubberBand.setGeometry(QRect(self.origin, event.pos()).normalized())

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.rubberBand.hide()
            rect = self.rubberBand.geometry()
            if rect.width() > 10 and rect.height() > 10:
                self.selected_region = {
                    "left": rect.x(),
                    "top": rect.y(),
                    "width": rect.width(),
                    "height": rect.height()
                }
            self.close()


if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)
    cm = CaptureManager()
    print("Selecting region...")
    region = cm.select_region()
    print(f"Selected: {region}")
    if region:
        path = cm.capture()
        print(f"Captured to {path}")
