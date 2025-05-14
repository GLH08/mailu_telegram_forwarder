import telegram
from telegram import InputFile
from io import BytesIO
import logging
import asyncio
import time
import imgkit # For HTML to Image conversion
import os # For imgkit options if needed
from PIL import Image # For image manipulation (splitting)
from . import config
from .email_parser import split_message

logger = logging.getLogger(__name__)

bot = telegram.Bot(token=config.TELEGRAM_BOT_TOKEN)

PARSEMODE_MARKDOWN = "Markdown"

# Define supported image MIME types for direct photo sending (from attachments)
SUPPORTED_IMAGE_MIME_TYPES = [
    "image/jpeg", "image/png", "image/gif", "image/bmp", "image/webp"
]

# Options for imgkit - can be customized
IMGKIT_OPTIONS = {
    'format': 'jpg', # Output format
    'encoding': "UTF-8",
    'width': 800, # Fixed width for better consistency in Telegram
    'quiet': '', # Suppress wkhtmltoimage output
    'enable-local-file-access': None, # Allow access to local files if HTML references them (use with caution)
    # 'disable-smart-width': None, # May help with some layouts
    # 'images': None, # Ensure images are loaded
    # 'javascript-delay': 2000, # Wait for JS to execute (ms)
}
# Consider adding a default CSS for better rendering if needed
# DEFAULT_CSS_PATH = os.path.join(os.path.dirname(__file__), 'default_render.css')
# if os.path.exists(DEFAULT_CSS_PATH):
#     IMGKIT_OPTIONS['user-style-sheet'] = DEFAULT_CSS_PATH


def escape_markdown_legacy_chars(text):
    """Escapes special characters for Telegram's legacy Markdown mode."""
    if not isinstance(text, str): return ""
    # For legacy Markdown, only `_`, `*`, `` ` ``, `[` need escaping.
    escape_chars = r'_*`['
    # Escape `\` first if it's used in the escape sequence, but it's not here.
    for char in escape_chars:
        text = text.replace(char, f'\\{char}')
    return text

async def send_telegram_message_async(chat_id, text, parse_mode=PARSEMODE_MARKDOWN, disable_web_page_preview=True):
    if not text: logger.warning(f"[{time.strftime('%H:%M:%S')}] Attempted to send an empty or None message."); return
    loop = asyncio.get_event_loop()
    message_parts = split_message(text)
    total_parts = len(message_parts)
    for part_idx, part in enumerate(message_parts):
        if not part.strip() and total_parts > 1 : 
            logger.debug(f"[{time.strftime('%H:%M:%S')}] Skipping empty part {part_idx + 1}/{total_parts}."); continue
        current_part_to_send = part
        if not part.strip() and total_parts == 1 and text.strip() == "":
             logger.debug(f"[{time.strftime('%H:%M:%S')}] Original text was empty, sending placeholder for part {part_idx + 1}.")
             current_part_to_send = escape_markdown_legacy_chars("_[空内容]_") if parse_mode else "_[空内容]_"
        try:
            message_object = await loop.run_in_executor(None, lambda: bot.send_message(chat_id=chat_id, text=current_part_to_send, parse_mode=parse_mode, disable_web_page_preview=disable_web_page_preview))
            logger.debug(f"[{time.strftime('%H:%M:%S')}] Sent message part {part_idx + 1}/{total_parts} to {chat_id}. Msg ID: {message_object.message_id if message_object else 'N/A'}")
        except telegram.error.TelegramError as e:
            if "can't parse entities" in str(e).lower() or "parse error" in str(e).lower() and parse_mode:
                logger.warning(f"[{time.strftime('%H:%M:%S')}] {parse_mode} parsing error for part {part_idx + 1}: {e}. Retrying as plain text.")
                try:
                    original_content_of_part = current_part_to_send.removesuffix(f"\n_(第 {part_idx+1}/{total_parts} 部分)_") if total_parts > 1 else current_part_to_send
                    message_object = await loop.run_in_executor(None, lambda: bot.send_message(chat_id=chat_id, text=original_content_of_part, parse_mode=None, disable_web_page_preview=disable_web_page_preview))
                    logger.debug(f"[{time.strftime('%H:%M:%S')}] Sent message part {part_idx + 1} as plain text. Msg ID: {message_object.message_id if message_object else 'N/A'}")
                except Exception as plain_e: logger.error(f"[{time.strftime('%H:%M:%S')}] Failed to send part {part_idx + 1} as plain text: {plain_e}")
            else: logger.error(f"[{time.strftime('%H:%M:%S')}] Telegram API Error sending text (part {part_idx + 1}): {e} - Text Preview: {current_part_to_send[:100]}...")
        except Exception as e: logger.error(f"[{time.strftime('%H:%M:%S')}] Unexpected error in send_telegram_message_async (part {part_idx + 1}): {e}", exc_info=True)

