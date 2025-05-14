import asyncio
import signal
import logging
from . import config 
from .imap_handler import IMAPHandler

logger = logging.getLogger(__name__)

async def main_loop():
    logger.info("Starting Mailu Telegram Forwarder...")
    imap_handler = IMAPHandler()
    stop_event = asyncio.Event(); loop = asyncio.get_event_loop()
    def signal_handler():
        logger.info("Shutdown signal received. Setting stop event...")
        if not stop_event.is_set(): stop_event.set()
        else: logger.info("Stop event already set.")
    for sig in (signal.SIGINT, signal.SIGTERM):
        try: loop.add_signal_handler(sig, signal_handler)
        except (NotImplementedError, RuntimeError) as e:
            logger.warning(f"loop.add_signal_handler for {sig} not fully supported: {e}")
            try: signal.signal(sig, lambda s, f: signal_handler())
            except Exception as sig_e: logger.error(f"Failed to set signal.signal fallback for {sig}: {sig_e}")
    idle_task = None
    try:
        if not imap_handler.connect(): logger.critical("Initial IMAP connect failed. Exiting."); return
        logger.info("Initial IMAP connection successful.")
        idle_task = asyncio.create_task(imap_handler.idle_loop())
        stop_event_task = asyncio.create_task(stop_event.wait())
        done, pending = await asyncio.wait([idle_task, stop_event_task], return_when=asyncio.FIRST_COMPLETED)
        if stop_event_task in done:
            logger.info("Stop event triggered. Shutting down IDLE task.")
            if idle_task and not idle_task.done(): idle_task.cancel()
        elif idle_task in done:
            logger.info("IDLE task completed. Triggering stop event.")
            if not stop_event.is_set(): stop_event.set()
        if pending:
            for task in pending:
                if not task.done(): task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
        if idle_task and idle_task.done() and not idle_task.cancelled():
            exc = idle_task.exception()
            if exc: logger.error(f"IDLE task exited with exception: {exc}", exc_info=exc)
    except asyncio.CancelledError: logger.info("Main loop cancelled.")
    except Exception as e: logger.critical(f"Critical error in main execution: {e}", exc_info=True)
    finally:
        logger.info("Shutting down IMAP handler in main_loop finally...")
        if idle_task and not idle_task.done():
            idle_task.cancel()
            try: await asyncio.gather(idle_task, return_exceptions=True)
            except asyncio.CancelledError: logger.info("IDLE task successfully cancelled during final shutdown.")
        if hasattr(imap_handler, 'close'): imap_handler.close()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try: loop.remove_signal_handler(sig)
            except (NotImplementedError, RuntimeError): 
                try: signal.signal(sig, signal.SIG_DFL)
                except: pass
        logger.info("Mailu Telegram Forwarder stopped.")

if __name__ == "__main__":
    try: asyncio.run(main_loop())
    except KeyboardInterrupt: logger.info("Application interrupted by user (KeyboardInterrupt from asyncio.run).")
    except SystemExit as e: logger.info(f"SystemExit called: {e}")
    except Exception as e: logger.critical(f"Unhandled exception at top level of __main__: {e}", exc_info=True)
