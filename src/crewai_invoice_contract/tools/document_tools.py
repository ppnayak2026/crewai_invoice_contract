"""Tools for reading the contract and invoice PDFs and diffing their line items.

Price and tax math is computed here, not by the agents, so the discrepancy
report quotes real figures instead of LLM arithmetic.
"""

import os
import re
from functools import lru_cache
from pathlib import Path

from crewai.tools import tool
from pypdf import PdfReader

DATA_DIR = Path(os.getenv("CONTRACT_INVOICE_DATA_DIR", Path(__file__).resolve().parents[3] / "data"))
CONTRACT_FILE = DATA_DIR / "purchase_terms_conditions.pdf"
INVOICE_FILE = DATA_DIR / "sample_invoice.pdf"


@lru_cache(maxsize=None)
def _extract_text(path: Path) -> str:
    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _parse_contract(text: str) -> dict:
    pricing = {
        name.strip(): float(price.replace(",", ""))
        for name, price in re.findall(r"-\s*(.+?):\s*\$([\d,]+\.\d{2})\s*per unit", text)
    }
    payment_terms = re.search(r"Payment terms:\s*(.+?)\.", text)
    payment_method = re.search(r"Payment method:\s*(.+?)\.", text)
    invoice_ref = re.search(r"Invoice No\.\s*([A-Za-z0-9-]+)", text)
    return {
        "pricing": pricing,
        "payment_terms": payment_terms.group(1).strip() if payment_terms else None,
        "payment_method": payment_method.group(1).strip() if payment_method else None,
        "invoice_reference": invoice_ref.group(1).strip() if invoice_ref else None,
    }


def _parse_invoice(text: str) -> dict:
    items = [
        {
            "description": desc.strip(),
            "qty": int(qty),
            "unit_price": float(unit_price.replace(",", "")),
            "amount": float(amount.replace(",", "")),
        }
        for desc, qty, unit_price, amount in re.findall(
            r"([A-Za-z][A-Za-z0-9 ,/&'-]+?)\s*\n\s*(\d+)\s*\n\s*\$([\d,]+\.\d{2})\s*\n\s*\$([\d,]+\.\d{2})",
            text,
        )
    ]
    subtotal = re.search(r"Subtotal\s*\n\s*\$([\d,]+\.\d{2})", text)
    tax = re.search(r"Sales Tax \(([\d.]+)%\)\s*\n\s*\$([\d,]+\.\d{2})", text)
    total = re.search(r"Total Due\s*\n\s*\$([\d,]+\.\d{2})", text)
    payment_terms = re.search(r"Payment Terms:\s*(.+)", text)
    invoice_number = re.search(r"Invoice #:\s*([A-Za-z0-9-]+)", text)
    return {
        "items": items,
        "subtotal": float(subtotal.group(1).replace(",", "")) if subtotal else None,
        "tax_rate_pct": float(tax.group(1)) if tax else None,
        "tax_amount": float(tax.group(2).replace(",", "")) if tax else None,
        "total_due": float(total.group(1).replace(",", "")) if total else None,
        "payment_terms": payment_terms.group(1).strip() if payment_terms else None,
        "invoice_number": invoice_number.group(1).strip() if invoice_number else None,
    }


@tool("Read Contract PDF")
def read_contract_text() -> str:
    """Return the full raw text of the purchase terms and conditions contract PDF."""
    return _extract_text(CONTRACT_FILE)


@tool("Read Invoice PDF")
def read_invoice_text() -> str:
    """Return the full raw text of the sample invoice PDF."""
    return _extract_text(INVOICE_FILE)