async def send_telegram_document_async(chat_id, document_data, filename, caption=None):
    loop = asyncio.get_event_loop()
    try:
        file_to_send = BytesIO(document_data)
        input_file = InputFile(file_to_send, filename=filename)
        # Captions for documents will be plain text in this simplified version
        plain_caption = caption 
        message_object = await loop.run_in_executor(None, lambda: bot.send_document(chat_id=chat_id, document=input_file, caption=plain_caption, parse_mode=None))
        logger.debug(f"[{time.strftime('%H:%M:%S')}] Sent document '{filename}' to {chat_id}. Msg ID: {message_object.message_id if message_object else 'N/A'}")
    except telegram.error.TelegramError as e:
        logger.error(f"[{time.strftime('%H:%M:%S')}] Telegram API Error sending document '{filename}': {e}")
        if "file is too big" in str(e).lower():
            error_msg = f"📎 附件 '{escape_markdown_legacy_chars(filename)}' 文件过大 ({len(document_data)/(1024*1024):.2f} MB)，无法发送。"
            await send_telegram_message_async(chat_id, error_msg, parse_mode=PARSEMODE_MARKDOWN) # Use legacy markdown for error
    except Exception as e: logger.error(f"[{time.strftime('%H:%M:%S')}] Unexpected error sending document '{filename}': {e}", exc_info=True)

async def send_telegram_photo_async(chat_id, photo_data, filename, caption=None):
    """Sends photo data as a photo message."""
    loop = asyncio.get_event_loop()
    try:
        photo_to_send = BytesIO(photo_data)
        input_photo = InputFile(photo_to_send, filename=filename) # filename is optional for photo but good for context
        # Caption for photos can use Markdown
        message_object = await loop.run_in_executor(None, lambda: bot.send_photo(
            chat_id=chat_id,
            photo=input_photo,
            caption=caption,
            parse_mode=PARSEMODE_MARKDOWN if caption else None
        ))
        logger.debug(f"[{time.strftime('%H:%M:%S')}] Sent photo '{filename}' to {chat_id}. Msg ID: {message_object.message_id if message_object else 'N/A'}")
        return True
    except telegram.error.TelegramError as e:
        logger.error(f"[{time.strftime('%H:%M:%S')}] Telegram API Error sending photo '{filename}': {e}")
        # Re-raise specific errors if they need to be handled by the caller (e.g., for splitting)
        if "photo_invalid_dimensions" in str(e).lower() or \
           "wrong file identifier" in str(e).lower() or \
           "PHOTO_SAVE_FILE_INVALID" in str(e).upper() or \
           "WEBPAGE_CURL_FAILED" in str(e).upper() or \
           "IMAGE_PROCESS_FAILED" in str(e).upper(): # Common error for oversized images
            raise e # Re-raise to be caught by send_html_as_image_async for splitting
    except Exception as e:
        logger.error(f"[{time.strftime('%H:%M:%S')}] Unexpected error sending photo '{filename}': {e}", exc_info=True)
    return False # Return False for other unhandled errors or if not re-raised

