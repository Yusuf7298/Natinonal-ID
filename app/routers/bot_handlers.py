from datetime import datetime, timedelta
from aiogram import Router, types, F
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext

from app.state import PDFBotStates
from app.config import settings
from utils.texts import WELCOME_TEXT, SINGLE_MODE_SELECTED

router = Router()

# --- TIMEOUT FUNCTION ---
async def auto_process_timeout(user_id: int, bot, dp, processor):
    """Triggered by APScheduler if user doesn't click Done within 10 mins"""
    state_context = dp.fsm.get_context(bot, user_id, user_id)
    state_data = await state_context.get_data()
    current_state = await state_context.get_state()

    if current_state == PDFBotStates.waiting_multiple_pdfs:
        files = state_data.get("pdf_list", [])
        if files:
            await bot.send_message(chat_id=user_id, text="⏳ 10 minutes passed! Processing your PDFs automatically...")
            await processor.process_multiple_pdfs(files, user_id)
        await state_context.clear()

# --- HANDLERS ---

# --- KEYBOARDS ---

# --- KEYBOARDS ---

def get_main_kb():
    kb = [
        [types.KeyboardButton(text="📄 One PDF"), types.KeyboardButton(text="📚 Multiple PDFs")]
    ]
    return types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, persistent=True)

def get_color_kb():
    kb = [
        [types.KeyboardButton(text="🎨 Color"), types.KeyboardButton(text="⚫ Black & White")],
        [types.KeyboardButton(text="🔙 Back to Menu")]
    ]
    return types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, persistent=True)

def get_template_kb():
    kb = [
        [types.KeyboardButton(text="🆔 Template A"), types.KeyboardButton(text="🆔 Template B")],
        [types.KeyboardButton(text="🔙 Back to Menu")]
    ]
    return types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, persistent=True)

def get_collecting_kb(count: int):
    kb = [
        [types.KeyboardButton(text=f"✅ Done (Collected: {count})")],
        [types.KeyboardButton(text="🔙 Back to Menu")]
    ]
    return types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, persistent=True)

# --- HANDLERS ---

@router.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(text=WELCOME_TEXT, reply_markup=get_main_kb(), disable_web_page_preview=True)

# 2. Handle Mode Selection
@router.message(F.text == "📄 One PDF")
async def single_mode(message: types.Message, state: FSMContext):
    await state.set_state(PDFBotStates.choosing_color)
    await state.update_data(mode="single")
    await message.answer("🎨 Please select output type:", reply_markup=get_color_kb())

@router.message(F.text == "📚 Multiple PDFs")
async def multi_mode(message: types.Message, state: FSMContext):
    await state.set_state(PDFBotStates.choosing_color)
    await state.update_data(mode="multiple", pdf_list=[])
    await message.answer("🎨 Please select output type:", reply_markup=get_color_kb())

# 2.5 Handle Color Selection
@router.message(PDFBotStates.choosing_color, F.text.in_(["🎨 Color", "⚫ Black & White"]))
async def choose_color(message: types.Message, state: FSMContext):
    is_color = message.text == "🎨 Color"
    data = await state.get_data()
    mode = data.get("mode")
    
    await state.update_data(is_color=is_color)
    
    await state.set_state(PDFBotStates.choosing_template)
    await message.answer("🆔 Please select the ID Template:", reply_markup=get_template_kb())

@router.message(PDFBotStates.choosing_template, F.text.in_(["🆔 Template A", "🆔 Template B"]))
async def choose_template(message: types.Message, state: FSMContext):
    template = "B" if "Template B" in message.text else "A"
    data = await state.get_data()
    mode = data.get("mode")
    is_color = data.get("is_color")
    color_text = "Color" if is_color else "B&W"
    
    await state.update_data(template=template)
    
    if mode == "single":
        await state.set_state(PDFBotStates.waiting_single_pdf)
        msg = await message.answer(f"✅ Mode: Single ({color_text}, Template {template})\nPlease send your PDF file.", reply_markup=get_main_kb())
        await state.update_data(status_msg_id=msg.message_id)
    else:
        await state.set_state(PDFBotStates.waiting_multiple_pdfs)
        msg = await message.answer(f"✅ Mode: Multiple ({color_text}, Template {template})\nReady to collect. Please send your first PDF.", reply_markup=get_collecting_kb(0))
        await state.update_data(status_msg_id=msg.message_id)

