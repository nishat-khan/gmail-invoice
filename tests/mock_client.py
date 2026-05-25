"""Mock Gmail API responses for local development and tests."""

MOCK_LIST_RESPONSE = {
    "messages": [{"id": "invoice_12345", "threadId": "thread_abc12345"}],
    "resultSizeEstimate": 1,
}

MOCK_GET_RESPONSE = {
    "id": "invoice_12345",
    "internalDate": "1747929300000",
    "payload": {
        "mimeType": "multipart/mixed",
        "headers": [
            {"name": "From", "value": "Apple Store <noreply@apple.com>"},
            {"name": "Subject", "value": "Your Receipt from Apple - INV-2026-9912"},
            {"name": "Date", "value": "Fri, 22 May 2026 10:15:00 -0700"},
        ],
        "parts": [
            {
                "mimeType": "text/plain",
                "body": {
                    "data": "T3JkZXIgdG90YWw6ICQxLDI5OS4wMC4gU2VlIGF0dGFjaGVkIFBERi4=",
                },
            },
            {
                "mimeType": "application/pdf",
                "filename": "apple_invoice_9912.pdf",
                "body": {"attachmentId": "ATTACHMENT_BLOB_ID_554433"},
            },
        ],
    },
}

MOCK_ATTACHMENT_RESPONSE = {
    "size": 45,
    "data": "JVBERi0xLjQKMSAwIG9iagogIDw8IC9UeXBlIC9DYXRhbG9nID4+CmVuZG9iag==",
}


class MockGmailClient:
    """Drop-in stand-in for GMailClient that returns canned API payloads."""

    def list_messages(self, query: str) -> dict:
        return MOCK_LIST_RESPONSE

    def get_message(self, message_id: str) -> dict:
        return MOCK_GET_RESPONSE

    def get_attachment(self, message_id: str, attachment_id: str) -> dict:
        return MOCK_ATTACHMENT_RESPONSE
