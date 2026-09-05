from rembg import remove, new_session
from PIL import Image
import numpy as np
import cv2
import io

# Cached rembg session to avoid reloading and ensure lightweight model is used
_session = None

def get_bg_session():
    global _session
    if _session is None:
        try:
            # u2netp is only ~4.5MB (fast download and inference)
            _session = new_session("u2netp")
        except Exception:
            _session = new_session("u2net")
    return _session

def get_image_without_bg(input_image):
    """
    Accepts a PIL Image or a NumPy (OpenCV) array.
    Removes the background and returns a PIL RGBA Image.
    Falls back gracefully to the original photo if model download or rembg fails.
    """
    # 1. If the input is a NumPy array (OpenCV), convert BGR to RGB
    if isinstance(input_image, np.ndarray):
        input_image = cv2.cvtColor(input_image, cv2.COLOR_BGR2RGB)
        input_image = Image.fromarray(input_image)

    # 2. rembg.remove with cached lightweight session
    try:
        session = get_bg_session()
        if session:
            output_image = remove(input_image, session=session)
            return output_image.convert("RGBA")
    except Exception as e:
        print(f"⚠️ rembg background removal failed ({e}), falling back to original photo.", flush=True)

    # Fallback: return image as RGBA without background removal
    return input_image.convert("RGBA")