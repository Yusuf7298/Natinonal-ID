import sys
import os
from pathlib import Path
sys.path.append(os.getcwd())
from core.image.image_generator import generate_final_id_image
import tempfile
def test_gen():
    try:
        sample_pdf = Path("data/sample.pdf")
        if not sample_pdf.exists():
            print("No sample PDF found at data/sample.pdf")
            return
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir)
            print("Starting test generation...")
            res = generate_final_id_image(
                pdf_path=sample_pdf,
                output_dir=out_dir,
                font_amharic="./fonts/truetype/abyssinica/AbyssinicaSIL-Regular.ttf",
                font_english="./fonts/truetype/noto/NotoSans-Regular.ttf",
                color=True
            )
            print(f"Success! Generated {len(res)} bytes")
    except Exception as e:
        import traceback
        print(f"FAILED: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    test_gen()
