from PIL import Image, ImageDraw, ImageFont
import cv2
import numpy as np
from pathlib import Path
from datetime import date
from io import BytesIO

from app.config import BASE_DIR
from core.image.image_crop import crop_pdf_sections
from core.pdf.pdf_data_extractor import extract_user_data, clean_extracted_text
from core.pdf.images_from_pdf import extract_images_from_pdf
from core.image.image_black_and_white_conv import get_grayscale_image
from core.image.image_bg_remove import get_image_without_bg
# ======================
# 🔹 Constants and Paths
# ======================
LOCAL_FONTS_DIR = BASE_DIR / "fonts" / "truetype"
_local_am = LOCAL_FONTS_DIR / "abyssinica" / "AbyssinicaSIL-Regular.ttf"
_local_en = LOCAL_FONTS_DIR / "noto" / "NotoSans-Regular.ttf"

FONT_AMHARIC_DEFAULT = str(_local_am) if _local_am.exists() else "/usr/share/fonts/truetype/sil-abyssinica/AbyssinicaSIL-Regular.ttf"
FONT_ENGLISH_DEFAULT = str(_local_en) if _local_en.exists() else "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"

TEMPLATES_DIR = BASE_DIR / "data" / "templates"
TEMPLATE_PATH = TEMPLATES_DIR / "white_template_cur.png"
MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

def format_gregorian_date_display(date_str: str, format_type: str = "YYYY/MM/DD") -> str:
    """
    Format Gregorian date string into Ethiopian ID style.
    e.g. '1973/12/13' or '1997-11-30' -> '1997/11/30' (YYYY/MM/DD).
    """
    if not date_str:
        return ""
    clean = str(date_str).strip().replace("-", "/")
    parts = clean.split("/")
    if len(parts) != 3:
        return date_str
    try:
        if len(parts[0]) == 4:
            year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
        else:
            day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
        if not (1 <= month <= 12):
            return date_str
        if format_type == "YYYY/MM/DD":
            return f"{year:04d}/{month:02d}/{day:02d}"
        elif format_type == "DD/Mon/YYYY":
            mon_abbr = MONTH_NAMES[month - 1]
            return f"{day:02d}/{mon_abbr}/{year:04d}"
        else:
            return f"{day:02d}/{month:02d}/{year:04d}"
    except Exception:
        return date_str

TEMPLATE_FIELDS = {
    # Amharic Fields
    "name_am": {"type": "text", "coords": (242, 103), "lang": "am", "size": 19},
    "date_of_birth_et": {"type": "text", "coords": (242, 193), "lang": "am", "size": 17},
    "sex_am": {"type": "text", "coords": (242, 236), "lang": "am", "size": 17},
    "region_am": {"type": "text", "coords": (698, 148), "lang": "am", "size": 17},
    "zone_am": {"type": "text", "coords": (698, 190), "lang": "am", "size": 17},
    "woreda_am": {"type": "text", "coords": (698, 232), "lang": "am", "size": 17},

    # English / Numeric Fields
    "name_en": {"type": "text", "coords": (242, 132), "lang": "en", "size": 19},
    "date_of_birth_greg": {"type": "text", "coords": (242, 193), "lang": "en", "size": 17},
    "sex_en": {"type": "text", "coords": (314, 236), "lang": "en", "size": 17},
    "expiry_date": {"type": "text", "coords": (242, 273), "lang": "am", "size": 17},
    "phone_number": {"type": "text", "coords": (698, 52), "lang": "en", "size": 17},
    "nationality": {"type": "text", "coords": (698, 105), "lang": "am", "size": 17},
    "region_en": {"type": "text", "coords": (698, 168), "lang": "en", "size": 17},
    "zone_en": {"type": "text", "coords": (698, 210), "lang": "en", "size": 17},
    "woreda_en": {"type": "text", "coords": (698, 252), "lang": "en", "size": 17},
    "fan_code": {"type": "text", "coords": (283, 301), "lang": "en", "size": 17},

    # Image fields
    "photo": {"type": "image", "coords": (25, 80, 230, 363)},
    "qrcode": {"type": "image", "coords": (940, 25, 1265, 340)},
    "fin_code": {"type": "image", "coords": (685, 308, 915, 342)},
    "small_image": {"type": "image", "coords": (484, 260, 564, 380)},
    "barcode": {"type": "image", "coords": (270, 290, 458, 355)},
}

