import Vision
import Quartz
from Foundation import NSURL
import os

try:
    from PIL import Image, ImageEnhance, ImageFilter
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False


def _preprocess_image(path: str) -> str:
    """
    Pre-processes a screenshot for better Vision OCR accuracy:
    - Upscales small images (Vision needs ≥ ~1000px width for good results)
    - Boosts contrast (helps with dark/stylized game UI backgrounds)
    - Sharpens (helps with antialiased game fonts)
    Returns path to processed image (may be the same path if PIL unavailable).
    """
    if not _PIL_AVAILABLE:
        return path
    try:
        img = Image.open(path).convert('RGB')
        w, h = img.size

        # Upscale if smaller than 1000px wide (gives Vision more pixels to work with)
        if w < 1000:
            scale = max(2.0, 1200 / w)
            new_w, new_h = int(w * scale), int(h * scale)
            img = img.resize((new_w, new_h), Image.LANCZOS)

        # Contrast boost — makes text pop against game backgrounds
        img = ImageEnhance.Contrast(img).enhance(1.4)

        # Slight sharpening — helps antialiased/blurry game fonts
        img = img.filter(ImageFilter.SHARPEN)

        out = path + '_proc.png'
        img.save(out, 'PNG')
        return out
    except Exception as e:
        print(f"[preprocess] {e}")
        return path