@router.message(F.text == "🔙 Back to Menu")
async def back_to_menu(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("🔙 Returned to main menu.", reply_markup=get_main_kb())

# 3. Handle Single PDF File
@router.message(PDFBotStates.waiting_single_pdf, F.document)
async def process_single_pdf_file(message: types.Message, state: FSMContext, processor):
    if message.document.mime_type != "application/pdf":
        return await message.answer("❌ Error: Please send a PDF file.")

    data = await state.get_data()
    status_msg_id = data.get("status_msg_id")
    is_color = data.get("is_color", True)
    template = data.get("template", "A")
    
    status_text = f"🔄 Processing your single ID card (Template {template})..."
    if status_msg_id:
        try:
            await message.bot.edit_message_text(chat_id=message.chat.id, message_id=status_msg_id, text=status_text)
        except Exception:
            msg = await message.answer(status_text)
            status_msg_id = msg.message_id
    else:
        msg = await message.answer(status_text)
        status_msg_id = msg.message_id
        
    await processor.process_pdf_from_telegram(
        file_id=message.document.file_id, 
        chat_id=message.chat.id, 
        color=is_color,
        template=template,
        status_message_id=status_msg_id
    )
    await message.answer("📋 ID processed. What would you like to do next?", reply_markup=get_main_kb())
    await state.clear()

# 4. Handle File Collection (Multiple)
@router.message(PDFBotStates.waiting_multiple_pdfs, F.document)
async def collect_files(message: types.Message, state: FSMContext, scheduler, bot, dp, processor):
    if message.document.mime_type != "application/pdf":
        return await message.answer("❌ Please only send PDF files.")
    
    data = await state.get_data()
    pdf_list = data.get("pdf_list", [])

    if len(pdf_list) >= settings.MAX_BATCH_SIZE:
        return await message.answer(
            f"⚠️ Batch limit reached! Maximum {settings.MAX_BATCH_SIZE} PDFs per batch.\n"
            f"Please click 'Done' below to process the current batch.",
            reply_markup=get_collecting_kb(len(pdf_list))
        )

    pdf_list.append(message.document.file_id)
    await state.update_data(pdf_list=pdf_list)

    # Timer logic
    user_id = message.from_user.id
    job_id = f"timer_{user_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)

    scheduler.add_job(
        auto_process_timeout,
        'date',
        run_date=datetime.now() + timedelta(minutes=10),
        args=[user_id, bot, dp, processor],
        id=job_id
    )
    
    status_msg_id = data.get("status_msg_id")
    status_text = f"📎 Received file #{len(pdf_list)}. Send another or click 'Done' below."
    
    if status_msg_id:
        try:
            await bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=status_msg_id,
                text=status_text,
                reply_markup=get_collecting_kb(len(pdf_list))
            )
        except Exception:
            msg = await message.answer(status_text, reply_markup=get_collecting_kb(len(pdf_list)))
            await state.update_data(status_msg_id=msg.message_id)
    else:
        msg = await message.answer(status_text, reply_markup=get_collecting_kb(len(pdf_list)))
        await state.update_data(status_msg_id=msg.message_id)

# 5. Handle "Done" button (Both Text and Callback)
@router.message(PDFBotStates.waiting_multiple_pdfs, F.text.startswith("✅ Done"))
@router.callback_query(F.data == "process_all")
async def process_multiple(event: types.Message | types.CallbackQuery, state: FSMContext, processor, scheduler):
    is_callback = isinstance(event, types.CallbackQuery)
    user_id = event.from_user.id
    message = event.message if is_callback else event

    job_id = f"timer_{user_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)

    data = await state.get_data()
    files = data.get("pdf_list", [])
    is_color = data.get("is_color", True)
    template = data.get("template", "A")
    
    if not files:
        if is_callback: await event.answer("No PDFs collected!", show_alert=True)
        else: await message.answer("You haven't sent any PDFs yet!")
        return

    status_msg_id = data.get("status_msg_id")
    status_text = f"🚀 Merging {len(files)} IDs (Template {template})... Please wait."
    
    if status_msg_id:
        try:
            await message.bot.edit_message_text(chat_id=message.chat.id, message_id=status_msg_id, text=status_text)
        except Exception:
            msg = await message.answer(status_text, reply_markup=get_main_kb())
            status_msg_id = msg.message_id
    else:
        msg = await message.answer(status_text, reply_markup=get_main_kb())
        status_msg_id = msg.message_id
    
    await processor.process_multiple_pdfs(files, message.chat.id, color=is_color, template=template, status_message_id=status_msg_id)
    
    if is_callback: await event.answer()
    await state.clear()

# 6. Default Document Handler (when no state is set)
@router.message(F.document, StateFilter(None))
async def process_pdf_default(message: types.Message, state: FSMContext, processor):
    if message.document.mime_type != "application/pdf":
        return await message.answer(text="❌ Error: Please send a PDF file.")

    msg = await message.answer(text="🔄 Processing your single ID card...")
    await processor.process_pdf_from_telegram(file_id=message.document.file_id, chat_id=message.chat.id, status_message_id=msg.message_id)
    await message.answer(text="📋 Processed! What next?", reply_markup=get_main_kb())
    await state.clear()

@router.message()
async def catch_all_debug(message: types.Message):
    await message.answer(text="Please select a mode or send a PDF.", reply_markup=get_main_kb())