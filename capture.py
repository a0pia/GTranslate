import subprocess
import os
from PyQt6.QtWidgets import QWidget, QRubberBand, QApplication
from PyQt6.QtCore import QRect, QSize, Qt, QPoint, QEventLoop
from PyQt6.QtGui import QScreen


class RegionSelector(QWidget):
    """
    Transparent full-screen overlay for user to drag-select a region.
    """
    def __init__(self):
        super().__init__()
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
        self.origin = QPoint()
        self.selected_region = None

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

    def select_region(self):
        selector = RegionSelector()
        loop = QEventLoop()
        selector.destroyed.connect(loop.quit)
        selector.start_selection()
        loop.exec()
        self.region = selector.selected_region
        return self.region

    def capture(self, output_path="capture.png"):
        """
        Captures the selected region using Apple's screencapture binary.
        This is the ONLY reliable method for standalone .app bundles.
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
                    '-x',                          # no sound
                    '-R', f'{int(x)},{int(y)},{int(w)},{int(h)}',
                    abs_path
                ],
                capture_output=True,
                timeout=5
            )
            if result.returncode == 0 and os.path.exists(abs_path) and os.path.getsize(abs_path) > 100:
                return abs_path
            else:
                print(f"[CaptureManager] screencapture failed: returncode={result.returncode}, stderr={result.stderr}")
                return None
        except Exception as e:
            print(f"[CaptureManager] Capture error: {e}")
            return None


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
