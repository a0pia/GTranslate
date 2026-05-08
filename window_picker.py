import Quartz
from Foundation import NSURL
import os
import subprocess

try:
    import mss
    import mss.tools
    _MSS_AVAILABLE = True
except ImportError:
    _MSS_AVAILABLE = False


def check_and_request_permission():
    """
    Checks if Screen Recording permission is granted.
    Does NOT show popups.
    """
    import Quartz
    # Just preflight check, no prompts
    return Quartz.CGPreflightScreenCaptureAccess()

def fast_capture_region(crop_region: dict, output_path: str = "win_capture.png") -> str | None:
    """
    Ultra-fast region capture using mss (direct framebuffer, no subprocess).
    crop_region: {left, top, width, height} in LOGICAL screen coordinates.
    Returns output_path on success, None on failure.
    Falls back to screencapture subprocess if mss fails.
    """
    abs_path = os.path.abspath(output_path)

    # -- Fast path: mss --------------------------------------------------------
    if _MSS_AVAILABLE:
        try:
            with mss.mss() as sct:
                shot = sct.grab(crop_region)
                mss.tools.to_png(shot.rgb, shot.size, output=abs_path)
            if os.path.exists(abs_path) and os.path.getsize(abs_path) > 1000:
                return abs_path
        except Exception as e:
            print(f"[fast_capture] mss failed: {e}, falling back to screencapture")

    # -- Fallback: screencapture subprocess ------------------------------------
    tmp_full = abs_path + "_full.png"
    try:
        result = subprocess.run(
            ['screencapture', '-x', tmp_full],
            capture_output=True, timeout=5
        )
        if result.returncode == 0 and os.path.exists(tmp_full) and os.path.getsize(tmp_full) > 10000:
            cx = crop_region['left']
            cy = crop_region['top']
            cw = crop_region['width']
            ch = crop_region['height']
            if _crop_image(tmp_full, cx, cy, cw, ch, abs_path):
                return abs_path
    except Exception as e:
        print(f"[fast_capture] screencapture fallback failed: {e}")
    finally:
        if os.path.exists(tmp_full):
            try:
                os.remove(tmp_full)
            except Exception:
                pass
    return None

