"""Command-line interface for gmail-invoice."""

import argparse
import logging
import os
import sys
from datetime import date, datetime

from dotenv import load_dotenv

from gmail_invoice.gmail_extractor import GMailClient, GMailInvoiceExtractor

logger = logging.getLogger(__name__)


def _resolve_config() -> tuple[str, str]:
    load_dotenv()

    raw_config_dir = os.environ.get("CONFIG_DIR")
    if not raw_config_dir:
        raise ValueError(
            "CONFIG_DIR is not set. Copy .env.example to .env and set CONFIG_DIR to the "
            "folder where you keep credentials.json (for example ~/.config/gmail-invoice)."
        )

    config_dir = os.path.expanduser(raw_config_dir)
    credentials_path = os.path.expanduser(
        os.environ.get(
            "GMAIL_CREDENTIALS_PATH",
            os.path.join(config_dir, "credentials.json"),
        )
    )
    token_path = os.path.expanduser(
        os.environ.get(
            "GMAIL_TOKEN_PATH",
            os.path.join(config_dir, "token.json"),
        )
    )
    return credentials_path, token_path


def _parse_target_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Invalid date {value!r}; expected YYYY-MM-DD."
        ) from exc


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    parser = argparse.ArgumentParser(
        description="Download purchase invoice emails and PDF attachments from Gmail.",
    )
    parser.add_argument(
        "--date",
        type=_parse_target_date,
        help="Target date YYYY-MM-DD (default: today)",
    )
    args = parser.parse_args()

    target_date = args.date or date.today()

    try:
        credentials_path, token_path = _resolve_config()
        api_client = GMailClient(credentials_path, token_path)
        extractor = GMailInvoiceExtractor(api_client, target_date)
        extractor.extract_purchases_for_date()
    except (ValueError, FileNotFoundError) as exc:
        logger.error("%s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
