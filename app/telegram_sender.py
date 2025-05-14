import telegram
from telegram import InputFile # For attachments
from io import BytesIO
import logging
import asyncio
import time
# import mimetypes # Not strictly needed if not handling inline image mime types
# import aiohttp # Not needed as we are not downloading images
from . import config
from .email_parser import split_message

logger = logging.getLogger(__name__)

bot = telegram.Bot(token=config.TELEGRAM_BOT_TOKEN)

# Using legacy Markdown as it's more forgiving than MarkdownV2
PARSEMODE_MARKDOWN = "Markdown" 

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

async def forward_email_to_telegram(parsed_email): # Removed original_eml_bytes
    chat_id = config.TELEGRAM_CHAT_ID; email_uid = parsed_email.get('uid', 'N/A')
    if not chat_id: logger.error(f"..."); return
    logger.info(f"[{time.strftime('%H:%M:%S')}] 开始转发邮件 UID {email_uid} ('{parsed_email['subject']}') 到 Telegram 聊天 {chat_id}")

    header_parts = []
    # Field mapping: config_key -> (Emoji Label, parsed_email_key, use_code_block)
    field_map = {
        "subject": ("🏷️ *主题:*", "subject", True),
        "from": ("👤 *发件人:*", "from", False),
        "to": ("➡️ *收件人:*", "to", False),
        "cc": ("👥 *抄送:*", "cc", False),
        "date": ("📅 *日期:*", "date", True),
        "importance": ("⚠️ *重要性:*", "importance", False), # Emoji will be conditional
        "message_id": ("🆔 *Message-ID:*", "message_id", True)
    }

    for field_key in config.TELEGRAM_HEADER_FIELDS:
        if field_key in field_map:
            label, email_key, use_code_block = field_map[field_key]
            value = parsed_email.get(email_key)

            if value and value != "N/A": # Ensure value exists and is not "N/A"
                value_escaped = escape_markdown_legacy_chars(str(value))
                
                current_label = label
                if field_key == "importance":
                    if value == "high":
                        current_label = f"❗*紧急邮件* ({value_escaped})" # Override label for high importance
                        header_parts.append(current_label) # Special formatting for high importance
                        continue # Skip default formatting for importance if high
                    elif value == "low":
                        current_label = f"📉 *低优先级* ({value_escaped})"
                        # Optionally skip showing 'low' or 'normal' importance if desired
                        # if not config.SHOW_LOW_NORMAL_IMPORTANCE: continue
                    elif value == "normal": # Don't show 'normal' importance by default unless explicitly asked
                        continue # Skip normal importance
                    else: # Should not happen if parser normalizes
                        current_label = f"{label} {value_escaped}"
                
                if use_code_block:
                    header_parts.append(f"{current_label} `{value_escaped}`")
                else:
                    header_parts.append(f"{current_label} {value_escaped}")

    if header_parts:
        header_text = "📧 *新邮件通知*\n\n" + "\n".join(header_parts)
    else: # Fallback if no header fields are configured or all values are N/A
        subject_escaped = escape_markdown_legacy_chars(parsed_email.get('subject', '[无主题]'))
        header_text = f"📧 *新邮件通知*\n\n🏷️ *主题:* `{subject_escaped}`"

    await send_telegram_message_async(chat_id, header_text, parse_mode=PARSEMODE_MARKDOWN)

    email_body_text = parsed_email['body']
    # Escape body for legacy Markdown. html2text output should be somewhat Markdown friendly.
    email_body_text_escaped = escape_markdown_legacy_chars(email_body_text) 
    
    if email_body_text != "_[邮件正文为空]_":
         separator = escape_markdown_legacy_chars("\n\n‐‐‐‐‐‐‐‐‐‐ 正文 ‐‐‐‐‐‐‐‐‐‐\n\n")
         final_body_to_send = separator + email_body_text_escaped
    else: final_body_to_send = email_body_text_escaped
    
    if final_body_to_send:
        logger.debug(f"[{time.strftime('%H:%M:%S')}] 发送邮件正文 UID {email_uid}...")
        await send_telegram_message_async(chat_id, final_body_to_send, parse_mode=PARSEMODE_MARKDOWN)
    
    if parsed_email['attachments']:
        logger.debug(f"[{time.strftime('%H:%M:%S')}] 发送 {len(parsed_email['attachments'])} 个附件，邮件 UID {email_uid}...")
        attachment_count = len(parsed_email['attachments'])
        # Attachment header can use simple Markdown
        attachment_header = f"📎 *附件 ({escape_markdown_legacy_chars(str(attachment_count))}):*"
        await send_telegram_message_async(chat_id, attachment_header, parse_mode=PARSEMODE_MARKDOWN)
        
        for idx, attachment in enumerate(parsed_email['attachments']):
            attachment_data = attachment['data']
            attachment_filename = attachment['filename']
            attachment_content_type = attachment['content_type'].lower()
            
            file_size_bytes = len(attachment_data)
            file_size_kb = file_size_bytes / 1024
            file_size_mb = file_size_kb / 1024
            size_str = f"{file_size_kb:.2f} KB" if file_size_kb < 1024 else f"{file_size_mb:.2f} MB"
            
            logger.debug(f"[{time.strftime('%H:%M:%S')}] 处理附件 {idx+1}/{attachment_count}: {attachment_filename} ({size_str}, {attachment_content_type}) UID {email_uid}")
            
            # Common caption for both photo and document
            caption = (f"文件: {escape_markdown_legacy_chars(attachment_filename)}\n"
                       f"类型: {escape_markdown_legacy_chars(attachment_content_type)}\n"
                       f"大小: {size_str}")

            photo_sent_successfully = False
            if config.TELEGRAM_IMAGE_PREVIEW and \
               attachment_content_type in SUPPORTED_IMAGE_MIME_TYPES and \
               file_size_bytes < config.TELEGRAM_IMAGE_PREVIEW_MAX_SIZE_BYTES:
                
                logger.info(f"[{time.strftime('%H:%M:%S')}] 尝试作为图片预览发送: {attachment_filename}")
                photo_sent_successfully = await send_telegram_photo_async(
                    chat_id,
                    attachment_data,
                    attachment_filename,
                    caption=caption
                )
            
            if not photo_sent_successfully:
                if config.TELEGRAM_IMAGE_PREVIEW and attachment_content_type in SUPPORTED_IMAGE_MIME_TYPES:
                    logger.info(f"[{time.strftime('%H:%M:%S')}] 图片预览发送失败或不适用，作为文档发送: {attachment_filename}")
                else:
                    logger.debug(f"[{time.strftime('%H:%M:%S')}] 作为文档发送: {attachment_filename}")
                
                await send_telegram_document_async(
                    chat_id,
                    attachment_data,
                    attachment_filename,
                    caption=caption
                )
    elif not parsed_email['attachments']: # No attachments to begin with
        logger.debug(f"[{time.strftime('%H:%M:%S')}] 邮件 UID {email_uid} 无附件。")
    else: # Attachments exist but FORWARD_ATTACHMENTS is false
        logger.info(f"[{time.strftime('%H:%M:%S')}] 根据配置，跳过发送邮件 UID {email_uid} 的 {len(parsed_email['attachments'])} 个附件.")
    
    # Removed .eml sending for simplification
    logger.info(f"[{time.strftime('%H:%M:%S')}] 邮件 UID {email_uid} ('{parsed_email['subject']}') 转发到 Telegram 完成。")
