import mss
import mss.tools
from PyQt6.QtWidgets import QWidget, QRubberBand, QApplication
from PyQt6.QtCore import QRect, QSize, Qt, QPoint, QEventLoop
import os

class RegionSelector(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
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
            # Convert screen geometry to mss format (left, top, width, height)
            self.selected_region = {
                "left": rect.x(),
                "top": rect.y(),
                "width": rect.width(),
                "height": rect.height()
            }
            self.close()

class CaptureManager:
    def __init__(self):
        self.sct = mss.mss()
        self.region = None

    def select_region(self):
        # Eğer zaten bir event loop varsa, yeni bir tane oluşturup bekleyeceğiz
        selector = RegionSelector()
        loop = QEventLoop()
        
        # Selector kapandığında loop'u bitir
        selector.destroyed.connect(loop.quit)
        
        selector.start_selection()
        loop.exec()
        
        self.region = selector.selected_region
        return self.region

    def capture(self, output_path="capture.png"):
        if not self.region:
            print("No region selected!")
            return None
        
        try:
            screenshot = self.sct.grab(self.region)
            mss.tools.to_png(screenshot.rgb, screenshot.size, output=output_path)
            return output_path
        except Exception as e:
            print(f"Capture Error: {e}")
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
