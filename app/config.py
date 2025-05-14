import os
from dotenv import load_dotenv
import logging
import time

dotenv_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)

IMAP_HOST = os.getenv('IMAP_HOST')
IMAP_PORT = int(os.getenv('IMAP_PORT', 993))
IMAP_USER = os.getenv('IMAP_USER')
IMAP_PASSWORD = os.getenv('IMAP_PASSWORD')
IMAP_MAILBOX = os.getenv('IMAP_MAILBOX', 'INBOX')

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

LOG_LEVEL_STR = os.getenv('LOG_LEVEL', 'INFO').upper()
LOG_LEVEL = getattr(logging, LOG_LEVEL_STR, logging.INFO)

PROCESSED_FOLDER_NAME = os.getenv('PROCESSED_FOLDER_NAME', None)
if PROCESSED_FOLDER_NAME == "":
    PROCESSED_FOLDER_NAME = None

# Email Quote Handling Configuration
ALLOWED_QUOTE_HANDLING_MODES = ['remove', 'markdown', 'preserve_text']
EMAIL_QUOTE_HANDLING = os.getenv('EMAIL_QUOTE_HANDLING', 'markdown').lower()
if EMAIL_QUOTE_HANDLING not in ALLOWED_QUOTE_HANDLING_MODES:
    logging.warning(
        f"Invalid EMAIL_QUOTE_HANDLING value: '{EMAIL_QUOTE_HANDLING}'. "
        f"Defaulting to 'markdown'. Allowed values are: {', '.join(ALLOWED_QUOTE_HANDLING_MODES)}"
    )
    EMAIL_QUOTE_HANDLING = 'markdown'

# Telegram Header Fields Configuration
# Defines which email header fields to display in the Telegram message.
# Comma-separated string, e.g., "subject,from,date,to,cc,importance"
# Known fields: subject, from, to, cc, date, importance
DEFAULT_TELEGRAM_HEADER_FIELDS = "subject,from,date"
TELEGRAM_HEADER_FIELDS_STR = os.getenv('TELEGRAM_HEADER_FIELDS', DEFAULT_TELEGRAM_HEADER_FIELDS)
TELEGRAM_HEADER_FIELDS = [field.strip().lower() for field in TELEGRAM_HEADER_FIELDS_STR.split(',')]

# Validate known fields (optional, but good for preventing typos)
KNOWN_HEADER_FIELDS = {'subject', 'from', 'to', 'cc', 'date', 'importance', 'message_id'}
for field in TELEGRAM_HEADER_FIELDS:
    if field not in KNOWN_HEADER_FIELDS:
        logging.warning(f"Unknown field '{field}' in TELEGRAM_HEADER_FIELDS. It will be ignored. Known fields are: {', '.join(KNOWN_HEADER_FIELDS)}")

# Telegram Image Preview Configuration
# If true, attempts to send image attachments as photo previews instead of documents.
TELEGRAM_IMAGE_PREVIEW_STR = os.getenv('TELEGRAM_IMAGE_PREVIEW', 'false').lower()
TELEGRAM_IMAGE_PREVIEW = TELEGRAM_IMAGE_PREVIEW_STR == 'true'

# Max size for image preview in MB (Telegram's limit for photos is around 5-10MB)
# Set a conservative default, e.g., 5MB.
TELEGRAM_IMAGE_PREVIEW_MAX_SIZE_MB = float(os.getenv('TELEGRAM_IMAGE_PREVIEW_MAX_SIZE_MB', '5.0'))
TELEGRAM_IMAGE_PREVIEW_MAX_SIZE_BYTES = int(TELEGRAM_IMAGE_PREVIEW_MAX_SIZE_MB * 1024 * 1024)

# Filtering and Content Forwarding Configuration
def compile_regex(pattern_str, flag=re.IGNORECASE):
    if pattern_str:
        try:
            return re.compile(pattern_str, flag)
        except re.error as e:
            logging.error(f"Invalid regex for '{pattern_str}': {e}. This filter will be disabled.")
            return None
    return None

FILTER_SENDER_BLACKLIST_REGEX_STR = os.getenv('FILTER_SENDER_BLACKLIST_REGEX', '')
FILTER_SENDER_BLACKLIST_REGEX = compile_regex(FILTER_SENDER_BLACKLIST_REGEX_STR)

FILTER_SENDER_WHITELIST_REGEX_STR = os.getenv('FILTER_SENDER_WHITELIST_REGEX', '')
FILTER_SENDER_WHITELIST_REGEX = compile_regex(FILTER_SENDER_WHITELIST_REGEX_STR)

FILTER_SUBJECT_BLACKLIST_REGEX_STR = os.getenv('FILTER_SUBJECT_BLACKLIST_REGEX', '')
FILTER_SUBJECT_BLACKLIST_REGEX = compile_regex(FILTER_SUBJECT_BLACKLIST_REGEX_STR)

FORWARD_ATTACHMENTS_STR = os.getenv('FORWARD_ATTACHMENTS', 'true').lower()
FORWARD_ATTACHMENTS = FORWARD_ATTACHMENTS_STR == 'true'

FORWARD_BODY_STR = os.getenv('FORWARD_BODY', 'true').lower()
FORWARD_BODY = FORWARD_BODY_STR == 'true'

logging.basicConfig(
    level=LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S', 
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

def validate_config():
    required_vars = {
        "IMAP_HOST": IMAP_HOST, "IMAP_USER": IMAP_USER, "IMAP_PASSWORD": IMAP_PASSWORD,
        "TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN, "TELEGRAM_CHAT_ID": TELEGRAM_CHAT_ID,
    }
    missing_vars = [key for key, value in required_vars.items() if value is None]
    if missing_vars:
        logger.critical(f"Missing critical environment variables: {', '.join(missing_vars)}")
        raise ValueError(f"Missing critical environment variables: {', '.join(missing_vars)}")
    logger.info("Configuration loaded successfully.")

validate_config()
