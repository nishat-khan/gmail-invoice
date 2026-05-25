"""
Structure of your Invoice Email:
└── multipart/mixed (MIME type)
    ├── multipart/alternative (MIME type)
    │   ├── text/plain  --> "Your invoice is attached..."
    │   └── text/html   --> [Styled HTML Email]
    └── application/pdf  --> [The actual invoice file payload]
"""

import base64
import json
import logging
import os
import random
import time
from datetime import UTC, date, datetime, timedelta
from email.utils import parseaddr, parsedate_to_datetime

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
DEFAULT_MAX_RETRIES = 5
DEFAULT_MAX_BACKOFF_S = 64.0
RATE_LIMIT_REASONS = frozenset({"rateLimitExceeded", "userRateLimitExceeded"})


def _gmail_error_reasons(error: HttpError) -> set[str]:
    reasons: set[str] = set()
    if error.error_details:
        for detail in error.error_details:
            reason = detail.get("reason")
            if reason:
                reasons.add(reason)
    return reasons


def _is_retryable_gmail_error(error: HttpError) -> bool:
    status = int(error.resp.status)
    if status == 429:
        return True
    if status == 403:
        return bool(_gmail_error_reasons(error) & RATE_LIMIT_REASONS)
    return False


def _backoff_seconds(attempt: int, max_backoff: float) -> float:
    return min((2**attempt) + random.random(), max_backoff)


class GMailClient:
    """Authenticated read-only Gmail API client."""

    def __init__(self, credentials_path: str, token_path: str):
        if not os.path.isfile(credentials_path):
            raise FileNotFoundError(
                f"Gmail credentials not found at {credentials_path}. "
                "Download credentials.json from Google Cloud and place it in CONFIG_DIR."
            )

        creds = None
        if os.path.exists(token_path):
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
                creds = flow.run_local_server(port=0)
            with open(token_path, "w", encoding="utf-8") as token_file:
                token_file.write(creds.to_json())

        self.service = build("gmail", "v1", credentials=creds)
        self._max_retries = int(os.environ.get("GMAIL_API_MAX_RETRIES", DEFAULT_MAX_RETRIES))
        self._max_backoff_s = float(
            os.environ.get("GMAIL_API_MAX_BACKOFF_S", DEFAULT_MAX_BACKOFF_S)
        )

    def _execute_with_retry(self, request):
        attempt = 0
        while True:
            try:
                return request.execute()
            except HttpError as exc:
                if attempt >= self._max_retries or not _is_retryable_gmail_error(exc):
                    raise
                delay = _backoff_seconds(attempt, self._max_backoff_s)
                logger.warning(
                    "Gmail API rate limit hit (retry %d/%d); waiting %.1fs",
                    attempt + 1,
                    self._max_retries,
                    delay,
                )
                time.sleep(delay)
                attempt += 1

    def list_messages(self, query: str) -> dict:
        logger.info("Listing messages: %s", query)
        request = (
            self.service.users()
            .messages()
            .list(userId="me", q=query, maxResults=10)
        )
        return self._execute_with_retry(request)

    def get_message(self, message_id: str) -> dict:
        logger.info("Fetching message %s", message_id)
        request = (
            self.service.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
        )
        return self._execute_with_retry(request)

    def get_attachment(self, message_id: str, attachment_id: str) -> dict:
        logger.info("Fetching attachment %s for message %s", attachment_id, message_id)
        request = (
            self.service.users()
            .messages()
            .attachments()
            .get(userId="me", messageId=message_id, id=attachment_id)
        )
        return self._execute_with_retry(request)


