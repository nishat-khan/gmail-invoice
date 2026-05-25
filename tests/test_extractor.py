"""Smoke tests for invoice extraction."""

from datetime import date

from gmail_invoice.gmail_extractor import GMailInvoiceExtractor
from tests.mock_client import MockGmailClient


def test_extract_purchases_writes_json_and_pdf(tmp_path):
    extractor = GMailInvoiceExtractor(
        MockGmailClient(),
        date(2026, 5, 22),
        output_dir=str(tmp_path),
    )
    extractor.extract_purchases_for_date()

    json_files = list(tmp_path.glob("email_*.json"))
    pdf_files = list(tmp_path.glob("*.pdf"))

    assert len(json_files) == 1
    assert len(pdf_files) == 1
