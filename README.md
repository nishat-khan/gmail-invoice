# gmail-invoice

Download purchase invoice emails and PDF attachments from Gmail (read-only).

For a given date, the tool searches Gmail's **Purchases** category, saves each email as JSON, and downloads any PDF attachments into a dated folder in your current working directory.

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

## Usage

```bash
# Today's purchase emails → ./invoices_YYYY_MM_DD/
gmail-invoice

# Specific date
gmail-invoice --date 2026-05-04
```

Equivalent module invocation:

```bash
python -m gmail_invoice --date 2026-05-04
```

## Output

Each run creates a folder (default: `invoices_YYYY_MM_DD/` in the current directory) containing:

- `email_YYYY_MM_DD_HH_MM_SS.json` — sender, subject, body text
- `*.pdf` — invoice attachments with a timestamp suffix

## Development

```bash
git clone https://github.com/nish/gmail-invoice.git
cd gmail-invoice
pip install -e ".[dev]"
pytest
ruff check .
gmail-invoice --date 2026-05-04
```

## License

MIT
