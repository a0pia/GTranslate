"""
Screen capture using Quartz CGDisplayCreateImage - the most reliable
method for bundled macOS apps. Avoids screencapture subprocess TCC issues.
"""
import os
import tempfile
import subprocess

import Quartz
from Foundation import NSURL

from PyQt6.QtWidgets import QWidget, QRubberBand, QApplication, QLabel
from PyQt6.QtCore import QRect, QSize, Qt, QPoint, QEventLoop
from PyQt6.QtGui import QPixmap, QPainter, QColor, QFont


def _capture_display_to_file(output_path: str) -> bool:
    """
    Captures the entire display using CGDisplayCreateImage.
    This is the most reliable API for bundled apps - it uses the
    display framebuffer directly and properly respects TCC permissions.
    """
    abs_path = os.path.abspath(output_path)
    try:
        display_id = Quartz.CGMainDisplayID()
        image = Quartz.CGDisplayCreateImage(display_id)
        if image is None:
            return False

        url = NSURL.fileURLWithPath_(abs_path)
        dest = Quartz.CGImageDestinationCreateWithURL(url, 'public.png', 1, None)
        if dest is None:
            return False

        Quartz.CGImageDestinationAddImage(dest, image, None)
        if not Quartz.CGImageDestinationFinalize(dest):
            return False

        return os.path.exists(abs_path) and os.path.getsize(abs_path) > 1000
    except Exception as e:
        print(f"[_capture_display_to_file] Error: {e}")
        return False


def _crop_image(src_path: str, x: int, y: int, w: int, h: int, out_path: str) -> bool:
    """Crops a region from a full-screen capture using Quartz (Retina-aware)."""
    try:
        url = NSURL.fileURLWithPath_(src_path)
        src_img = Quartz.CGImageSourceCreateWithURL(url, None)
        if not src_img:
            return False
        cg_img = Quartz.CGImageSourceCreateImageAtIndex(src_img, 0, None)
        if not cg_img:
            return False

        img_w = Quartz.CGImageGetWidth(cg_img)
        img_h = Quartz.CGImageGetHeight(cg_img)

        # Detect HiDPI / Retina scale
        screen = Quartz.CGDisplayBounds(Quartz.CGMainDisplayID())
        logical_w = screen.size.width
        scale = img_w / logical_w if logical_w > 0 else 1.0

        px = max(0, int(x * scale))
        py = max(0, int(y * scale))
        pw = min(int(w * scale), img_w - px)
        ph = min(int(h * scale), img_h - py)

        if pw <= 0 or ph <= 0:
            return False

        crop_rect = Quartz.CGRectMake(px, py, pw, ph)
        cropped = Quartz.CGImageCreateWithImageInRect(cg_img, crop_rect)
        if not cropped:
            return False

        out_url = NSURL.fileURLWithPath_(out_path)
        dest = Quartz.CGImageDestinationCreateWithURL(out_url, 'public.png', 1, None)
        if not dest:
            return False
        Quartz.CGImageDestinationAddImage(dest, cropped, None)
        return Quartz.CGImageDestinationFinalize(dest)
    except Exception as e:
        print(f"[_crop_image] Error: {e}")
        return False


class RegionSelector(QWidget):
    """
    Full-screen region selector that shows a frozen screenshot background
    so users can see all windows while selecting a region.
    """
    def __init__(self, screenshot_path: str = ""):
        super().__init__()
        self.selected_region = None
        self.origin = QPoint()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        self._pixmap = QPixmap(screenshot_path) if screenshot_path else QPixmap()
        self.rubberBand = QRubberBand(QRubberBand.Shape.Rectangle, self)

    def start_selection(self):
        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(screen)
        self.show()
        self.raise_()
        self.activateWindow()

    def paintEvent(self, event):
        painter = QPainter(self)
        if not self._pixmap.isNull():
            painter.drawPixmap(0, 0, self.width(), self.height(), self._pixmap)
        # Semi-transparent dark overlay
        painter.fillRect(self.rect(), QColor(0, 0, 0, 80))
        # Instruction text
        painter.setPen(QColor(255, 255, 255, 220))
        font = QFont()
        font.setPointSize(13)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(
            self.rect(),
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter,
            "\n  Bolge Sec - surukle ve birak  |  ESC: iptal"
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
    Manages screen region selection and capture using Quartz CGDisplayCreateImage.
    """
    def __init__(self):
        self.region = None
        self._tmp_dir = tempfile.mkdtemp()

    def _take_fullscreen(self) -> str | None:
        """Takes a full screenshot using CGDisplayCreateImage."""
        path = os.path.join(self._tmp_dir, "fullscreen.png")
        if _capture_display_to_file(path):
            return path
        return None

    def select_region(self):
        """Shows a frozen screenshot background for region selection."""
        screenshot_path = self._take_fullscreen() or ""
        selector = RegionSelector(screenshot_path)
        loop = QEventLoop()
        selector.destroyed.connect(loop.quit)
        selector.start_selection()
        loop.exec()
        self.region = selector.selected_region
        return self.region

    def capture(self, output_path: str = "capture.png") -> str | None:
        """Captures the selected region using CGDisplayCreateImage."""
        if not self.region:
            print("No region selected!")
            return None

        x = self.region.get('left', 0)
        y = self.region.get('top', 0)
        w = self.region.get('width', 100)
        h = self.region.get('height', 100)

        tmp_full = os.path.join(self._tmp_dir, "cap_full.png")
        abs_out = os.path.abspath(output_path)

        if not _capture_display_to_file(tmp_full):
            print("[CaptureManager] Full display capture failed.")
            return None

        if _crop_image(tmp_full, x, y, w, h, abs_out):
            return abs_out

        print("[CaptureManager] Crop failed.")
        return None