@tool("Compute Contract vs Invoice Discrepancies")
def compute_discrepancies() -> str:
    """Parse the contract and invoice PDFs and compute every price, quantity,
    scope, tax, and payment-term discrepancy between them with exact numbers.
    Use this instead of doing the comparison math yourself."""
    contract = _parse_contract(_extract_text(CONTRACT_FILE))
    invoice = _parse_invoice(_extract_text(INVOICE_FILE))

    lines = []
    lines.append(f"Contract invoice reference: {contract['invoice_reference']}")
    lines.append(f"Invoice number on invoice: {invoice['invoice_number']}")
    ref_match = contract["invoice_reference"] == invoice["invoice_number"]
    lines.append(f"Invoice reference match: {'YES' if ref_match else 'NO - MISMATCH'}")
    lines.append("")

    lines.append(f"Contract payment terms: {contract['payment_terms']}")
    lines.append(f"Invoice payment terms: {invoice['payment_terms']}")
    terms_match = invoice["payment_terms"] and invoice["payment_terms"] in (contract["payment_terms"] or "")
    lines.append(f"Payment terms match: {'YES' if terms_match else 'NO - MISMATCH'}")
    lines.append("")

    lines.append("LINE ITEM COMPARISON (contract unit price vs invoice unit price):")
    contract_items = set(contract["pricing"])
    invoice_items = {i["description"] for i in invoice["items"]}

    for item in invoice["items"]:
        desc = item["description"]
        contract_price = contract["pricing"].get(desc)
        if contract_price is None:
            lines.append(
                f"- {desc}: NOT FOUND IN CONTRACT (invoiced at ${item['unit_price']:.2f}/unit, "
                f"qty {item['qty']}, amount ${item['amount']:.2f}) -> flag as out-of-scope charge"
            )
            continue
        expected_amount = round(contract_price * item["qty"], 2)
        price_delta = round(item["unit_price"] - contract_price, 2)
        amount_delta = round(item["amount"] - expected_amount, 2)
        status = "MATCH" if price_delta == 0 else ("OVERCHARGE" if price_delta > 0 else "UNDERCHARGE")
        lines.append(
            f"- {desc}: contract ${contract_price:.2f}/unit vs invoice ${item['unit_price']:.2f}/unit "
            f"(delta ${price_delta:+.2f}/unit, {status}) | qty {item['qty']} | "
            f"expected amount ${expected_amount:.2f} vs invoiced ${item['amount']:.2f} "
            f"(amount delta ${amount_delta:+.2f})"
        )

    for desc in contract_items - invoice_items:
        lines.append(f"- {desc}: IN CONTRACT BUT MISSING FROM INVOICE (contract price ${contract['pricing'][desc]:.2f}/unit)")

    lines.append("")
    lines.append("INVOICE MATH CHECK:")
    computed_subtotal = round(sum(i["amount"] for i in invoice["items"]), 2)
    lines.append(f"- Sum of line item amounts: ${computed_subtotal:.2f} vs stated subtotal ${invoice['subtotal']:.2f} "
                  f"({'OK' if computed_subtotal == invoice['subtotal'] else 'MISMATCH'})")
    if invoice["subtotal"] is not None and invoice["tax_rate_pct"] is not None:
        computed_tax = round(invoice["subtotal"] * invoice["tax_rate_pct"] / 100, 2)
        lines.append(f"- Tax at {invoice['tax_rate_pct']}% of subtotal: ${computed_tax:.2f} vs stated tax ${invoice['tax_amount']:.2f} "
                      f"({'OK' if abs(computed_tax - invoice['tax_amount']) < 0.02 else 'MISMATCH'})")
        computed_total = round(invoice["subtotal"] + invoice["tax_amount"], 2)
        lines.append(f"- Subtotal + tax: ${computed_total:.2f} vs stated total due ${invoice['total_due']:.2f} "
                      f"({'OK' if computed_total == invoice['total_due'] else 'MISMATCH'})")
    lines.append(
        "- Contract note on taxes: \"Applicable sales tax shall be added and paid by the Buyer.\" "
        "The contract does not fix a tax rate, so the 8.25% rate itself cannot be flagged as a discrepancy, "
        "only whether the tax math on the invoice is internally consistent."
    )

    total_overbilled = round(
        sum(
            item["amount"] - round(contract["pricing"][item["description"]] * item["qty"], 2)
            for item in invoice["items"]
            if item["description"] in contract["pricing"]
        ),
        2,
    )
    lines.append("")
    lines.append(f"NET LINE-ITEM AMOUNT DELTA (invoice minus contract-expected, before tax): ${total_overbilled:+.2f}")

    return "\n".join(lines)
