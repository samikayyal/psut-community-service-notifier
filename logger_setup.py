import logging
import sys

from error_notifier import NtfyErrorHandler, install_exception_hook

install_exception_hook(__name__)

# Configure the root logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger("PSUT_SCRAPER")

ntfy_handler = NtfyErrorHandler(level=logging.ERROR)
ntfy_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)
logger.addHandler(ntfy_handler)