# ======================
# 🔹 Helper Functions
# ======================
def gregorian_to_ethiopian(g_y, g_m, g_d):
    ethiopian_month_lengths = [30] * 12 + [5]
    new_year_offset = 11
    g = date(g_y, g_m, g_d)
    e_new_year = date(g_y, 9, new_year_offset)
    if g < e_new_year:
        e_new_year = date(g_y - 1, 9, new_year_offset)
        e_year = g_y - 1 - 7
    else:
        e_year = g_y - 7

    delta = (g - e_new_year).days
    for m_idx, ml in enumerate(ethiopian_month_lengths):
        if delta < ml:
            return e_year, m_idx + 1, delta + 1
        delta -= ml
    return e_year, 13, delta + 1


def draw_bold_text(draw, position, text, font, fill=(0, 0, 0), boldness=1):
    """Draw text thicker by offset overlaying."""
    x, y = position
    for dx in range(int(boldness) + 1):
        for dy in range(int(boldness) + 1):
            draw.text((x + dx, y + dy), text, font=font, fill=fill)


def draw_vertical_text(base_img, position, text, font_path, font_size=22, fill=(0, 0, 0), boldness=1, scale=1):
    """Draw sharp vertical text (rotated upward) using supersampling."""
    try:
        font = ImageFont.truetype(font_path, font_size * scale)
    except Exception:
        font = ImageFont.load_default()

    # Make a transparent canvas for the text
    text_img = Image.new("RGBA", (500 * scale, 100 * scale), (255, 255, 255, 0))
    text_draw = ImageDraw.Draw(text_img)

    # Draw bold text
    for dx in range(int(boldness * scale) + 1):
        for dy in range(int(boldness * scale) + 1):
            text_draw.text((dx, dy), text, font=font, fill=fill)

    # Rotate upward
    rotated = text_img.rotate(90, expand=True)

    # Paste upward relative to the position
    x, y = position
    x *= scale
    y *= scale
    base_img.paste(rotated, (x, y - rotated.height), rotated)


