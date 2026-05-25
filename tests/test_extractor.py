"""Smoke tests for invoice extraction."""

import json
from datetime import date

from gmail_invoice.gmail_extractor import GMailInvoiceExtractor
from tests.mock_client import MockGmailClient


class MockInvoiceParser:
    def parse(self, email_data, output_dir):
        return {
            "is_invoice": True,
            "vendor_name": "Apple",
            "invoice_number": "INV-2026-9912",
            "invoice_date": "2026-05-22",
            "due_date": None,
            "currency": "USD",
            "subtotal": 1199.0,
            "tax": 100.0,
            "total": 1299.0,
            "line_items": [],
            "payment_method": None,
            "notes": None,
        }


def test_extract_purchases_writes_json_and_pdf(tmp_path):
    extractor = GMailInvoiceExtractor(
        MockGmailClient(),
        date(2026, 5, 22),
        output_dir=str(tmp_path),
        invoice_parser=MockInvoiceParser(),
    )
    extractor.extract_purchases_for_date()

    json_files = list(tmp_path.glob("email_*.json"))
    pdf_files = list(tmp_path.glob("*.pdf"))

    assert len(json_files) == 1
    assert len(pdf_files) == 1

    data = json.loads(json_files[0].read_text(encoding="utf-8"))
    assert data["invoice"]["is_invoice"] is True
    assert data["invoice"]["total"] == 1299.0
