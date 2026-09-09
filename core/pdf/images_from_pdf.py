import pymupdf as fitz
import io
import numpy as np
import cv2 
from PIL import Image
def extract_images_from_pdf(pdf_path):
    extracted_images = []
    face_photo = None
    with fitz.open(pdf_path) as doc:
        for page_index in range(len(doc)):
            page = doc[page_index]
            image_list = page.get_images(full=True)
            for img in image_list:
                xref = img[0]
                base_image = doc.extract_image(xref)
                image_bytes = base_image["image"]
                pil_img = Image.open(io.BytesIO(image_bytes))
                numpy_img = np.array(pil_img)
                if len(numpy_img.shape) == 3:
                    if numpy_img.shape[2] == 3: 
                        numpy_img = cv2.cvtColor(numpy_img, cv2.COLOR_RGB2BGR)
                    elif numpy_img.shape[2] == 4: 
                        numpy_img = cv2.cvtColor(numpy_img, cv2.COLOR_RGBA2BGR)
                extracted_images.append(numpy_img)

                if page_index == 0 and face_photo is None:
                    for r in page.get_image_rects(xref):
                        if r.x0 < 80 and 80 < r.y0 < 130 and base_image.get("width", 0) > 80:
                            face_photo = pil_img
                            break

    num_found = len(extracted_images)
    if face_photo is None and num_found > 0:
        face_photo = Image.fromarray(cv2.cvtColor(extracted_images[0], cv2.COLOR_BGR2RGB))
    return {
        "photo": face_photo,
        "qrcode": extracted_images[1] if num_found > 1 else None
    }