async def send_html_as_image_async(chat_id, html_content, caption):
    """Renders HTML content to an image and sends it as a photo, splitting if necessary."""
    loop = asyncio.get_event_loop()
    MAX_IMAGE_HEIGHT_TG = 2560 # Telegram's typical max height for a photo might be around this, width is less restrictive.
                               # However, total pixels (W*H) also matter. Let's try a reasonable height.
    IMG_QUALITY = 85 # JPEG quality for split images

    try:
        logger.debug(f"[{time.strftime('%H:%M:%S')}] Attempting to render HTML to image...")
        full_html = f"""
        <html><head><meta charset="UTF-8">
        <style>
            body {{ font-family: sans-serif; margin: 0; background-color: #ffffff; width: {IMGKIT_OPTIONS.get('width', 800)}px; }}
            img {{ max-width: 100%; height: auto; display: block; }}
            table {{ border-collapse: collapse; width: 100%; margin-bottom: 1em; table-layout: fixed; }}
            th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; word-wrap: break-word; }}
            th {{ background-color: #f2f2f2; }}
            pre, code {{ white-space: pre-wrap; word-wrap: break-word; background-color: #f5f5f5; padding: 0.2em 0.4em; border-radius: 3px; display: block; }}
            /* Add more robust styling as needed */
        </style></head><body>{html_content}</body></html>
        """
        image_bytes = await loop.run_in_executor(None, lambda: imgkit.from_string(full_html, False, options=IMGKIT_OPTIONS))
        
        if not image_bytes:
            logger.error(f"[{time.strftime('%H:%M:%S')}] imgkit.from_string returned empty bytes. Cannot send image.")
            return False

        logger.info(f"[{time.strftime('%H:%M:%S')}] HTML successfully rendered to image ({len(image_bytes)} bytes). Attempting to send to Telegram...")
        
        try:
            # First, try sending the whole image
            if await send_telegram_photo_async(chat_id, image_bytes, "email_body.jpg", caption=caption):
                return True # Successfully sent as a single image
        except telegram.error.TelegramError as e:
            if not ("photo_invalid_dimensions" in str(e).lower() or \
                    "wrong file identifier" in str(e).lower() or \
                    "PHOTO_SAVE_FILE_INVALID" in str(e).upper() or \
                    "WEBPAGE_CURL_FAILED" in str(e).upper() or \
                    "IMAGE_PROCESS_FAILED" in str(e).upper()): # If error is not dimension related, re-raise or log and fail
                logger.error(f"[{time.strftime('%H:%M:%S')}] Error sending full image (not dimension related): {e}")
                return False # Fallback to text

            logger.warning(f"[{time.strftime('%H:%M:%S')}] Full image sending failed due to dimensions/processing: {e}. Attempting to split.")
            
            # Splitting logic
            try:
                img = Image.open(BytesIO(image_bytes))
                original_width, original_height = img.width, img.height
                num_splits = (original_height + MAX_IMAGE_HEIGHT_TG - 1) // MAX_IMAGE_HEIGHT_TG # Ceiling division

                if num_splits <= 1: # Should have been caught by first send attempt, but as a safeguard
                    logger.warning(f"[{time.strftime('%H:%M:%S')}] Image already small enough but failed first send. Not splitting further.")
                    return False

                logger.info(f"[{time.strftime('%H:%M:%S')}] Splitting image into {num_splits} parts (Original H: {original_height}, Max H per part: {MAX_IMAGE_HEIGHT_TG}).")
                
                all_parts_sent = True
                for i in range(num_splits):
                    top = i * MAX_IMAGE_HEIGHT_TG
                    bottom = min((i + 1) * MAX_IMAGE_HEIGHT_TG, original_height)
                    cropped_img = img.crop((0, top, original_width, bottom))
                    
                    img_byte_arr = BytesIO()
                    # Correct the format string for Pillow
                    pillow_format = IMGKIT_OPTIONS.get('format', 'jpeg').upper()
                    if pillow_format == 'JPG': # Common mistake, ensure it's JPEG for Pillow
                        pillow_format = 'JPEG'
                    cropped_img.save(img_byte_arr, format=pillow_format, quality=IMG_QUALITY)
                    cropped_image_bytes = img_byte_arr.getvalue()
                    
                    part_filename = f"email_body_part_{i+1}.{IMGKIT_OPTIONS.get('format', 'jpg')}"
                    part_caption = caption if i == 0 else None # Only first part gets the full caption
                    if i > 0: # Add a simple part indicator for subsequent parts if desired
                        part_caption = f"_(邮件图片 {i+1}/{num_splits})_"


                    if not await send_telegram_photo_async(chat_id, cropped_image_bytes, part_filename, caption=part_caption):
                        logger.error(f"[{time.strftime('%H:%M:%S')}] Failed to send split image part {i+1}.")
                        all_parts_sent = False
                        break # Stop if one part fails
                    await asyncio.sleep(0.5) # Small delay between sending parts
                
                return all_parts_sent

            except Exception as split_e:
                logger.error(f"[{time.strftime('%H:%M:%S')}] Error during image splitting: {split_e}", exc_info=True)
                return False # Fallback to text if splitting fails

        # If the first send_telegram_photo_async didn't raise a dimension error but failed for other reasons
        return False


    except FileNotFoundError as e:
        logger.critical(f"[{time.strftime('%H:%M:%S')}] wkhtmltoimage not found: {e}", exc_info=True)
        await send_telegram_message_async(chat_id, "错误：`wkhtmltoimage` 未安装或未配置，无法将邮件渲染为图片。", parse_mode=None)
        return False
    except OSError as e:
        logger.error(f"[{time.strftime('%H:%M:%S')}] OS error during HTML to image conversion (wkhtmltoimage issue?): {e}", exc_info=True)
        return False
    except Exception as e:
        logger.error(f"[{time.strftime('%H:%M:%S')}] Failed to convert HTML to image: {e}", exc_info=True)
        return False

