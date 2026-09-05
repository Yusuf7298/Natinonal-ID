import asyncio
import io
import traceback
try:
    import magic
except (ImportError, Exception):
    magic = None
import tempfile
import math
import time
import httpx
import urllib.request
from pathlib import Path
from aiogram import Bot, types
from aiogram.types import BufferedInputFile
from PIL import Image, ImageChops, ImageOps
from core.image.image_generator import generate_final_id_image
from core.image.image_generator_b import generate_final_id_image_b
from core.pdf.extractor import get_pdf_metadata
from app.config import settings
def _download_via_http(url: str, expected_size: int = 0, timeout: int = 45, max_retries: int = 5) -> bytes:
    downloaded = bytearray()
    for attempt in range(max_retries):
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            if downloaded:
                headers["Range"] = f"bytes={len(downloaded)}-"
                print(f"Resuming download from byte {len(downloaded)} (attempt {attempt + 1}/{max_retries})...", flush=True)
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                while True:
                    chunk = resp.read(65536) 
                    if not chunk:
                        return bytes(downloaded)
                    downloaded.extend(chunk)
                    if expected_size and len(downloaded) >= expected_size:
                        return bytes(downloaded)
        except Exception as e:
            err_name = type(e).__name__
            print(f"Connection interrupted at {len(downloaded)} bytes ({err_name}). Auto-resuming...", flush=True)
            time.sleep(1)
    if downloaded:
        return bytes(downloaded)
    raise ConnectionError("Failed to download file after multiple resume attempts.")

