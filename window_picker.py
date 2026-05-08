import Quartz
from Foundation import NSURL
import os
import subprocess


def check_and_request_permission():
    """
    Checks if Screen Recording permission is granted silently.
    """
    return Quartz.CGPreflightScreenCaptureAccess()


def _screencapture_region(x, y, w, h, output_path):
    """
    Uses Apple's system screencapture binary to capture a screen region.
    This is the ONLY method that reliably works from a standalone .app bundle
    because screencapture is Apple-signed and inherits the app's TCC permission.
    """
    abs_path = os.path.abspath(output_path)
    try:
        result = subprocess.run(
            ['/usr/sbin/screencapture', '-x', '-R', f'{int(x)},{int(y)},{int(w)},{int(h)}', abs_path],
            capture_output=True,
            timeout=5
        )
        if result.returncode == 0 and os.path.exists(abs_path) and os.path.getsize(abs_path) > 1000:
            return abs_path
    except Exception as e:
        print(f"[screencapture] Region capture failed: {e}")
    return None


def _screencapture_window(wid, output_path):
    """
    Captures a specific window by ID using Apple's screencapture binary.
    """
    abs_path = os.path.abspath(output_path)
    try:
        result = subprocess.run(
            ['/usr/sbin/screencapture', '-x', '-l', str(wid), abs_path],
            capture_output=True,
            timeout=5
        )
        if result.returncode == 0 and os.path.exists(abs_path) and os.path.getsize(abs_path) > 1000:
            return abs_path
    except Exception as e:
        print(f"[screencapture] Window capture failed: {e}")
    return None


def fast_capture_region(crop_region: dict, output_path: str = "win_capture.png") -> str | None:
    """
    Captures a specific screen region using Apple's system screencapture.
    crop_region: {left, top, width, height} in LOGICAL screen coordinates.
    Returns output_path on success, None on failure.
    """
    x = crop_region.get('left', 0)
    y = crop_region.get('top', 0)
    w = crop_region.get('width', 100)
    h = crop_region.get('height', 100)
    return _screencapture_region(x, y, w, h, output_path)


def get_open_windows():
    """
    Returns a list of all visible, on-screen windows with their info.
    """
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
    Captures a window's content using Apple's screencapture binary.
    Strategy 1: Window-locked capture by window ID.
    Strategy 2: Region capture (by screen coordinates).
    """
    wid = window_info['id']
    abs_path = os.path.abspath(output_path)
    x, y, w, h = window_info['bounds']
    region = {"left": x, "top": y, "width": w, "height": h}

    # --- Strategy 1: screencapture by window ID ---
    result = _screencapture_window(wid, abs_path)
    if result:
        return abs_path, region

    # --- Strategy 2: screencapture by screen region ---
    result = _screencapture_region(x, y, w, h, abs_path)
    if result:
        return abs_path, region

    print(f"[capture_window] All strategies failed for window {wid}")
    return None, None


def capture_window_region(window_info, crop_region, output_path="win_capture.png"):
    """
    Captures a specific region of the screen.
    If crop_region is provided, captures that exact region.
    Otherwise captures the full window.
    """
    abs_path = os.path.abspath(output_path)

    if crop_region:
        x = crop_region.get('left', 0)
        y = crop_region.get('top', 0)
        w = crop_region.get('width', 100)
        h = crop_region.get('height', 100)
        result = _screencapture_region(x, y, w, h, abs_path)
        if result:
            return abs_path, crop_region
        return None, None

    # No crop region → capture the whole window
    return capture_window(window_info, output_path)
