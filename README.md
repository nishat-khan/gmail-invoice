# gmail-invoice

Download purchase invoice emails and PDF attachments from Gmail (read-only).

For a given date, the tool searches Gmail's **Purchases** category, saves each email as JSON, downloads any PDF attachments, and uses an LLM to extract structured invoice fields into the same JSON file.

## Install

```bash
pip install gmail-invoice
```

## Setup

1. Create a [Google Cloud OAuth desktop client](https://console.cloud.google.com/) with the Gmail API enabled and download `credentials.json`.

2. Create a config folder **outside this project** (so credentials are not in your repo or workspace):

   ```bash
   mkdir -p ~/.config/gmail-invoice
   mv ~/Downloads/credentials.json ~/.config/gmail-invoice/
   ```

3. Copy the sample env file, paste your config folder path, and save as `.env`:

   ```bash
   cp .env.example .env
   ```

   ```env
   # .env — do not commit; do not share with AI assistants
   CONFIG_DIR=/Users/you/.config/gmail-invoice

   # Optional: where to write invoice folders (default: ./invoices_YYYY_MM_DD)
   # GMAIL_INVOICE_OUTPUT_DIR=./invoices_2026_05_24
   ```

   Replace `/Users/you` with your username (or use the full expanded path to `~/.config/gmail-invoice`). On first run, OAuth will create `token.json` in that config folder.

4. Add LLM settings in your config folder for invoice parsing:

   **Anthropic (default)** — sends PDFs natively and uses structured outputs:

   ```bash
   cat > ~/.config/gmail-invoice/llm.env <<'EOF'
   LLM_PROVIDER=anthropic
   LLM_API_KEY=sk-ant-api03-your-key-here
   LLM_MODEL=claude-sonnet-4-6
   EOF
   ```

   **OpenAI-compatible** (OpenAI, Groq, Together, Ollama shim, etc.):

   ```bash
   cat > ~/.config/gmail-invoice/llm.env <<'EOF'
   LLM_PROVIDER=openai
   LLM_API_KEY=sk-your-key-here
   LLM_BASE_URL=https://api.openai.com/v1
   LLM_MODEL=gpt-4o-mini
   EOF
   ```

## Usage

```bash
# Today's purchase emails → ./invoices_YYYY_MM_DD/
gmail-invoice

# Specific date
gmail-invoice --date 2026-05-04

# Download only — skip LLM parsing
gmail-invoice --date 2026-05-04 --skip-parse
```

Equivalent module invocation:

```bash
python -m gmail_invoice --date 2026-05-04
```

## Output

Each run creates a folder (default: `invoices_YYYY_MM_DD/` in the current directory) containing:

- `email_YYYY_MM_DD_HH_MM_SS.json` — sender, subject, body text, and parsed `invoice` object
- `*.pdf` — invoice attachments with a timestamp suffix

Example `invoice` fields in the JSON:

```json
{
  "is_invoice": true,
  "vendor_name": "Apple",
  "invoice_number": "INV-2026-9912",
  "invoice_date": "2026-05-22",
  "currency": "USD",
  "subtotal": 1199.0,
  "tax": 100.0,
  "total": 1299.0,
  "line_items": [{"description": "MacBook", "quantity": 1, "unit_price": 1199.0, "amount": 1199.0}]
}
```

## Development

```bash
git clone https://github.com/nishat-khan/gmail-invoice.git
cd gmail-invoice
pip install -e ".[dev]"
pytest
ruff check .
gmail-invoice --date 2026-05-04
```

## License

MIT
