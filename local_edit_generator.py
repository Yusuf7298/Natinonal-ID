import json
import os
import sys
import tempfile
from pathlib import Path
from core.pdf.pdf_data_extractor import extract_user_data
from core.image.image_generator import generate_final_id_image
from core.image.image_generator_b import generate_final_id_image_b
def manual_edit_data(data):
    print("\n--- Extracted Data ---")
    keys = list(data.keys())
    for i, key in enumerate(keys):
        print(f"{i + 1}. {key}: {data[key]}")
    while True:
        choice = input("\nEnter the number of the field to edit (or 'done' to finish): ").strip().lower()
        if choice == 'done':
            break
        try:
            index = int(choice) - 1
            if 0 <= index < len(keys):
                key = keys[index]
                new_value = input(f"Enter new value for {key} (current: {data[key]}): ")
                data[key] = new_value
                print(f"Updated {key} to: {data[key]}")
            else:
                print("Invalid index.")
        except ValueError:
            print("Invalid input. Please enter a number or 'done'.")
    return data

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 local_edit_generator.py <pdf_path> [template_type A or B]")
        sys.exit(1)
    pdf_path = Path(sys.argv[1])
    if not pdf_path.exists():
        print(f"Error: File {pdf_path} not found.")
        sys.exit(1)
    template = "A"
    if len(sys.argv) > 2:
        template = sys.argv[2].upper()
    print(f"📂 Extracting data from {pdf_path}...")
    data = extract_user_data(pdf_path)
    if not data:
        print("❌ Failed to extract data.")
        sys.exit(1)
    edited_data = manual_edit_data(data)
    print(f"🎨 Generating ID card (Template {template})...")
    with tempfile.TemporaryDirectory() as temp_dir:
        output_path = Path(temp_dir)
        if template == "B":
            # pyrefly: ignore [unexpected-keyword]
            image_bytes = generate_final_id_image_b(pdf_path, output_path, text_data=edited_data, color=False)
        else:
            # pyrefly: ignore [unexpected-keyword]
            image_bytes = generate_final_id_image(pdf_path, output_path, text_data=edited_data, color=False)
        output_filename = f"edited_id_{template}_{pdf_path.stem}.png"
        with open(output_filename, 'wb') as f:
            f.write(image_bytes)
    print(f"✅ ID card generated: {output_filename}")

if __name__ == "__main__":
    main()
