"""Extract structured invoice fields from email metadata, body, and PDFs via an LLM."""

import base64
import json
import logging
import os
import re
from html import unescape
from typing import Any, Protocol

from anthropic import Anthropic
from dotenv import load_dotenv
from openai import OpenAI
from pypdf import PdfReader
from pypdf.errors import PdfStreamError

logger = logging.getLogger(__name__)

INVOICE_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "is_invoice": {
            "type": "boolean",
            "description": "True if this email/PDF contains a purchase receipt or invoice.",
        },
        "vendor_name": {"type": ["string", "null"]},
        "invoice_number": {"type": ["string", "null"]},
        "invoice_date": {
            "type": ["string", "null"],
            "description": "ISO date YYYY-MM-DD when known.",
        },
        "due_date": {"type": ["string", "null"]},
        "currency": {"type": ["string", "null"], "description": "ISO 4217 code, e.g. USD."},
        "subtotal": {"type": ["number", "null"]},
        "tax": {"type": ["number", "null"]},
        "total": {"type": ["number", "null"]},
        "line_items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "description": {"type": "string"},
                    "quantity": {"type": ["number", "null"]},
                    "unit_price": {"type": ["number", "null"]},
                    "amount": {"type": ["number", "null"]},
                },
                "required": ["description"],
                "additionalProperties": False,
            },
        },
        "payment_method": {"type": ["string", "null"]},
        "notes": {"type": ["string", "null"]},
    },
    "required": [
        "is_invoice",
        "vendor_name",
        "invoice_number",
        "invoice_date",
        "due_date",
        "currency",
        "subtotal",
        "tax",
        "total",
        "line_items",
        "payment_method",
        "notes",
    ],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """You extract structured invoice and receipt data from purchase emails.
Use email metadata, body text, and any attached PDF documents together.
Prefer PDF values when they conflict with the email body.
If the message is not a receipt or invoice (e.g. marketing, shipping update),
set is_invoice to false and leave financial fields null."""


class InvoiceParser(Protocol):
    def parse(self, email_data: dict[str, Any], output_dir: str) -> dict[str, Any]: ...


def _strip_html(html: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<.*?>", " ", text)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _truncate(text: str, limit: int = 12_000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n...[truncated]"


def _email_body_text(email_data: dict[str, Any]) -> str:
    body = email_data.get("email_body") or ""
    if "<" in body and ">" in body:
        body = _strip_html(body)
    return _truncate(body) or "(empty)"


def _email_metadata_text(email_data: dict[str, Any]) -> str:
    return "\n".join(
        [
            "## Email metadata",
            f"From: {email_data.get('sender_name')} <{email_data.get('sender_email')}>",
            f"Subject: {email_data.get('subject')}",
            f"Date: {email_data.get('created_ts')}",
            "",
            "## Email body",
            _email_body_text(email_data),
        ]
    )


def extract_pdf_text(pdf_path: str) -> str:
    try:
        with open(pdf_path, "rb") as pdf_file:
            reader = PdfReader(pdf_file)
            pages = [page.extract_text() or "" for page in reader.pages]
    except PdfStreamError:
        logger.warning("Could not extract text from PDF: %s", pdf_path)
        return ""
    return "\n".join(pages).strip()


def _load_llm_env(config_dir: str) -> str:
    llm_env_path = os.path.join(os.path.expanduser(config_dir), "llm.env")
    if os.path.isfile(llm_env_path):
        load_dotenv(llm_env_path)
    return llm_env_path


def _require_api_key(llm_env_path: str) -> str:
    api_key = os.environ.get("LLM_API_KEY")
    if not api_key:
        raise ValueError(
            f"LLM_API_KEY is not set. Create {llm_env_path} with your API key "
            "to enable AI invoice parsing."
        )
    return api_key


def _log_invoice_result(invoice: dict[str, Any]) -> None:
    logger.info(
        "Parsed invoice: is_invoice=%s vendor=%s total=%s",
        invoice.get("is_invoice"),
        invoice.get("vendor_name"),
        invoice.get("total"),
    )


class AnthropicInvoiceParser:
    """Parse invoices via the native Anthropic Messages API with PDF document blocks."""

    def __init__(self, api_key: str, *, model: str = "claude-sonnet-4-6"):
        self.client = Anthropic(api_key=api_key)
        self.model = model

    def _build_content(self, email_data: dict[str, Any], output_dir: str) -> list[dict[str, Any]]:
        content: list[dict[str, Any]] = [
            {"type": "text", "text": _email_metadata_text(email_data)},
        ]

        for filename in email_data.get("pdf_filenames") or []:
            pdf_path = os.path.join(output_dir, filename)
            if not os.path.isfile(pdf_path):
                logger.warning("PDF not found for parsing: %s", pdf_path)
                continue
            with open(pdf_path, "rb") as pdf_file:
                pdf_data = base64.standard_b64encode(pdf_file.read()).decode("utf-8")
            content.append(
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": pdf_data,
                    },
                }
            )
            content.append({"type": "text", "text": f"Above is the attached PDF: {filename}"})

        return content

    def parse(self, email_data: dict[str, Any], output_dir: str) -> dict[str, Any]:
        logger.info("Parsing invoice with Anthropic %s", self.model)

        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": self._build_content(email_data, output_dir)}],
            output_config={
                "format": {
                    "type": "json_schema",
                    "schema": INVOICE_JSON_SCHEMA,
                }
            },
        )

        if not response.content:
            raise ValueError("LLM returned empty invoice response.")

        text_block = next((block for block in response.content if block.type == "text"), None)
        if text_block is None or not text_block.text:
            raise ValueError("LLM returned no text in invoice response.")

        invoice = json.loads(text_block.text)
        _log_invoice_result(invoice)
        return invoice


