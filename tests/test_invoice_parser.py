"""Tests for LLM invoice parsing."""

import json
from unittest.mock import MagicMock, patch

from gmail_invoice.invoice_parser import (
    AnthropicInvoiceParser,
    OpenAIInvoiceParser,
    _strip_html,
    create_invoice_parser,
    extract_pdf_text,
)

MOCK_INVOICE = {
    "is_invoice": True,
    "vendor_name": "Apple",
    "invoice_number": "INV-2026-9912",
    "invoice_date": "2026-05-22",
    "due_date": None,
    "currency": "USD",
    "subtotal": 1199.0,
    "tax": 100.0,
    "total": 1299.0,
    "line_items": [
        {"description": "MacBook", "quantity": 1, "unit_price": 1199.0, "amount": 1199.0}
    ],
    "payment_method": "Credit Card",
    "notes": None,
}

EMAIL_DATA = {
    "sender_name": "Apple Store",
    "sender_email": "noreply@apple.com",
    "subject": "Your Receipt from Apple",
    "created_ts": "2026-05-22 10:15:00",
    "email_body": "Order total: $1,299.00. See attached PDF.",
    "pdf_filenames": [],
}


class TestHelpers:
    def test_strip_html_removes_tags(self):
        html = "<p>Total: <strong>$19.99</strong></p>"
        assert _strip_html(html) == "Total: $19.99"


def test_extract_pdf_text_reads_mock_pdf(tmp_path):
    pdf_bytes = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj"
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(pdf_bytes)

    text = extract_pdf_text(str(pdf_path))
    assert text == ""


def test_create_invoice_parser_uses_anthropic_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)

    (tmp_path / "llm.env").write_text(
        "LLM_API_KEY=test-key-from-file\nLLM_MODEL=claude-test\n",
        encoding="utf-8",
    )

    with patch("gmail_invoice.invoice_parser.Anthropic") as mock_anthropic_cls:
        parser = create_invoice_parser(str(tmp_path))

    assert isinstance(parser, AnthropicInvoiceParser)
    assert parser.model == "claude-test"
    mock_anthropic_cls.assert_called_once_with(api_key="test-key-from-file")


def test_create_invoice_parser_uses_openai_when_configured(tmp_path, monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)

    (tmp_path / "llm.env").write_text(
        "LLM_PROVIDER=openai\nLLM_API_KEY=test-key\nLLM_MODEL=gpt-test\n",
        encoding="utf-8",
    )

    with patch("gmail_invoice.invoice_parser.OpenAI") as mock_openai_cls:
        parser = create_invoice_parser(str(tmp_path))

    assert isinstance(parser, OpenAIInvoiceParser)
    assert parser.model == "gpt-test"
    mock_openai_cls.assert_called_once_with(api_key="test-key", base_url=None)


def test_openai_invoice_parser_returns_structured_invoice(tmp_path):
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content=json.dumps(MOCK_INVOICE)))]

    with patch("gmail_invoice.invoice_parser.OpenAI") as mock_openai_cls:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_cls.return_value = mock_client

        parser = OpenAIInvoiceParser(api_key="test-key", model="gpt-4o-mini")
        result = parser.parse(EMAIL_DATA, str(tmp_path))

    assert result == MOCK_INVOICE
    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert call_kwargs["response_format"]["type"] == "json_schema"


def test_anthropic_invoice_parser_returns_structured_invoice(tmp_path):
    mock_text_block = MagicMock(type="text", text=json.dumps(MOCK_INVOICE))
    mock_response = MagicMock(content=[mock_text_block])

    with patch("gmail_invoice.invoice_parser.Anthropic") as mock_anthropic_cls:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic_cls.return_value = mock_client

        parser = AnthropicInvoiceParser(api_key="test-key", model="claude-sonnet-4-6")
        result = parser.parse(EMAIL_DATA, str(tmp_path))

    assert result == MOCK_INVOICE
    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert call_kwargs["output_config"]["format"]["type"] == "json_schema"
