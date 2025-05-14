from imapclient import IMAPClient
from imapclient.exceptions import IMAPClientError, LoginError
import ssl
import logging
import time
import socket
import asyncio
from . import config
from .email_parser import parse_email # Ensure this is the updated version
from .telegram_sender import forward_email_to_telegram # Ensure this is the updated version

logger = logging.getLogger(__name__)

CONNECTION_TIMEOUT_SECONDS = 30
IDLE_CHECK_TIMEOUT_SECONDS = 25 * 60

class IMAPHandler:
    def __init__(self):
        self.host = config.IMAP_HOST; self.port = config.IMAP_PORT; self.user = config.IMAP_USER
        self.password = config.IMAP_PASSWORD; self.mailbox = config.IMAP_MAILBOX
        self.processed_folder = config.PROCESSED_FOLDER_NAME; self.client = None
        self.is_mailbox_selected = False; self.ssl_context = ssl.create_default_context()

    def _close_existing_client(self):
        if self.client:
            try: logger.info(f"[{time.strftime('%H:%M:%S')}] Closing existing IMAP client session."); self.client.logout()
            except Exception as e: logger.debug(f"[{time.strftime('%H:%M:%S')}] Exception while logging out (ignored): {e}")
        self.client = None; self.is_mailbox_selected = False

    def _select_mailbox_if_needed(self):
        if not self.client: logger.warning(f"[{time.strftime('%H:%M:%S')}] Cannot select mailbox, client is None."); return False
        try:
            select_info = self.client.select_folder(self.mailbox, readonly=False)
            if select_info:
                logger.info(f"[{time.strftime('%H:%M:%S')}] Successfully selected/re-selected mailbox: {self.mailbox}. Info: {select_info}")
                self.is_mailbox_selected = True; return True
            else: logger.error(f"[{time.strftime('%H:%M:%S')}] select_folder for '{self.mailbox}' returned None/empty."); self.is_mailbox_selected = False; return False
        except (IMAPClientError, socket.error, BrokenPipeError) as e:
            logger.error(f"[{time.strftime('%H:%M:%S')}] Error during select_folder for '{self.mailbox}': {e}")
            self.is_mailbox_selected = False; self._close_existing_client(); return False

    def connect(self): # This method now performs a single connection attempt.
        self._close_existing_client() # Ensure any old client is gone
        self.connection_attempts += 1

        try:
            logger.info(f"[{time.strftime('%H:%M:%S')}] Attempting to connect (attempt {self.connection_attempts}) to IMAP server {self.host}:{self.port}")
            self.client = IMAPClient(self.host, port=self.port, ssl=True, ssl_context=self.ssl_context, timeout=CONNECTION_TIMEOUT_SECONDS)
            self.client.login(self.user, self.password)
            logger.info(f"[{time.strftime('%H:%M:%S')}] Successfully connected and logged in as {self.user}")
            
            if not self.client.folder_exists(self.mailbox):
                logger.critical(f"Mailbox '{self.mailbox}' does not exist. Exiting."); self._close_existing_client(); raise ValueError(f"Mailbox '{self.mailbox}' not found.")
            
            if not self._select_mailbox_if_needed(): # This already handles its own errors and might close client
                logger.error(f"[{time.strftime('%H:%M:%S')}] Mailbox selection failed after connect.")
                # _select_mailbox_if_needed might have closed the client, ensure it's None if failed
                if self.client: self._close_existing_client()
                return False # Indicate connection process failed at selection stage

            if self.processed_folder and not self.client.folder_exists(self.processed_folder):
                try:
                    self.client.create_folder(self.processed_folder)
                    logger.info(f"[{time.strftime('%H:%M:%S')}] Created folder: {self.processed_folder}")
                except IMAPClientError as e:
                    logger.error(f"Failed to create folder {self.processed_folder}: {e}. Will mark as read instead.")
                    self.processed_folder = None # Disable moving to this folder
            
            # Connection successful
            logger.info(f"[{time.strftime('%H:%M:%S')}] IMAP connection fully established. Resetting attempts.")
            self.connection_attempts = 0
            self.current_reconnect_delay = INITIAL_RECONNECT_DELAY_SECONDS
            return True

        except LoginError as e:
            logger.critical(f"IMAP Login failed: {e}. Check credentials. This is a fatal error for the current session.")
            self._close_existing_client()
            raise # Re-raise to be caught by main loop for exit
        
        except (IMAPClientError, socket.timeout, TimeoutError, ConnectionRefusedError, OSError, BrokenPipeError) as e:
            logger.error(f"[{time.strftime('%H:%M:%S')}] IMAP connection error (attempt {self.connection_attempts}, type {type(e).__name__}): {e}.")
            self._close_existing_client() # Ensure client is closed on error
            self.current_reconnect_delay = min(MAX_RECONNECT_DELAY_SECONDS, self.current_reconnect_delay * RECONNECT_BACKOFF_FACTOR)
            logger.info(f"Next reconnect attempt will be in {self.current_reconnect_delay}s.")
            # Optional: Check for MAX_CONNECTION_ATTEMPTS_BEFORE_LONG_PAUSE
            if self.connection_attempts >= MAX_CONNECTION_ATTEMPTS_BEFORE_LONG_PAUSE:
                logger.warning(f"Max connection attempts ({MAX_CONNECTION_ATTEMPTS_BEFORE_LONG_PAUSE}) reached. Pausing for {LONG_PAUSE_SECONDS}s before resetting attempts.")
                # This sleep should ideally be handled by the caller (idle_loop) to be async
                # For now, if connect is called in a sync context that expects this, it's okay.
                # However, idle_loop will manage async sleeps.
                # We can signal idle_loop to take a long pause.
                # For simplicity here, just reset for next cycle of calls from idle_loop.
                # self.connection_attempts = 0 # Reset after long pause, or let idle_loop manage
                # self.current_reconnect_delay = LONG_PAUSE_SECONDS # Signal a long pause
            return False

        except Exception as e: # Catch any other unexpected errors
            logger.error(f"[{time.strftime('%H:%M:%S')}] Unexpected error during IMAP connection (attempt {self.connection_attempts}, type {type(e).__name__}): {e}", exc_info=True)
            self._close_existing_client()
            self.current_reconnect_delay = min(MAX_RECONNECT_DELAY_SECONDS, self.current_reconnect_delay * RECONNECT_BACKOFF_FACTOR)
            logger.info(f"Next reconnect attempt will be in {self.current_reconnect_delay}s due to unexpected error.")
            return False

    async def process_message(self, msg_uid, raw_email_bytes):
        try:
            logger.info(f"[{time.strftime('%H:%M:%S')}] Processing email UID {msg_uid}")
            parsed_email = parse_email(raw_email_bytes, uid=msg_uid)

            # Apply filtering rules
            sender = parsed_email.get('from', '')
            subject = parsed_email.get('subject', '')

            # Whitelist check (overrides blacklist if present and matched)
            if config.FILTER_SENDER_WHITELIST_REGEX:
                if not config.FILTER_SENDER_WHITELIST_REGEX.search(sender):
                    logger.info(f"[{time.strftime('%H:%M:%S')}] Email UID {msg_uid} from '{sender}' (Subject: '{subject}') skipped: Sender not in whitelist.")
                    # Mark as seen even if skipped by filter, to avoid re-processing
                    if self.client and self.is_mailbox_selected: self.client.add_flags([msg_uid], [b'\\Seen'])
                    return
            # Blacklist check (only if whitelist is not active or did not cause a skip)
            elif config.FILTER_SENDER_BLACKLIST_REGEX:
                if config.FILTER_SENDER_BLACKLIST_REGEX.search(sender):
                    logger.info(f"[{time.strftime('%H:%M:%S')}] Email UID {msg_uid} from '{sender}' (Subject: '{subject}') skipped: Sender in blacklist.")
                    if self.client and self.is_mailbox_selected: self.client.add_flags([msg_uid], [b'\\Seen'])
                    return
            
            if config.FILTER_SUBJECT_BLACKLIST_REGEX:
                if config.FILTER_SUBJECT_BLACKLIST_REGEX.search(subject):
                    logger.info(f"[{time.strftime('%H:%M:%S')}] Email UID {msg_uid} (Subject: '{subject}') skipped: Subject in blacklist.")
                    if self.client and self.is_mailbox_selected: self.client.add_flags([msg_uid], [b'\\Seen'])
                    return

            await forward_email_to_telegram(parsed_email)
            if not self.client:
                 logger.warning(f"[{time.strftime('%H:%M:%S')}] IMAP client None before marking UID {msg_uid}. Reconnecting.")
                 if not self.connect(): logger.error(f"[{time.strftime('%H:%M:%S')}] Reconnect failed. UID {msg_uid} not marked."); return
            if not self.is_mailbox_selected:
                if not self._select_mailbox_if_needed(): logger.error(f"[{time.strftime('%H:%M:%S')}] Failed to select mailbox for UID {msg_uid}. Cannot mark."); return
            if not self.client: logger.error(f"[{time.strftime('%H:%M:%S')}] IMAP client None after select for UID {msg_uid}. Cannot mark."); return
            if self.processed_folder and self.client.folder_exists(self.processed_folder):
                logger.info(f"[{time.strftime('%H:%M:%S')}] Moving email UID {msg_uid} to '{self.processed_folder}'")
                self.client.move([msg_uid], self.processed_folder)
            else:
                if self.processed_folder: logger.warning(f"[{time.strftime('%H:%M:%S')}] Folder '{self.processed_folder}' not found. Marking UID {msg_uid} as read.")
                logger.info(f"[{time.strftime('%H:%M:%S')}] Marking email UID {msg_uid} as \\Seen")
                self.client.add_flags([msg_uid], [b'\\Seen'])
            logger.info(f"[{time.strftime('%H:%M:%S')}] Successfully processed and marked/moved email UID {msg_uid}")
        except Exception as e: logger.error(f"[{time.strftime('%H:%M:%S')}] Critical error processing/marking UID {msg_uid} ({type(e).__name__}): {e}", exc_info=True)

    async def _handle_unseen_messages(self):
        try:
            if not self.client or not self.is_mailbox_selected:
                logger.warning(f"[{time.strftime('%H:%M:%S')}] Client not ready for unseen check. Reconnecting/reselecting.")
                if not self.connect(): return False
                if not self.is_mailbox_selected: logger.error(f"[{time.strftime('%H:%M:%S')}] Failed select after connect in _handle_unseen."); return False
            unseen_msgs_uids = self.client.search(['UNSEEN'])
            if unseen_msgs_uids:
                logger.info(f"[{time.strftime('%H:%M:%S')}] Found {len(unseen_msgs_uids)} unseen messages. Processing.")
                for i in range(0, len(unseen_msgs_uids), 5):
                    chunk_uids = unseen_msgs_uids[i:i+5]
                    try:
                        fetched_data = self.client.fetch(chunk_uids, ['RFC822'])
                        for msg_uid, data in fetched_data.items():
                            raw_email_bytes = data.get(b'RFC822')
                            if raw_email_bytes: await self.process_message(msg_uid, raw_email_bytes)
                            else: logger.warning(f"[{time.strftime('%H:%M:%S')}] No RFC822 for UID {msg_uid} in unseen check.")
                    except (IMAPClientError, socket.error, BrokenPipeError) as fetch_err:
                        logger.error(f"[{time.strftime('%H:%M:%S')}] Error fetching unseen chunk: {fetch_err}. Reconnecting in IDLE loop."); self.is_mailbox_selected = False; self._close_existing_client(); raise
                    await asyncio.sleep(0.5)
                return True
            return False
        except (IMAPClientError, socket.error, OSError, BrokenPipeError) as e:
            logger.error(f"[{time.strftime('%H:%M:%S')}] Error during unseen check: {e}. Reconnecting in IDLE loop."); self.is_mailbox_selected = False; self._close_existing_client(); raise

    async def idle_loop(self):
        logger.info(f"[{time.strftime('%H:%M:%S')}] Initializing IDLE mode for mailbox {self.mailbox}...")
        
        while True:
            try:
                # Connection and mailbox selection management
                if not self.client or not self.is_mailbox_selected:
                    if not self.client:
                        logger.info(f"[{time.strftime('%H:%M:%S')}] IMAP client is not connected.")
                        if self.connection_attempts >= MAX_CONNECTION_ATTEMPTS_BEFORE_LONG_PAUSE:
                            logger.warning(f"Reached {self.connection_attempts} connection attempts. Taking a long pause for {LONG_PAUSE_SECONDS}s.")
                            await asyncio.sleep(LONG_PAUSE_SECONDS)
                            self.connection_attempts = 0 # Reset attempts after long pause
                            self.current_reconnect_delay = INITIAL_RECONNECT_DELAY_SECONDS
                            continue # Retry connection immediately after long pause
                        elif self.connection_attempts > 0: # It's a retry, not the very first attempt in app lifecycle
                            logger.info(f"Waiting {self.current_reconnect_delay}s before next connection attempt ({self.connection_attempts + 1})...")
                            await asyncio.sleep(self.current_reconnect_delay)
                        
                        if not self.connect(): # connect() now handles attempt counting and delay calculation
                            # connect() returned False, means it failed and has set up for next retry
                            continue # Loop to retry connection after the calculated delay
                        # If connect() was successful, it reset attempts and delay.

                    if not self.is_mailbox_selected: # Client connected, but mailbox not selected
                        logger.info(f"[{time.strftime('%H:%M:%S')}] Mailbox not selected, re-selecting '{self.mailbox}'...")
                        if not self._select_mailbox_if_needed():
                            logger.error(f"[{time.strftime('%H:%M:%S')}] Failed to select mailbox in IDLE loop. Will attempt reconnect in next cycle.")
                            # _select_mailbox_if_needed might close client if it fails badly
                            if self.client: self._close_existing_client() # Ensure client is closed to force reconnect
                            continue # To top of loop, will trigger reconnect logic
                
                # At this point, client should be connected and mailbox selected
                await self._handle_unseen_messages() # Process any existing unseen messages

                logger.info(f"[{time.strftime('%H:%M:%S')}] Entering IDLE state (timeout: {IDLE_CHECK_TIMEOUT_SECONDS}s).")
                self.client.idle()
                logger.debug(f"[{time.strftime('%H:%M:%S')}] IMAPClient.idle() called.")
                responses = self.client.idle_check(timeout=IDLE_CHECK_TIMEOUT_SECONDS)
                logger.info(f"[{time.strftime('%H:%M:%S')}] IMAPClient.idle_check() returned: {responses if responses else 'Timeout/no specific response'}")
                self.client.idle_done()
                logger.debug(f"[{time.strftime('%H:%M:%S')}] IMAPClient.idle_done() called.")

                if responses:
                    logger.info(f"[{time.strftime('%H:%M:%S')}] IDLE responses received. Next loop will check unseen.")
                    # _handle_unseen_messages will be called at the start of the next loop iteration.
                else: # IDLE timed out
                    logger.debug(f"[{time.strftime('%H:%M:%S')}] IDLE check timed out. Sending NOOP to keep alive.")
                    try:
                        if self.client:
                            self.client.noop()
                            logger.info(f"[{time.strftime('%H:%M:%S')}] Sent NOOP successfully.")
                        else: # Should not happen if logic above is correct
                            logger.warning(f"[{time.strftime('%H:%M:%S')}] Client None, cannot NOOP. Forcing reconnect.")
                            self._close_existing_client() # Force reconnect in next loop
                    except (IMAPClientError, socket.error, BrokenPipeError) as noop_e:
                        logger.warning(f"[{time.strftime('%H:%M:%S')}] Failed NOOP: {noop_e}. Stale connection likely. Forcing reconnect.")
                        self._close_existing_client() # Force reconnect
                
                await asyncio.sleep(1) # Brief pause before next IDLE cycle or unseen check

            except LoginError as e: # Raised by self.connect()
                logger.critical(f"IMAP Login failed during idle_loop recovery: {e}. This is fatal. Exiting application.")
                # In a real app, you might want to signal the main thread to exit gracefully.
                # For this script, re-raising might be caught by a top-level handler in main.py or just stop the loop.
                raise

            except (socket.timeout, TimeoutError) as e: # More general timeouts during IDLE ops
                logger.warning(f"[{time.strftime('%H:%M:%S')}] Timeout in IDLE operations ({type(e).__name__}): {e}. Forcing reconnect.")
                self._close_existing_client() # Force reconnect
                # Loop will continue and trigger reconnect logic

            except (IMAPClientError, ConnectionError, BrokenPipeError, socket.error, OSError) as e:
                logger.error(f"[{time.strftime('%H:%M:%S')}] Major IMAP/network error in IDLE loop ({type(e).__name__}): {e}. Forcing reconnect.")
                self._close_existing_client() # Force reconnect
                # Loop will continue and trigger reconnect logic

            except Exception as e: # Catch-all for truly unexpected errors in the loop
                logger.critical(f"[{time.strftime('%H:%M:%S')}] Unexpected critical error in IDLE loop ({type(e).__name__}): {e}", exc_info=True)
                logger.info(f"[{time.strftime('%H:%M:%S')}] Attempting to recover by forcing reconnect.")
                self._close_existing_client() # Force reconnect
                # Loop will continue and trigger reconnect logic. Add a small delay to prevent rapid crash loops on persistent unknown errors.
                await asyncio.sleep(5)

    def close(self):
        logger.info(f"[{time.strftime('%H:%M:%S')}] Initiating IMAP client shutdown.")
        self._close_existing_client()