# ======================
# 🔹 Main Function
# ======================
def generate_final_id_image(
    pdf_path: Path,
    output_dir: Path,
    font_amharic: str = FONT_AMHARIC_DEFAULT,
    font_english: str = FONT_ENGLISH_DEFAULT,
    font_size: int = 17, # Balanced default 17
    boldness: float = 0.5,
    dpi: int = 600,
    color: bool = True
) -> bytes:
    """
    Generate an Ethiopian ID card from a PDF.
    
    Args:
        pdf_path: Path to the input PDF file
        output_dir: Directory to save temporary crops (if needed)
        font_amharic: Path to Amharic font
        font_english: Path to English font
        font_size: Base font size
        boldness: Text stroke boldness multiplier
        dpi: Rendering DPI
        color: True for Color, False for Black and White
        
    Returns:
        bytes: High quality PNG image bytes of the ID card
    """
    # 1️⃣ Extract data and images in memory
    text_data = extract_user_data(pdf_path)
    image_crops = crop_pdf_sections(pdf_path, output_dir, dpi=dpi)
    second_images = extract_images_from_pdf(pdf_path)

    raw_photo = image_crops.get("photo")
    processed_photo = None
    if raw_photo is not None:
        try:
            processed_photo = get_image_without_bg(raw_photo)
        except Exception:
            if isinstance(raw_photo, np.ndarray):
                processed_photo = Image.fromarray(cv2.cvtColor(raw_photo, cv2.COLOR_BGR2RGB)).convert("RGBA")
            else:
                processed_photo = raw_photo.convert("RGBA")

    image_crops["photo"] = processed_photo
    image_crops["small_image"] = processed_photo
    image_crops["qrcode"] = second_images.get("qrcode")
    
    # 2️⃣ Load base template
    template_img = cv2.imread(str(TEMPLATE_PATH))
    if template_img is None:
        raise FileNotFoundError(f"Template not found at {TEMPLATE_PATH}")
    img_pil = Image.fromarray(cv2.cvtColor(template_img, cv2.COLOR_BGR2RGB))

    # 3️⃣ Supersampled drawing canvas
    scale = 3
    w, h = img_pil.size
    img_large = img_pil.resize((w * scale, h * scale), Image.Resampling.LANCZOS)
    draw_large = ImageDraw.Draw(img_large)

    # Load fonts
    try:
        font_am_large = ImageFont.truetype(font_amharic, font_size * scale)
    except Exception:
        font_am_large = ImageFont.load_default()
    try:
        font_en_large = ImageFont.truetype(font_english, font_size * scale)
    except Exception:
        font_en_large = font_am_large

    # 4️⃣ Generate date data (8-year validity, numeric format)
    today = date.today()
    e_year, e_month, e_day = gregorian_to_ethiopian(today.year, today.month, today.day)
    
    date_of_issue_greg = f"{today.year:04d}/{today.month:02d}/{today.day:02d}"
    date_of_issue_eth = f"{e_day:02d}/{e_month:02d}/{e_year:04d}"
    
    expiry_eth_date = f"{e_day:02d}/{e_month:02d}/{e_year + 8:04d}"
    expiry_date_greg = f"{today.year + 8:04d}/{today.month:02d}/{today.day:02d}"
    
    text_data["expiry_date"] = f"{expiry_eth_date} | {expiry_date_greg}"
    text_data["nationality"] = "ኢትዮጵያዊ | Ethiopian"

    # 5️⃣ Draw text fields
    for key, field in TEMPLATE_FIELDS.items():
        if field["type"] != "text" or key not in text_data:
            continue

        text_to_draw = clean_extracted_text(str(text_data[key]))
        font_use = font_am_large if field.get("lang") == "am" else font_en_large
        coords = field.get("coords", ())
        if len(coords) != 2:
            continue
        x, y = coords[0] * scale, coords[1] * scale

        # Handle combined or special fields
        if key == "sex_en":
            am_text = text_data.get("sex_am", "")
            am_width = draw_large.textlength(am_text, font=font_am_large)
            x = (TEMPLATE_FIELDS["sex_am"]["coords"][0] * scale) + am_width + 10
            text_to_draw = "| " + text_to_draw
        elif key == "date_of_birth_greg":
            continue
        elif key == "date_of_birth_et" and "date_of_birth_greg" in text_data:
            greg_formatted = format_gregorian_date_display(text_data["date_of_birth_greg"], "YYYY/MM/DD")
            text_to_draw = f"{text_data['date_of_birth_et']} | {greg_formatted}"
            font_use = font_en_large

        draw_bold_text(draw_large, (x, y), text_to_draw, font_use, boldness=boldness * scale)

    # 6️⃣ Paste cropped images
    for key, field in TEMPLATE_FIELDS.items():
        if field["type"] != "image" or key not in image_crops:  
            continue
        crop_img = image_crops[key]
        if crop_img is None: # Photo could be None if missing in PDF
            continue
            
        try:
            pil_crop = None

            # --- 1. Use already processed photo/small_image OR process other images ---
            if key == "photo" or key == "small_image":
                # Already processed above!
                pil_crop = crop_img
            else:
                # For other image types (QR code, etc.), just convert to PIL
                if isinstance(crop_img, np.ndarray):
                    if crop_img.size == 0: continue
                    pil_crop = Image.fromarray(cv2.cvtColor(crop_img, cv2.COLOR_BGR2RGB))
                else:
                    pil_crop = crop_img.convert("RGBA")

            if pil_crop is None: continue

            # --- 2. RESIZE ---
            coords = field.get("coords", ())
            if len(coords) != 4:
                continue
            x1, y1, x2, y2 = coords
            target_w, target_h = (x2 - x1) * scale, (y2 - y1) * scale
            pil_crop = pil_crop.resize((target_w, target_h), Image.Resampling.LANCZOS)

            # --- 3. PASTE ---
            if pil_crop.mode == "RGBA":
                # Use alpha as mask
                img_large.paste(pil_crop, (x1 * scale, y1 * scale), pil_crop)
            else:
                # No transparency (e.g., barcode)
                img_large.paste(pil_crop, (x1 * scale, y1 * scale))

        except Exception:
            pass

    # 7️⃣ Draw vertical date text (both)
    draw_vertical_text(img_large, (7, 156), date_of_issue_greg, font_english, 14, boldness=boldness, scale=scale)
    draw_vertical_text(img_large, (7, 310), date_of_issue_eth, font_amharic, 14, boldness=boldness, scale=scale)

    # 8️⃣ Resize back to original dimensions for the user
    img_final = img_large.resize((w, h), Image.Resampling.LANCZOS)

    # 9️⃣ Return as high-quality PNG bytes
    buffer = BytesIO()
    img_final.save(buffer, format="PNG", optimize=True, dpi=(300, 300))
    return buffer.getvalue()
