import pymupdf as fitz
from typing import Dict, Any
def get_pdf_metadata(pdf_bytes: bytes) -> Dict[str, Any]:
    try:
        pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")
        page_count = len(pdf_document)
        pdf_document.close()
        return {"page_count": page_count} 
    except Exception as e:
        return {
            "page_count": 0
        }