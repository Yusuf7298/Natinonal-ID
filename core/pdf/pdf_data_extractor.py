import camelot
from pathlib import Path
import pdfplumber
import unicodedata
from typing import Any
def clean_extracted_text(text: Any) -> str:
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    ligature_map = {
        "\u0133": "ij",
        "\u0132": "IJ", 
        "\ufb00": "ff", 
        "\ufb01": "fi", 
        "\ufb02": "fl",  
        "\ufb03": "ffi", 
        "\ufb04": "ffl", 
        "\ufb05": "ft",  
        "\ufb06": "st",  
        "\u0167": "IJ", 
        "\u0168": "ffi", 
        "\u0169": "ffl",  
        "\u016a": "gj",
        "\u016b": "ij",
        "\u023f": "--",
    }
    for lig, rep in ligature_map.items():
        text = text.replace(lig, rep)
    text = unicodedata.normalize("NFKC", text)
    return " ".join(text.split()).strip()
def extract_user_data(pdf_path: str | Path, debug: bool = False) -> dict:
    pdf_path = str(pdf_path)    
    try:
        tables = camelot.read_pdf(pdf_path, pages="all", flavor="stream", suppress_stdout=False)
        if len(tables) == 0:
            raise ValueError("No tables found in the PDF.")
        table = tables[0].df
        data_extracted = {
            "name_en": clean_extracted_text(table[1][1]),
            "date_of_birth_greg": clean_extracted_text(table[0][5]),
            "date_of_birth_et": clean_extracted_text(table[0][4]),
            "sex_am": clean_extracted_text(table[0][7]),
            "sex_en": clean_extracted_text(table[0][8]),
            "phone_number": clean_extracted_text(table[0][13]),
            "region_am": clean_extracted_text(table[1][4]),
            "region_en": clean_extracted_text(table[1][5]),
            "zone_am": clean_extracted_text(table[1][7]),
            "zone_en": clean_extracted_text(table[1][8]),
            "woreda_am": clean_extracted_text(table[1][10]),
            "woreda_en": clean_extracted_text(table[1][11]),
        }
        x0, y0, x1, y1 = 170.7, 218.43, 300.0, 227.43
        with pdfplumber.open(pdf_path) as pdf:
            page = pdf.pages[0]
            region = page.crop((x0, y0, x1, y1))
            text = region.extract_text()
            data_extracted["name_am"] = clean_extracted_text(text)
        if debug:
            try:
                print("Extracted Data:")
                for k, v in data_extracted.items():
                    print(f"  {k}: {v}")
            except UnicodeEncodeError:
                print("Extracted Data:")
                for k, v in data_extracted.items():
                    print(f"  {k}: {str(v).encode('ascii', 'backslashreplace').decode('ascii')}")
        return data_extracted
    except Exception as e:
        try:
            print(f"Failed to extract data: {e}")
        except UnicodeEncodeError:
            print(f"Failed to extract data: {e}")
        return {}