class ProcessingService:
    def __init__(self, bot: Bot):
        self.bot = bot
        self.lock = asyncio.Lock()

    async def _download_file_with_retry(self, file_id: str, retries: int = 3) -> bytes:
        last_exception = None
        for attempt in range(retries):
            try:
                print(f"Getting file metadata for file_id: {file_id}...", flush=True)
                file = await self.bot.get_file(file_id=file_id)
                if not file.file_path:
                    raise ValueError("Telegram API did not return a valid file_path")
                file_size = getattr(file, "file_size", 0) or 0
                print(f"Telegram file path: {file.file_path} ({file_size / 1024:.1f} KB)", flush=True)
                file_url = f"https://api.telegram.org/file/bot{self.bot.token}/{file.file_path}"
                try:
                    print(f"Downloading file ({file_size / 1024:.1f} KB)...", flush=True)
                    data = await asyncio.to_thread(_download_via_http, file_url, file_size)
                    print(f"Download completed successfully ({len(data)} bytes)!", flush=True)
                    return data
                except Exception as http_err:
                    print(f"Direct HTTP download error ({type(http_err).__name__}: {http_err}), trying bot.download_file fallback...", flush=True)
                    pdf_bytes_io = await self.bot.download_file(file_path=file.file_path, timeout=300)
                    if pdf_bytes_io:
                        res = pdf_bytes_io.read()
                        print(f"bot.download_file fallback succeeded ({len(res)} bytes).", flush=True)
                        return res
            except Exception as e:
                err_type = type(e).__name__
                err_msg = str(e) or repr(e)
                last_exception = e
                if attempt < retries - 1:
                    wait_time = (attempt + 1) * 2
                    print(f"Download attempt {attempt + 1}/{retries} failed: [{err_type}] {err_msg}. Retrying in {wait_time}s...", flush=True)
                    await asyncio.sleep(wait_time)
                else:
                    print(f"Download failed after {retries} attempts: [{err_type}] {err_msg}", flush=True)
        # pyrefly: ignore [bad-raise]
        raise last_exception
    async def process_pdf_from_telegram(self, file_id: str, chat_id: int, color: bool = True, template: str = "A", status_message_id: int = None) -> bool:
        status_msg_id = status_message_id
        try:
            if status_msg_id:
                try:
                    await self.bot.edit_message_text(chat_id=chat_id, message_id=status_msg_id, text="📥 Downloading your PDF...")
                except Exception:
                    msg = await self.bot.send_message(chat_id=chat_id, text="📥 Downloading your PDF...")
                    status_msg_id = msg.message_id
            else:
                msg = await self.bot.send_message(chat_id=chat_id, text="📥 Downloading your PDF...")
                status_msg_id = msg.message_id
            pdf_bytes = await self._download_file_with_retry(file_id)
            await self.bot.edit_message_text(
                text="🧩 Checking file type...", 
                chat_id=chat_id, 
                message_id=status_msg_id
            )
            is_pdf = False
            detected_type = "unknown"
            if magic:
                try:
                    detected_type = magic.from_buffer(pdf_bytes, mime=True)
                    is_pdf = (detected_type == "application/pdf")
                except Exception:
                    is_pdf = pdf_bytes.startswith(b"%PDF")
            else:
                is_pdf = pdf_bytes.startswith(b"%PDF")
                detected_type = "application/pdf" if is_pdf else "non-pdf"

            if not is_pdf:
                await self.bot.edit_message_text(
                    text=f"Error: Not a PDF. Detected: `{detected_type}`", 
                    chat_id=chat_id, 
                    message_id=status_msg_id
                )
                return False
            metadata = get_pdf_metadata(pdf_bytes)
            page_count = metadata.get("page_count", 1)
            if page_count != 1:
                await self.bot.edit_message_text(
                    text=f"Invalid PDF: Found {page_count} pages. Please send 1 page.",
                    chat_id=chat_id, 
                    message_id=status_msg_id
                )
                return False
            await self.bot.edit_message_text(
                text="🔄 Generating your ID card...", 
                chat_id=chat_id, 
                message_id=status_msg_id
            )
            async with self.lock:
                with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
                    temp_path = Path(temp_dir)
                    pdf_file = temp_path / "input.pdf"
                    pdf_file.write_bytes(pdf_bytes)
                    output_dir = temp_path / "output"
                    output_dir.mkdir(exist_ok=True)
                    generator_func = generate_final_id_image_b if template == "B" else generate_final_id_image
                    print(f"[*] Starting ID card generation (Template {template}, Color={color})...", flush=True)
                    image_bytes = await asyncio.to_thread(
                        generator_func,
                        pdf_path=pdf_file,
                        output_dir=output_dir,
                        font_amharic="./fonts/truetype/abyssinica/AbyssinicaSIL-Regular.ttf",
                        font_english="./fonts/truetype/noto/NotoSans-Regular.ttf",
                        font_size=17,
                        boldness=0.5,
                        dpi=600,
                        color=color
                    )
                    print(f"[OK] ID card generated successfully ({len(image_bytes)} bytes)!", flush=True)
            photo_sent = False
            for send_attempt in range(1, 4):
                try:
                    photo = BufferedInputFile(image_bytes, filename="id_card.png")
                    await self.bot.send_photo(
                        chat_id=chat_id, 
                        photo=photo, 
                        request_timeout=120
                    )
                    photo_sent = True
                    break
                except Exception as send_err:
                    print(f"⚠️ Failed to send ID photo (attempt {send_attempt}/3): {send_err}", flush=True)
                    if send_attempt < 3:
                        await asyncio.sleep(2 * send_attempt)
                    else:
                        raise send_err
            try:
                await self.bot.delete_message(chat_id=chat_id, message_id=status_msg_id)
            except Exception:
                pass
            return True
        except Exception as e:
            error_traceback = traceback.format_exc()
            print(f"Processing Error: {e}\n{error_traceback}", flush=True)
            if status_msg_id:
                try:
                    if settings.DEBUG or chat_id in settings.authorized_users:
                        msg_text = f"Error: {repr(e)}\n\n(Debug: {error_traceback[:200]}...)"
                    else:
                        msg_text = "An error occurred while processing your ID card. Please ensure your PDF is an official, valid Ethiopian Fayda printable ID (1 page) and try again."
                    await self.bot.edit_message_text(
                        text=msg_text, 
                        chat_id=chat_id, 
                        message_id=status_msg_id
                    )
                except Exception:
                    pass
            return False

    async def process_multiple_pdfs(self, file_ids: list[str], chat_id: int, color: bool = True, template: str = "A", status_message_id: int = None) -> bool:
        status_msg_id = status_message_id
        if status_msg_id:
            try:
                await self.bot.edit_message_text(chat_id=chat_id, message_id=status_msg_id, text=f"🚀 Starting batch processing of {len(file_ids)} PDFs...")
            except Exception:
                msg = await self.bot.send_message(chat_id=chat_id, text=f"🚀 Starting batch processing of {len(file_ids)} PDFs...")
                status_msg_id = msg.message_id
        else:
            msg = await self.bot.send_message(chat_id=chat_id, text=f"🚀 Starting batch processing of {len(file_ids)} PDFs...")
            status_msg_id = msg.message_id
        A4_WIDTH = 905
        A4_HEIGHT = 1280
        ID_TARGET_W = 388
        ID_TARGET_H = 244
        GAP = 28
        TARGET_HEIGHT = ID_TARGET_H
        TARGET_ROW_WIDTH = (ID_TARGET_W * 2) + GAP
        all_rows_processed = []
        try:
            semaphore = asyncio.Semaphore(5)
            completed_downloads = 0
            download_lock = asyncio.Lock()
            async def download_task(fid, idx):
                async with semaphore:
                    data = await self._download_file_with_retry(fid)
                    nonlocal completed_downloads
                    async with download_lock:
                        completed_downloads += 1
                        try:
                            await self.bot.edit_message_text(
                                text=f"📥 Downloaded {completed_downloads} of {len(file_ids)} IDs...",
                                chat_id=chat_id,
                                message_id=status_msg_id
                            )
                        except Exception:
                            pass
                    return data
            all_pdf_bytes = await asyncio.gather(*(download_task(fid, i) for i, fid in enumerate(file_ids)))
            for i, pdf_bytes in enumerate(all_pdf_bytes):
                await self.bot.edit_message_text(
                    text=f"🔄 Processing ID #{i+1} of {len(file_ids)}...",
                    chat_id=chat_id,
                    message_id=status_msg_id
                )
                async with self.lock: 
                    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
                        temp_path = Path(temp_dir)
                        pdf_file = temp_path / f"input_{i}.pdf"
                        pdf_file.write_bytes(pdf_bytes)
                        output_dir = temp_path / "output"
                        output_dir.mkdir(exist_ok=True)
                        generator_func = generate_final_id_image_b if template == "B" else generate_final_id_image
                        image_bytes = await asyncio.to_thread(
                            generator_func,
                            pdf_path=pdf_file,
                            output_dir=output_dir,
                            font_amharic="./fonts/truetype/abyssinica/AbyssinicaSIL-Regular.ttf",
                            font_english="./fonts/truetype/noto/NotoSans-Regular.ttf",
                            font_size=17,
                            boldness=0.5,
                            dpi=600,
                            color=color
                        )
                full_id_img = Image.open(io.BytesIO(image_bytes))
                id_w, id_h = full_id_img.size
                front_raw = full_id_img.crop((0, 0, id_w // 2, id_h))
                back_raw = full_id_img.crop((id_w // 2, 0, id_w, id_h))
                def trim_all(im, threshold=10):
                    gray = im.convert("L")
                    inv = ImageOps.invert(gray)
                    bbox = inv.point(lambda p: p > threshold and 255).getbbox()
                    if not bbox: return im
                    return im.crop(bbox)
                front = trim_all(front_raw).resize((ID_TARGET_W, ID_TARGET_H), Image.Resampling.LANCZOS)
                back = trim_all(back_raw).resize((ID_TARGET_W, ID_TARGET_H), Image.Resampling.LANCZOS)
                new_row = Image.new('RGB', (TARGET_ROW_WIDTH, TARGET_HEIGHT), (255, 255, 255))
                new_row.paste(front, (0, 0))
                new_row.paste(back, (ID_TARGET_W + GAP, 0))
                all_rows_processed.append(new_row)
            num_pages = math.ceil(len(file_ids) / 5)
            for p in range(num_pages):
                await self.bot.edit_message_text(
                    text=f"📄 Generating A4 page {p+1} of {num_pages}...",
                    chat_id=chat_id,
                    message_id=status_msg_id
                )  
                start_idx = p * 5
                end_idx = min(start_idx + 5, len(file_ids))
                current_batch_size = end_idx - start_idx
                a4_canvas = Image.new('RGB', (A4_WIDTH, A4_HEIGHT), (255, 255, 255))
                v_gap = 10
                total_block_h = (current_batch_size * TARGET_HEIGHT) + ((current_batch_size - 1) * v_gap if current_batch_size > 1 else 0)
                start_y = (A4_HEIGHT - total_block_h) // 2
                x_pos = (A4_WIDTH - TARGET_ROW_WIDTH) // 2
                for j in range(current_batch_size):
                    y_pos = start_y + j * (TARGET_HEIGHT + v_gap)
                    a4_canvas.paste(all_rows_processed[start_idx + j], (x_pos, y_pos))
                a4_canvas = a4_canvas.transpose(Image.FLIP_LEFT_RIGHT)
                out_io = io.BytesIO()
                a4_canvas.save(out_io, format='PNG')
                out_bytes = out_io.getvalue()
                doc_sent = False
                for send_attempt in range(1, 4):
                    try:
                        print(f"Sending A4 Page {p+1} ({len(out_bytes) / 1024:.1f} KB, attempt {send_attempt}/3)...", flush=True)
                        await self.bot.send_document(
                            chat_id=chat_id,
                            document=BufferedInputFile(out_bytes, filename=f"A4_IDs_PAGE_{p+1}.png"),
                            caption=f"✅ A4 Page {p+1} ({current_batch_size} IDs)\nLayout: [Back | Front] (MIRRORED)\nType: {'Color' if color else 'B&W'}",
                            request_timeout=300
                        )
                        doc_sent = True
                        print(f"[OK] A4 Page {p+1} sent successfully!", flush=True)
                        break
                    except Exception as send_err:
                        print(f"⚠️ Failed to send A4 Page {p+1} (attempt {send_attempt}/3): {send_err}", flush=True)
                        if send_attempt < 3:
                            await asyncio.sleep(2 * send_attempt)
                        else:
                            raise send_err

            try:
                await self.bot.delete_message(chat_id=chat_id, message_id=status_msg_id)
            except Exception:
                pass
            await self.bot.send_message(chat_id=chat_id, text=f"✅ All {len(file_ids)} IDs processed and sent!")
            return True
        except Exception as e:
            error_traceback = traceback.format_exc()
            print(f"Batch Processing Error: {e}\n{error_traceback}", flush=True)
            if settings.DEBUG or chat_id in settings.authorized_users:
                msg_text = f"❌ Batch Error: {repr(e)}\n\n(Debug: {error_traceback[:200]}...)"
            else:
                msg_text = "❌ An error occurred while generating the batch ID cards. Please ensure all uploaded PDFs are valid 1-page Ethiopian Fayda IDs and try again."
            if status_msg_id:
                try:
                    await self.bot.edit_message_text(
                        text=msg_text, 
                        chat_id=chat_id, 
                        message_id=status_msg_id
                    )
                except Exception:
                    pass
            else:
                try:
                    await self.bot.send_message(chat_id=chat_id, text=msg_text)
                except Exception:
                    pass
            return False