class OpenAIInvoiceParser:
    """Parse invoices using any OpenAI-compatible chat completions API."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str | None = None,
        model: str = "gpt-4o-mini",
    ):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    def _build_user_prompt(self, email_data: dict[str, Any], output_dir: str) -> str:
        pdf_sections: list[str] = []
        for filename in email_data.get("pdf_filenames") or []:
            pdf_path = os.path.join(output_dir, filename)
            if not os.path.isfile(pdf_path):
                logger.warning("PDF not found for parsing: %s", pdf_path)
                continue
            pdf_text = extract_pdf_text(pdf_path)
            if pdf_text:
                pdf_sections.append(f"--- PDF: {filename} ---\n{_truncate(pdf_text)}")

        parts = [_email_metadata_text(email_data)]
        if pdf_sections:
            parts.extend(["", "## PDF attachment text", *pdf_sections])
        else:
            parts.extend(["", "## PDF attachment text", "(none)"])

        return "\n".join(parts)

    def parse(self, email_data: dict[str, Any], output_dir: str) -> dict[str, Any]:
        user_prompt = self._build_user_prompt(email_data, output_dir)
        logger.info("Parsing invoice with OpenAI-compatible %s", self.model)

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "invoice",
                    "strict": True,
                    "schema": INVOICE_JSON_SCHEMA,
                },
            },
        )

        content = response.choices[0].message.content
        if not content:
            raise ValueError("LLM returned empty invoice response.")

        invoice = json.loads(content)
        _log_invoice_result(invoice)
        return invoice


# Backward-compatible alias
LLMInvoiceParser = OpenAIInvoiceParser


def create_invoice_parser(config_dir: str) -> InvoiceParser:
    """Load llm.env from config_dir and return the configured invoice parser."""
    llm_env_path = _load_llm_env(config_dir)
    api_key = _require_api_key(llm_env_path)

    provider = os.environ.get("LLM_PROVIDER", "anthropic").lower()
    model = os.environ.get("LLM_MODEL")

    if provider == "anthropic":
        return AnthropicInvoiceParser(
            api_key=api_key,
            model=model or "claude-sonnet-4-6",
        )

    return OpenAIInvoiceParser(
        api_key=api_key,
        base_url=os.environ.get("LLM_BASE_URL"),
        model=model or "gpt-4o-mini",
    )
