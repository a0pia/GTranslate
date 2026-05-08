"""
Screen capture using Quartz CGDisplayCreateImage.
Reliable for standalone .app bundles - uses the TCC permission
granted to the bundle directly, unlike screencapture subprocess.
"""
import Quartz
from Foundation import NSURL
import os
import tempfile


def check_and_request_permission():
    """
    Checks Screen Recording permission using CGPreflightScreenCaptureAccess.
    This NEVER triggers the system dialog - safe to call anytime.
    """
    return Quartz.CGPreflightScreenCaptureAccess()


def _capture_display_to_file(output_path: str) -> bool:
    """
    Captures the full display using CGDisplayCreateImage.
    Works reliably in standalone .app bundles with proper TCC permission.
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
    """Crops a region from a full-screen capture (Retina-aware)."""
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


def fast_capture_region(crop_region: dict, output_path: str = "win_capture.png") -> str | None:
    """Captures a screen region using CGDisplayCreateImage."""
    tmp_full = output_path + "_full.png"
    abs_path = os.path.abspath(output_path)
    try:
        if not _capture_display_to_file(tmp_full):
            return None
        x = crop_region.get('left', 0)
        y = crop_region.get('top', 0)
        w = crop_region.get('width', 100)
        h = crop_region.get('height', 100)
        if _crop_image(tmp_full, x, y, w, h, abs_path):
            return abs_path
        return None
    finally:
        try:
            if os.path.exists(tmp_full):
                os.remove(tmp_full)
        except Exception:
            pass


def get_open_windows():
    """Returns a list of all visible, on-screen windows."""
    options = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
    windows_info = Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID)
    result = []

    for w in windows_info:
        app_name = w.get('kCGWindowOwnerName', '')
        title = w.get('kCGWindowName', '') or ''
        wid = w.get('kCGWindowNumber', 0)
        bounds = w.get('kCGWindowBounds', {})
        layer = w.get('kCGWindowLayer', 0)

        if layer != 0 and not title:
            continue
        if not app_name or app_name in ('Window Server', 'Dock', 'SystemUIServer'):
            continue

        display_name = f"[{wid}] {app_name}" + (f" - {title}" if title else "")
        x = bounds.get('X', 0)
        y = bounds.get('Y', 0)
        w_size = bounds.get('Width', 0)
        h_size = bounds.get('Height', 0)

        if w_size < 50 or h_size < 50:
            continue

        result.append({
            'id': wid,
            'name': app_name,
            'title': title,
            'display': display_name,
            'bounds': (int(x), int(y), int(w_size), int(h_size))
        })
    return result


def capture_window(window_info, output_path="win_capture.png"):
    """
    Captures only the area of the screen where the selected window is located.
    1. Capture full screen.
    2. Crop to window bounds.
    """
    abs_path = os.path.abspath(output_path)
    x, y, w, h = window_info['bounds']
    
    tmp_full = abs_path + "_full.png"
    try:
        if _capture_display_to_file(tmp_full):
            if _crop_image(tmp_full, x, y, w, h, abs_path):
                return abs_path, {"left": x, "top": y, "width": w, "height": h}
    finally:
        if os.path.exists(tmp_full):
            try: os.remove(tmp_full)
            except: pass

    print(f"[capture_window] Capture failed for window {window_info.get('id')}")
    return None, None


def capture_window_region(window_info, crop_region, output_path="win_capture.png"):
    """Captures a specific region of the screen."""
    abs_path = os.path.abspath(output_path)
    if crop_region:
        result = fast_capture_region(crop_region, abs_path)
        if result:
            return abs_path, crop_region
        return None, None
    return capture_window(window_info, output_path)