def get_open_windows():
    """
    Returns a list of all visible, on-screen windows with their info.
    """
    options = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
    windows_info = Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID)

    result = []
    seen = set()

    for w in windows_info:
        app_name = w.get('kCGWindowOwnerName', '')
        title = w.get('kCGWindowName', '') or ''
        wid = w.get('kCGWindowNumber', 0)
        bounds = w.get('kCGWindowBounds', {})
        layer = w.get('kCGWindowLayer', 0)

        # Allow layer 0 (normal) and some others if they have titles
        if layer != 0 and not title:
            continue
            
        if not app_name or app_name in ('Window Server', 'Dock', 'SystemUIServer'):
            continue

        # Use ID to make display name unique
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
    Captures a specific window's content using multiple strategies.
    """
    wid = window_info['id']
    abs_path = os.path.abspath(output_path)
    x, y, w, h = window_info['bounds']
    region = {"left": x, "top": y, "width": w, "height": h}

    # --- Strategy 1: screencapture -l <window_id> (BEST for macOS window-locking) ---
    try:
        result = subprocess.run(
            ['screencapture', '-l', str(wid), '-x', abs_path],
            capture_output=True, timeout=3
        )
        if result.returncode == 0 and os.path.exists(abs_path):
            if os.path.getsize(abs_path) > 10000:
                return abs_path, region
    except Exception:
        pass

    # --- Strategy 2: CGWindowListCreateImage (Truly window-based fallback) ---
    image = Quartz.CGWindowListCreateImage(
        Quartz.CGRectNull,
        Quartz.kCGWindowListOptionIncludingWindow,
        wid,
        Quartz.kCGWindowImageBoundsIgnoreFraming
    )
    if image is not None:
        url = NSURL.fileURLWithPath_(abs_path)
        dest = Quartz.CGImageDestinationCreateWithURL(url, 'public.png', 1, None)
        if dest:
            Quartz.CGImageDestinationAddImage(dest, image, None)
            if Quartz.CGImageDestinationFinalize(dest):
                if os.path.exists(abs_path) and os.path.getsize(abs_path) > 10000:
                    return abs_path, region

    # --- Strategy 3: mss (Fast but screen-based) ---
    if _MSS_AVAILABLE:
        try:
            with mss.mss() as sct:
                shot = sct.grab(region)
                mss.tools.to_png(shot.rgb, shot.size, output=abs_path)
            if os.path.exists(abs_path) and os.path.getsize(abs_path) > 10000:
                return abs_path, region
        except Exception as e:
            print(f"[capture_window] mss fallback failed: {e}")

    # --- Strategy 4: Full screen → crop to window bounds ---
    tmp_full = abs_path + "_fullscreen.png"
    try:
        success = False
        if _MSS_AVAILABLE:
            with mss.mss() as sct:
                shot = sct.shot(output=tmp_full)
                if os.path.exists(tmp_full): success = True
        
        if not success:
            result = subprocess.run(
                ['screencapture', '-x', tmp_full],
                capture_output=True, timeout=5
            )
            success = (result.returncode == 0 and os.path.exists(tmp_full))

        if success and os.path.getsize(tmp_full) > 10000:
            cropped = _crop_image(tmp_full, x, y, w, h, abs_path)
            if cropped:
                return abs_path, region
    except Exception as e:
        print(f"Full-screen capture fallback failed: {e}")
    finally:
        if os.path.exists(tmp_full):
            try: os.remove(tmp_full)
            except: pass

    print("HATA: Tum yakalama yontemleri basarisiz oldu. Ekran Kaydi iznini kontrol edin.")
    return None, None


def _crop_image(src_path, x, y, w, h, out_path):
    """
    Crops a region from src_path and saves to out_path using Quartz.
    Handles Retina (HiDPI) displays by checking actual pixel dimensions.
    """
    # Load source image
    url = NSURL.fileURLWithPath_(src_path)
    src_img = Quartz.CGImageSourceCreateWithURL(url, None)
    if not src_img:
        return False
    cg_img = Quartz.CGImageSourceCreateImageAtIndex(src_img, 0, None)
    if not cg_img:
        return False

    img_w = Quartz.CGImageGetWidth(cg_img)
    img_h = Quartz.CGImageGetHeight(cg_img)

    # Detect HiDPI scale factor (Retina = 2x)
    # We get the logical screen size from Quartz
    screen = Quartz.CGDisplayBounds(Quartz.CGMainDisplayID())
    logical_w = screen.size.width
    scale = img_w / logical_w if logical_w > 0 else 1.0

    # Scale crop rect to actual pixel coords
    px = int(x * scale)
    py = int(y * scale)
    pw = int(w * scale)
    ph = int(h * scale)

    # Clamp to image bounds
    px = max(0, min(px, img_w - 1))
    py = max(0, min(py, img_h - 1))
    pw = min(pw, img_w - px)
    ph = min(ph, img_h - py)

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


def capture_window_region(window_info, crop_region, output_path="win_capture.png"):
    """
    If crop_region is provided ({left, top, width, height} in SCREEN coords),
    captures only that rectangular area from the screen - much faster and focused.
    Otherwise falls back to capturing the full window.
    """
    abs_path = os.path.abspath(output_path)
    tmp_full = abs_path + "_full.png"

    if crop_region:
        # Direct full-screen capture then crop to the exact region
        try:
            result = subprocess.run(
                ['screencapture', '-x', tmp_full],
                capture_output=True, timeout=5
            )
            if result.returncode == 0 and os.path.exists(tmp_full) and os.path.getsize(tmp_full) > 10000:
                cx = crop_region['left']
                cy = crop_region['top']
                cw = crop_region['width']
                ch = crop_region['height']
                if _crop_image(tmp_full, cx, cy, cw, ch, abs_path):
                    return abs_path, crop_region
        except Exception as e:
            print(f"Region capture failed: {e}")
        finally:
            if os.path.exists(tmp_full):
                os.remove(tmp_full)
        return None, None

    # No crop region → capture the whole window
    return capture_window(window_info, output_path)
