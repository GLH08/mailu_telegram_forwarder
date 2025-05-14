import email
from email.header import decode_header
from email.utils import parsedate_to_datetime
import html2text
import markdownify
from bs4 import BeautifulSoup
import logging
import chardet
import time
import re
from . import config

logger = logging.getLogger(__name__)

MAX_TELEGRAM_MESSAGE_LENGTH = 4096
EFFECTIVE_MAX_LENGTH = MAX_TELEGRAM_MESSAGE_LENGTH - 30

def decode_email_header(header_value):
    if not header_value: return ""
    decoded_parts = []
    for part, charset in decode_header(header_value):
        if isinstance(part, bytes):
            try: decoded_parts.append(part.decode(charset or 'utf-8', errors='replace'))
            except LookupError: decoded_parts.append(part.decode('utf-8', errors='replace'))
        else: decoded_parts.append(part)
    return "".join(decoded_parts)

def handle_email_quotes(text_body):
    if not text_body or not isinstance(text_body, str):
        return text_body

    lines = text_body.splitlines()
    processed_lines = []
    
    # Regex to identify typical quote headers or forward separators
    quote_header_pattern = re.compile(r"^(on\s.*?wrote:|在\s.*?写道：|le\s.*?a écrit\s?:|from:.*?subject:.*?date:)", re.IGNORECASE | re.DOTALL)
    forward_separator_pattern = re.compile(r"^-+.*?forwarded message.*?-+$|^-+original message-+$", re.IGNORECASE)
    # Regex to identify a line that likely starts a quote (e.g., "> ", ">> ")
    quote_line_pattern = re.compile(r"^(>\s*)+", re.UNICODE)

    handling_mode = config.EMAIL_QUOTE_HANDLING

    if handling_mode == 'remove':
        in_quote_block = False
        for line in lines:
            stripped_line = line.strip()
            if quote_header_pattern.match(stripped_line) or forward_separator_pattern.match(stripped_line):
                in_quote_block = True # Assume rest of the email from here might be quoted
                # Optionally, add a placeholder like "[引用内容已移除]"
                # processed_lines.append("[引用内容已移除]")
                break # Stop processing further lines
            if quote_line_pattern.match(line):
                in_quote_block = True
                continue # Skip this line
            if in_quote_block and not line.strip(): # Heuristic: empty line might end a quote block
                 # This is tricky, for 'remove' mode, we might remove too much or too little.
                 # A more robust solution would require deeper parsing.
                 pass # For now, continue skipping if we think we are in a quote block.
            if not in_quote_block:
                processed_lines.append(line)
        # If nothing is left (e.g. whole email was a quote), return empty or placeholder
        if not processed_lines and lines: # Original had content
             return "_[引用内容已移除]_"

    elif handling_mode == 'markdown':
        for line in lines:
            stripped_line = line.strip()
            if quote_header_pattern.match(stripped_line) or forward_separator_pattern.match(stripped_line):
                # For markdown, we can represent these as a separator or a blockquote too
                processed_lines.append(f"> {stripped_line}")
                continue
            if quote_line_pattern.match(line):
                # Prepend "> " to lines that already look like quotes,
                # or ensure they start with "> " if we want to standardize.
                # This simplistic approach might add extra ">" if already formatted.
                # A better way: remove existing ">" then add one.
                cleaned_from_gt = quote_line_pattern.sub('', line)
                processed_lines.append(f"> {cleaned_from_gt.lstrip()}")
            else:
                processed_lines.append(line)
                
    elif handling_mode == 'preserve_text':
        for line in lines:
            stripped_line = line.strip()
            if quote_header_pattern.match(stripped_line) or forward_separator_pattern.match(stripped_line):
                # Skip these header lines for 'preserve_text' mode
                continue
            # Remove leading '>' and optional space.
            cleaned_line = quote_line_pattern.sub('', line)
            processed_lines.append(cleaned_line)
    else: # Default to 'preserve_text' or original if mode is unknown (though config should prevent this)
        return text_body

    return "\n".join(processed_lines).strip()

