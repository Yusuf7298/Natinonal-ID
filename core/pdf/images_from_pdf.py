import pymupdf as fitz
import io
import numpy as np
import cv2 
from PIL import Image
def extract_images_from_pdf(pdf_path):
    extracted_images = []
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
    num_found = len(extracted_images)
    return {"photo": extracted_images[0] if num_found > 0 else None,"qrcode": extracted_images[1] if num_found > 1 else None}