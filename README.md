# CrewAI Invoice/Contract Discrepancy Checker

A [CrewAI](https://docs.crewai.com/) crew that reads a purchase contract and a vendor invoice
(both PDFs), extracts their terms and line items, and produces a discrepancy report flagging
price mismatches, scope differences, and invoice math errors.

## How it works

Three agents run in sequence:

1. **Contract Analyst** — reads `data/purchase_terms_conditions.pdf` and extracts the
   contracted unit prices, payment terms, and tax provision.
2. **Invoice Analyst** — reads `data/sample_invoice.pdf` and extracts the billed line items,
   quantities, subtotal, tax, and total due.
3. **Discrepancy Auditor** — calls a deterministic comparison tool
   ([`document_tools.compute_discrepancies`](src/crewai_invoice_contract/tools/document_tools.py))
   that parses both documents and computes every price/amount/tax delta in Python, then writes
   the final report from those verified numbers (not from its own arithmetic).

The report is guardrail-validated to ensure it always includes: Summary, Line Item
Discrepancies, Scope Differences, Terms & Math Checks, and Recommendation.

## Setup

Requires [uv](https://docs.astral.sh/uv/) and Python 3.10–3.13.

```bash
uv sync
cp .env_example .env
# edit .env and add your OPENAI_API_KEY
```

## Run

```bash
uv run kickoff
```

The report is printed to the console and saved to `output/discrepancy_report_<timestamp>.md`
(the `output/` directory is git-ignored).

## Using your own documents

Replace the files in `data/` (keeping the same filenames), or point at a different folder:

```bash
CONTRACT_INVOICE_DATA_DIR=/path/to/folder uv run kickoff
```

The contract parser expects pricing lines in the form `- Item name: $XX.XX per unit`. The
invoice parser expects a `Description / Qty / Unit Price / Amount` line-item table. If your
documents use a different layout, adjust the regex in
[`document_tools.py`](src/crewai_invoice_contract/tools/document_tools.py) accordingly.

## Project layout

```
src/crewai_invoice_contract/
├── main.py                          # entry point (uv run kickoff)
├── tools/document_tools.py          # PDF parsing + discrepancy computation
└── crews/discrepancy_crew/
    ├── discrepancy_crew.py          # agent/task wiring, report guardrail
    └── config/
        ├── agents.yaml
        └── tasks.yaml
```