async def forward_email_to_telegram(parsed_email):
    chat_id = config.TELEGRAM_CHAT_ID
    email_uid = parsed_email.get('uid', 'N/A')
    if not chat_id:
        logger.error(f"TELEGRAM_CHAT_ID is not set. Cannot forward email UID {email_uid}.")
        return
    logger.info(f"[{time.strftime('%H:%M:%S')}] 开始转发邮件 UID {email_uid} ('{parsed_email['subject']}') 到 Telegram 聊天 {chat_id}")

    header_parts = []
    field_map = {
        "subject": ("🏷️ *主题:*", "subject", True), "from": ("👤 *发件人:*", "from", False),
        "to": ("➡️ *收件人:*", "to", False), "cc": ("👥 *抄送:*", "cc", False),
        "date": ("📅 *日期:*", "date", True), "importance": ("⚠️ *重要性:*", "importance", False),
        "message_id": ("🆔 *Message-ID:*", "message_id", True)
    }

    for field_key in config.TELEGRAM_HEADER_FIELDS:
        if field_key in field_map:
            label, email_key, use_code_block = field_map[field_key]
            value = parsed_email.get(email_key)
            if value and value != "N/A":
                value_escaped = escape_markdown_legacy_chars(str(value))
                current_label = label
                if field_key == "importance":
                    if value == "high": current_label = f"❗*紧急邮件* ({value_escaped})"
                    elif value == "low": current_label = f"📉 *低优先级* ({value_escaped})"
                    elif value == "normal": continue
                    else: current_label = f"{label} {value_escaped}" # Should not happen
                
                if field_key == "importance" and value == "high": # Special case for high importance to always show
                     header_parts.append(current_label)
                elif field_key != "importance" or (field_key == "importance" and value != "normal"): # Add if not normal importance
                    header_parts.append(f"{current_label} `{value_escaped}`" if use_code_block else f"{current_label} {value_escaped}")
    
    header_text_for_image_caption = "📧 *新邮件通知*\n" + "\n".join(header_parts) if header_parts else f"📧 *新邮件通知*\n🏷️ *主题:* `{escape_markdown_legacy_chars(parsed_email.get('subject', '[无主题]'))}`"
    header_text_for_message = "📧 *新邮件通知*\n\n" + "\n".join(header_parts) if header_parts else f"📧 *新邮件通知*\n\n🏷️ *主题:* `{escape_markdown_legacy_chars(parsed_email.get('subject', '[无主题]'))}`"


    # Attempt to send HTML body as image first
    body_html_raw = parsed_email.get('body_html')
    body_sent_as_image = False

    if body_html_raw and config.FORWARD_BODY: # Check if HTML body exists and we should forward body
        logger.info(f"[{time.strftime('%H:%M:%S')}] 邮件 UID {email_uid} 包含 HTML 正文，尝试渲染为图片...")
        # Use the shorter header_text for image caption to avoid exceeding caption limits
        body_sent_as_image = await send_html_as_image_async(chat_id, body_html_raw, caption=header_text_for_image_caption)
        if body_sent_as_image:
            logger.info(f"[{time.strftime('%H:%M:%S')}] 邮件 UID {email_uid} 的 HTML 正文已作为图片发送。")
        else:
            logger.warning(f"[{time.strftime('%H:%M:%S')}] 邮件 UID {email_uid} 的 HTML 正文渲染为图片失败。将回退到文本格式。")
            # If image sending failed, we need to send the header separately if it wasn't part of a successful image caption
            await send_telegram_message_async(chat_id, header_text_for_message, parse_mode=PARSEMODE_MARKDOWN)
    else:
        # No HTML body or body forwarding is disabled, send header as a separate message
         await send_telegram_message_async(chat_id, header_text_for_message, parse_mode=PARSEMODE_MARKDOWN)


    # If body was not sent as image (or HTML was not available/image failed), send text body
    if not body_sent_as_image and config.FORWARD_BODY:
        email_body_text = parsed_email.get('body', "_[邮件正文处理失败]_") # Fallback for text body
        email_body_text_escaped = escape_markdown_legacy_chars(email_body_text)
        
        if email_body_text != "_[邮件正文为空]_" and email_body_text != "_[邮件正文处理失败]_":
            separator = escape_markdown_legacy_chars("\n\n‐‐‐‐‐‐‐‐‐‐ 正文 ‐‐‐‐‐‐‐‐‐‐\n\n")
            final_body_to_send = separator + email_body_text_escaped
        else:
            final_body_to_send = email_body_text_escaped # Send placeholder like "[邮件正文为空]"
        
        if final_body_to_send:
            logger.debug(f"[{time.strftime('%H:%M:%S')}] 发送邮件文本正文 UID {email_uid}...")
            await send_telegram_message_async(chat_id, final_body_to_send, parse_mode=PARSEMODE_MARKDOWN)
    elif not config.FORWARD_BODY:
        logger.info(f"[{time.strftime('%H:%M:%S')}] 根据配置，跳过发送邮件 UID {email_uid} 的正文。")


    if config.FORWARD_ATTACHMENTS and parsed_email['attachments']:
        logger.debug(f"[{time.strftime('%H:%M:%S')}] 发送 {len(parsed_email['attachments'])} 个附件，邮件 UID {email_uid}...")
        attachment_count = len(parsed_email['attachments'])
        attachment_header = f"📎 *附件 ({escape_markdown_legacy_chars(str(attachment_count))}):*"
        await send_telegram_message_async(chat_id, attachment_header, parse_mode=PARSEMODE_MARKDOWN)
        
        for idx, attachment in enumerate(parsed_email['attachments']):
            attachment_data = attachment['data']; attachment_filename = attachment['filename']
            attachment_content_type = attachment['content_type'].lower()
            file_size_bytes = len(attachment_data)
            file_size_kb = file_size_bytes / 1024; file_size_mb = file_size_kb / 1024
            size_str = f"{file_size_kb:.2f} KB" if file_size_kb < 1024 else f"{file_size_mb:.2f} MB"
            
            logger.debug(f"[{time.strftime('%H:%M:%S')}] 处理附件 {idx+1}/{attachment_count}: {attachment_filename} ({size_str}, {attachment_content_type}) UID {email_uid}")
            
            caption = (f"文件: {escape_markdown_legacy_chars(attachment_filename)}\n"
                       f"类型: {escape_markdown_legacy_chars(attachment_content_type)}\n"
                       f"大小: {size_str}")

            photo_sent_successfully = False
            if config.TELEGRAM_IMAGE_PREVIEW and \
               attachment_content_type in SUPPORTED_IMAGE_MIME_TYPES and \
               file_size_bytes < config.TELEGRAM_IMAGE_PREVIEW_MAX_SIZE_BYTES and \
               file_size_bytes > 0: # Ensure data is not empty
                
                logger.info(f"[{time.strftime('%H:%M:%S')}] 尝试作为图片预览发送附件: {attachment_filename}")
                photo_sent_successfully = await send_telegram_photo_async(
                    chat_id, attachment_data, attachment_filename, caption=caption
                )
            
            if not photo_sent_successfully:
                if config.TELEGRAM_IMAGE_PREVIEW and attachment_content_type in SUPPORTED_IMAGE_MIME_TYPES:
                    logger.info(f"[{time.strftime('%H:%M:%S')}] 附件图片预览发送失败或不适用，作为文档发送: {attachment_filename}")
                else:
                    logger.debug(f"[{time.strftime('%H:%M:%S')}] 作为文档发送附件: {attachment_filename}")
                
                if file_size_bytes > 0: # Ensure data is not empty before sending as document
                    await send_telegram_document_async(
                        chat_id, attachment_data, attachment_filename, caption=caption
                    )
                else:
                    logger.warning(f"[{time.strftime('%H:%M:%S')}] 附件 '{attachment_filename}' 数据为空，跳过发送。")

    elif not parsed_email['attachments']:
        logger.debug(f"[{time.strftime('%H:%M:%S')}] 邮件 UID {email_uid} 无附件。")
    else: # Attachments exist but FORWARD_ATTACHMENTS is false
        logger.info(f"[{time.strftime('%H:%M:%S')}] 根据配置，跳过发送邮件 UID {email_uid} 的 {len(parsed_email['attachments'])} 个附件.")
    
    logger.info(f"[{time.strftime('%H:%M:%S')}] 邮件 UID {email_uid} ('{parsed_email['subject']}') 转发到 Telegram 完成。")