def get_email_body(msg):
    body_plain = ""; body_html = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type(); content_disposition = str(part.get("Content-Disposition", "")).lower()
            if "attachment" not in content_disposition:
                payload = part.get_payload(decode=True)
                if payload is None: continue
                charset = part.get_content_charset() or chardet.detect(payload).get('encoding') or 'utf-8'
                try: decoded_payload = payload.decode(charset, errors='replace')
                except Exception: decoded_payload = payload.decode('utf-8', errors='replace')
                
                if content_type == "text/plain" and not body_plain: body_plain = decoded_payload
                elif content_type == "text/html" and not body_html: body_html = decoded_payload
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or chardet.detect(payload).get('encoding') or 'utf-8'
            try: decoded_payload = payload.decode(charset, errors='replace')
            except Exception: decoded_payload = payload.decode('utf-8', errors='replace')

            if msg.get_content_type() == "text/plain": body_plain = decoded_payload
            elif msg.get_content_type() == "text/html": body_html = decoded_payload

    final_body_text = ""
    processed_html_successfully = False

    if body_html:
        try:
            # Try markdownify first
            # Configure markdownify: strip unwanted tags, convert headings, etc.
            # Example: markdownify.markdownify(body_html, heading_style=markdownify.টেড_HEADING, strip=['script', 'style'])
            final_body_text = markdownify.markdownify(body_html, heading_style="ATX", strip=['script', 'style']).strip()
            logger.debug(f"[{time.strftime('%H:%M:%S')}] Successfully converted HTML to Markdown using markdownify.")
            processed_html_successfully = True
        except Exception as e_md:
            logger.warning(f"[{time.strftime('%H:%M:%S')}] markdownify conversion failed: {e_md}. Falling back to html2text.")
            try:
                h = html2text.HTML2Text()
                h.ignore_links = False
                h.ignore_images = True
                h.body_width = 0
                h.unicode_snob = True
                h.emphasis_mark = '*'
                h.strong_mark = '**'
                final_body_text = h.handle(body_html).strip()
                logger.debug(f"[{time.strftime('%H:%M:%S')}] Successfully converted HTML to text using html2text.")
                processed_html_successfully = True
            except Exception as e_h2t:
                logger.error(f"[{time.strftime('%H:%M:%S')}] html2text conversion also failed: {e_h2t}. Falling back to BeautifulSoup.")
                try:
                    soup = BeautifulSoup(body_html, "html.parser")
                    final_body_text = soup.get_text(separator="\n").strip()
                    logger.debug(f"[{time.strftime('%H:%M:%S')}] Extracted text using BeautifulSoup.")
                    processed_html_successfully = True # Considered successful for text extraction
                except Exception as e_bs:
                    logger.error(f"[{time.strftime('%H:%M:%S')}] BeautifulSoup text extraction failed: {e_bs}")
                    # If all HTML processing fails, body_html content is lost for now.
                    # We might assign body_html to final_body_text directly if we want raw html as last resort.
                    final_body_text = "" # Or some error message like "_[HTML parsing failed]_"

    if not processed_html_successfully and body_plain:
        logger.debug(f"[{time.strftime('%H:%M:%S')}] Using plain text body as HTML processing was not successful or HTML body was empty.")
        final_body_text = body_plain.strip()
    elif not body_html and body_plain: # Only plain text was available
        logger.debug(f"[{time.strftime('%H:%M:%S')}] No HTML body found, using plain text body.")
        final_body_text = body_plain.strip()
    
    # Apply quote handling to the chosen text
    cleaned_body = handle_email_quotes(final_body_text)

    if not cleaned_body.strip() and not (config.EMAIL_QUOTE_HANDLING == 'remove' and final_body_text.strip()):
         # If cleaned_body is empty, but it wasn't because 'remove' mode cleared actual content
        return "_[邮件正文为空]_"
    return cleaned_body

def get_attachments(msg):
    attachments = []
    for part in msg.walk():
        content_disposition = str(part.get("Content-Disposition", "")).lower()
        if ("attachment" in content_disposition) or part.get_filename():
            # Ensure we are not picking up inline images that html2text might have ignored
            content_type_main = part.get_content_type().split(';')[0].strip().lower()
            if "inline" in content_disposition and content_type_main.startswith("image/"):
                continue # Skip inline images if we are generally ignoring them

            filename = part.get_filename()
            if filename: filename = decode_email_header(filename)
            else:
                filename = part.get_param('name', header='content-type')
                if filename: filename = decode_email_header(filename)
                else: filename = f"attachment_{len(attachments) + 1}"
            try:
                attachment_data = part.get_payload(decode=True)
                if attachment_data:
                    attachments.append({"filename": filename, "data": attachment_data, "content_type": part.get_content_type()})
            except Exception as e: logger.error(f"[{time.strftime('%H:%M:%S')}] Could not decode attachment {filename}: {e}")
    return attachments

def parse_email(raw_email_bytes, uid=None):
    msg = email.message_from_bytes(raw_email_bytes)
    subject = decode_email_header(msg.get("Subject", "[无主题]"))
    from_ = decode_email_header(msg.get("From", "[未知发件人]"))
    to_ = decode_email_header(msg.get("To", "[未知收件人]"))
    cc_ = decode_email_header(msg.get("Cc"))
    date_str = msg.get("Date"); email_date_obj = None
    if date_str:
        try: email_date_obj = parsedate_to_datetime(date_str)
        except Exception: logger.warning(f"[{time.strftime('%H:%M:%S')}] Could not parse date string: {date_str}")
    
    # Parse email importance
    importance_str = msg.get("Importance", "").lower()
    x_priority_str = msg.get("X-Priority", "").lower()
    email_importance = "normal" # Default

    if "high" in importance_str or "1" in x_priority_str or "2" in x_priority_str: # X-Priority 1 (Highest), 2 (High)
        email_importance = "high"
    elif "low" in importance_str or "5" in x_priority_str or "4" in x_priority_str: # X-Priority 5 (Lowest), 4 (Low)
        email_importance = "low"
    # 'normal' (Importance) or '3' (X-Priority) or empty/not present defaults to 'normal'

    body = get_email_body(msg) # Gets only text body
    attachments = get_attachments(msg) # Gets only actual file attachments

    return {"uid": uid, "subject": subject, "from": from_, "to": to_, "cc": cc_ if cc_ else "N/A",
            "date": email_date_obj.strftime("%Y-%m-%d %H:%M:%S %Z") if email_date_obj else date_str or "N/A",
            "body": body,
            "importance": email_importance,
            "attachments": attachments,
            "message_id": msg.get("Message-ID", "N/A")}

def split_message(text, max_length=EFFECTIVE_MAX_LENGTH):
    parts = []; temp_parts = []
    if not text: return [""]
    current_text = str(text)
    while len(current_text) > 0:
        if len(current_text) <= max_length: temp_parts.append(current_text); break
        else:
            split_at = current_text.rfind('\n', 0, max_length)
            if split_at == -1 or split_at == 0: split_at = max_length
            temp_parts.append(current_text[:split_at])
            current_text = current_text[split_at:].lstrip('\n')
    if not temp_parts: return [""]
    total_parts = len(temp_parts)
    if total_parts > 1:
        for i, part_content in enumerate(temp_parts): parts.append(f"{part_content}\n_(第 {i+1}/{total_parts} 部分)_")
    else: parts = temp_parts
    return parts