def _get_dominant_color_from_img(img: Image.Image, norm_bbox: dict) -> str:
    """
    Extracts dominant color from an already opened PIL image.
    Prioritizes vibrant/saturated colors (speaker identifiers) over background.
    """
    try:
        w, h = img.size
        # Convert normalized coords to pixel coords
        left   = int(norm_bbox['x'] * w)
        top    = int(norm_bbox['y'] * h)
        width  = int(norm_bbox['w'] * w)
        height = int(norm_bbox['h'] * h)
        
        # Clamp
        left, top = max(0, min(left, w-1)), max(0, min(top, h-1))
        width, height = max(1, min(width, w-left)), max(1, min(height, h-top))
        
        crop = img.crop((left, top, left + width, top + height))
        # Higher resolution for density-based color analysis
        crop = crop.resize((30, 30), Image.BILINEAR)
        
        colors = crop.getcolors(900) 
        if not colors: return "#ddeeff"
            
        # ── 1. Find Background Color (Most frequent non-vibrant color) ────────
        # This helps us avoid picking up the game world behind the text.
        bg_color = None
        # Sorting by frequency (count)
        for count, (r, g, b) in sorted(colors, key=lambda x: x[0], reverse=True):
            mx = max(r, g, b)
            sat = (mx - min(r, g, b)) / mx if mx > 0 else 0
            if sat < 0.20: # Likely background (gray/black/dark)
                bg_color = (r, g, b)
                break

        best_color = None
        max_score  = -1.0
        
        for count, (r, g, b) in colors:
            # 1. Brightness check
            brightness = (r * 299 + g * 587 + b * 114) / 1000
            if brightness < 35: continue
            
            # 2. Saturation (Vibrancy)
            mn, mx = min(r, g, b), max(r, g, b)
            sat = (mx - mn) / mx if mx > 0 else 0
            
            # 3. Dynamic Scoring
            # We give a massive boost to vibrant colors.
            sat_boost = 1.0 + (sat ** 1.5) * 20.0
            score = (count * 0.1) * sat_boost * (brightness / 255.0)
            
            # ── 4. Background Penalty ──
            # If this color is very close to the detected background, penalize it heavily.
            if bg_color:
                bg_dist = abs(r - bg_color[0]) + abs(g - bg_color[1]) + abs(b - bg_color[2])
                if bg_dist < 45:
                    score *= 0.05

            if score > max_score:
                max_score = score
                # Rounding stabilizes color shifts between frames
                rr, gg, bb = (r//8)*8, (g//8)*8, (b//8)*8
                best_color = f"#{rr:02x}{gg:02x}{bb:02x}"
        
        return best_color if best_color else "#ffffff"
    except:
        return "#ddeeff"


# Minimum word/character thresholds to avoid OCR noise
_MIN_TEXT_LEN   = 2    # ignore single-char results
_MIN_CONFIDENCE = 0.2  # permissive — game fonts can have low Vision confidence


class OCREngine:
    def recognize_text_with_bounds(self, image_path: str) -> list[dict]:
        """
        Runs Apple Vision OCR on image_path.
        Returns a list of text blocks, where spatially adjacent words on the
        same visual line are merged into complete sentences/phrases.
        Each block: {text, norm_x, norm_y, norm_w, norm_h}  (0.0–1.0 coords)
        """
        if not os.path.exists(image_path):
            return []

        # Preprocess image for better OCR on stylized game fonts
        proc_path = _preprocess_image(image_path)
        _cleanup_proc = (proc_path != image_path)  # track if we created a temp file

        url     = NSURL.fileURLWithPath_(proc_path)
        handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(url, {})
        raw     = []

        def _handler(request, error):
            if error:
                print(f"Vision OCR error: {error}")
                return
            observations = request.results()
            if not observations:
                return
            
            for obs in observations:
                conf = float(obs.confidence()) if hasattr(obs, 'confidence') else 1.0
                if conf < _MIN_CONFIDENCE:
                    continue
                candidates = obs.topCandidates_(1)
                if not candidates:
                    continue
                text = candidates[0].string()
                if not text or len(text.strip()) < _MIN_TEXT_LEN:
                    continue
                letters = sum(c.isalpha() for c in text)
                if letters == 0:
                    continue
 
                bbox   = obs.boundingBox()
                norm_x = bbox.origin.x
                norm_y = 1.0 - bbox.origin.y - bbox.size.height
                norm_w = bbox.size.width
                norm_h = bbox.size.height
                
                raw.append({
                    'text':   text.strip(),
                    'norm_x': norm_x,
                    'norm_y': norm_y,
                    'norm_w': norm_w,
                    'norm_h': norm_h,
                })

        req = Vision.VNRecognizeTextRequest.alloc().initWithCompletionHandler_(_handler)
        req.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
        req.setUsesLanguageCorrection_(True)
        try:
            req.setRecognitionLanguages_(['en-US'])
        except Exception:
            pass 

        ok, err = handler.performRequests_error_([req], None)
        if not ok:
            print(f"Vision request failed: {err}")

        # -- 1. Merge blocks first (FAST) --------------------------------------
        merged = _merge_adjacent_lines(raw)
        
        # -- 2. Add color ONLY to the final merged sentences (MUCH FASTER!) -----
        if _PIL_AVAILABLE and merged:
            try:
                color_img = Image.open(proc_path).convert('RGB')
                for m in merged:
                    m['color'] = _get_dominant_color_from_img(color_img, 
                        {'x': m['norm_x'], 'y': m['norm_y'], 'w': m['norm_w'], 'h': m['norm_h']})
                color_img.close()
            except:
                for m in merged: m['color'] = "#ddeeff"
        else:
            for m in merged: m['color'] = "#ddeeff"

        # Clean up temp preprocessed file
        if _cleanup_proc and os.path.exists(proc_path):
            try:
                os.remove(proc_path)
            except Exception:
                pass

        return merged


def _merge_adjacent_lines(blocks: list[dict],
                           y_tol: float = 0.03,
                           x_gap_max: float = 0.08) -> list[dict]:
    """
    Merges OCR blocks into sentences using two criteria:
      1. Same visual line - vertical centres within `y_tol`
      2. Spatially adjacent — horizontal gap between consecutive words ≤ `x_gap_max`

    This prevents merging text elements from opposite sides of the screen
    (e.g. a button on the left and a dialog line on the right) into garbage.
    """
    if not blocks:
        return []

    # Sort top-to-bottom first, then left-to-right
    blocks = sorted(blocks, key=lambda b: (b['norm_y'], b['norm_x']))

    # Group blocks into visual lines (close Y centre)
    lines: list[list[dict]] = []
    used = [False] * len(blocks)

    for i, b in enumerate(blocks):
        if used[i]:
            continue
        cy_i = b['norm_y'] + b['norm_h'] / 2.0
        line = [b]
        used[i] = True
        for j, other in enumerate(blocks):
            if used[j]:
                continue
            cy_j = other['norm_y'] + other['norm_h'] / 2.0
            if abs(cy_i - cy_j) <= y_tol:
                line.append(other)
                used[j] = True
        line.sort(key=lambda b: b['norm_x'])
        lines.append(line)

    # Within each visual line, only merge words that are close together (small X gap)
    result = []
    for line in lines:
        # Split line into adjacency groups
        groups: list[list[dict]] = []
        current_group = [line[0]]
        for k in range(1, len(line)):
            prev = current_group[-1]
            this = line[k]
            gap  = this['norm_x'] - (prev['norm_x'] + prev['norm_w'])
            if gap <= x_gap_max:
                current_group.append(this)
            else:
                groups.append(current_group)
                current_group = [this]
        groups.append(current_group)

        # Merge each adjacency group into one block
        for grp in groups:
            text  = ' '.join(b['text'] for b in grp)
            min_x = min(b['norm_x'] for b in grp)
            min_y = min(b['norm_y'] for b in grp)
            max_x = max(b['norm_x'] + b['norm_w'] for b in grp)
            max_y = max(b['norm_y'] + b['norm_h'] for b in grp)
            result.append({
                'text':   text,
                'norm_x': min_x,
                'norm_y': min_y,
                'norm_w': max_x - min_x,
                'norm_h': max_y - min_y
            })

    return result