class GMailInvoiceExtractor:
    """Extract purchase emails and PDF attachments for a given date."""

    def __init__(
        self,
        client,
        target_date: date,
        output_dir: str | None = None,
        invoice_parser=None,
    ):
        self.client = client
        self.target_date = target_date
        if output_dir is None:
            output_dir = os.environ.get(
                "GMAIL_INVOICE_OUTPUT_DIR",
                f"invoices_{self.target_date.strftime('%Y_%m_%d')}",
            )
        self.output_dir = os.path.expanduser(output_dir)
        self.invoice_parser = invoice_parser

    @staticmethod
    def _decode_gmail_base64(encoded: str) -> bytes:
        return base64.urlsafe_b64decode(encoded)

    def _walk_parts(self, parts: list) -> list:
        flattened = []
        for part in parts:
            flattened.append(part)
            nested = part.get("parts")
            if nested:
                flattened.extend(self._walk_parts(nested))
        return flattened

    def _build_purchase_query(self) -> str:
        after = self.target_date.strftime("%Y/%m/%d")
        before = (self.target_date + timedelta(days=1)).strftime("%Y/%m/%d")
        return f"category:purchases after:{after} before:{before}"

    def extract_purchases_for_date(self):
        os.makedirs(self.output_dir, exist_ok=True)

        query = self._build_purchase_query()
        logger.info("Query: %s", query)

        list_data = self.client.list_messages(query)
        messages = list_data.get("messages", [])

        if not messages:
            logger.info("No purchase emails found for %s.", self.target_date)
            return

        logger.info("Found %d message(s)", len(messages))
        for msg_ref in messages:
            self._extract_one_message(msg_ref["id"])

    @staticmethod
    def _message_datetime(message: dict, headers: dict) -> datetime:
        date_header = headers.get("Date")
        if date_header:
            return parsedate_to_datetime(date_header.strip())

        internal_date = message.get("internalDate")
        if internal_date:
            return datetime.fromtimestamp(int(internal_date) / 1000, tz=UTC)

        raise ValueError(f"Message {message.get('id')} has no Date header or internalDate.")

    def _save_pdf_attachment(self, part: dict, created_ts: str, message_id: str) -> str:
        original = part.get("filename") or "invoice.pdf"
        filename = original.replace(".pdf", f"_{created_ts}.pdf")
        attachment_id = part.get("body", {}).get("attachmentId")
        if not attachment_id:
            raise ValueError(f"PDF part in message {message_id} is missing attachmentId.")

        attachment_data = self.client.get_attachment(message_id, attachment_id)
        pdf_bytes = self._decode_gmail_base64(attachment_data["data"])
        pdf_path = os.path.join(self.output_dir, filename)

        with open(pdf_path, "wb") as pdf_file:
            pdf_file.write(pdf_bytes)

        logger.info("Saved PDF: %s", pdf_path)
        return filename

    def _extract_one_message(self, message_id: str):
        message_content = self.client.get_message(message_id)
        payload = message_content.get("payload", {})
        headers = {header["name"]: header["value"] for header in payload.get("headers", [])}

        created_dt = self._message_datetime(message_content, headers)
        created_ts = created_dt.strftime("%Y_%m_%d_%H_%M_%S")

        sender_name, sender_email = parseaddr(headers.get("From", ""))
        extracted_data = {
            "message_id": message_id,
            "sender_name": sender_name,
            "sender_email": sender_email,
            "subject": headers.get("Subject"),
            "created_ts": created_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "email_body": "",
            "pdf_filenames": [],
        }

        logger.info(
            "Parsing email from %s — %s",
            sender_name or sender_email,
            extracted_data["subject"],
        )

        parts = self._walk_parts(payload.get("parts", []))
        if not parts and payload.get("body", {}).get("data"):
            parts = [payload]

        body_chunks = []
        pdf_filenames = []

        for part in parts:
            mime_type = part.get("mimeType", "")
            body = part.get("body", {})
            if "data" in body and mime_type.startswith("text/"):
                body_chunks.append(self._decode_gmail_base64(body["data"]).decode("utf-8"))
            elif mime_type == "application/pdf":
                pdf_filenames.append(self._save_pdf_attachment(part, created_ts, message_id))

        extracted_data["email_body"] = "\n".join(body_chunks)
        extracted_data["pdf_filenames"] = pdf_filenames

        if self.invoice_parser is not None:
            extracted_data["invoice"] = self.invoice_parser.parse(extracted_data, self.output_dir)

        json_path = os.path.join(self.output_dir, f"email_{created_ts}.json")
        with open(json_path, "w", encoding="utf-8") as json_file:
            json.dump(extracted_data, json_file, indent=2, ensure_ascii=False)

        logger.info("Saved email metadata: %s", json_path)
