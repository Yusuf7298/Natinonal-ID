import cv2
import numpy as np
from pathlib import Path
from core.pdf.pdf_to_image_converter import pdf_to_image


def crop_pdf_sections(pdf_path: Path, output_dir: Path, dpi: int = 600):
    """
    Convert PDF to a high-resolution image, crop regions (photo, barcode, QR),
    and return them as NumPy arrays (high quality, no saving).
    """

    # 1️⃣ Convert PDF to image at high DPI
    image_path = pdf_to_image(pdf_path, output_dir, dpi=dpi)

    # 2️⃣ Load image using OpenCV
    img = cv2.imread(str(image_path))
    if img is None:
        raise ValueError(f"Image not found at {image_path}")

    # 3️⃣ Define crop coordinates (x1, y1, x2, y2) at BASE DPI 400
    # These were measured at 400 DPI
    BASE_DPI = 400
    scale = dpi / BASE_DPI

    photo_coords = (2445, 670, 2810, 1130)
    barcode_coords = (2445, 1610, 2800, 1720)
    qrcode_coords = (2290, 2000, 3000, 2700)
    fin_code_coords = (2640, 2730, 3000, 2790)

    # 3️⃣ Crop each section with scaling
    def crop_section(coords):
        x1, y1, x2, y2 = [int(c * scale) for c in coords]
        return img[y1:y2, x1:x2]

    photo = crop_section(photo_coords)
    barcode = crop_section(barcode_coords)
    qrcode = crop_section(qrcode_coords)
    fin_code = crop_section(fin_code_coords)
    
    # 4️⃣ Optional enhancement for clarity
    def enhance(img_section):
        if img_section is None or img_section.size == 0:
            return img_section
        gaussian = cv2.GaussianBlur(img_section, (0, 0), 2)
        return cv2.addWeighted(img_section, 1.5, gaussian, -0.5, 0)

    def clean_white_background(img_section, thresh=180):
        if img_section is None or img_section.size == 0:
            return img_section
        gray = cv2.cvtColor(img_section, cv2.COLOR_BGR2GRAY)
        cleaned = img_section.copy()
        cleaned[gray > thresh] = [255, 255, 255]
        return cleaned

    photo = enhance(photo)
    barcode = clean_white_background(enhance(barcode), thresh=200)
    qrcode = enhance(qrcode)
    fin_code = clean_white_background(enhance(fin_code), thresh=180)

    return {
        "photo": photo,
        "barcode": barcode,
        "qrcode": qrcode,
        "fin_code": fin_code,
        "small_image": photo
    }


