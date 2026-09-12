"""Message evidence extraction for Phase 3: Message & Image Evidence Resolution."""

import re
from datetime import date
from decimal import Decimal
from typing import Any

from data.models import Message
from evidence.confidence import (
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    CONFIDENCE_MEDIUM,
    CONFIDENCE_UNTRUSTED,
    validate_confidence,
)
from evidence.models import FinancialEvidence
from utils.dates import parse_date
from utils.money import parse_money

# Indonesian & English month name map for date parsing
MONTH_MAP = {
    "january": 1, "januari": 1, "jan": 1,
    "february": 2, "februari": 2, "feb": 2,
    "march": 3, "maret": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5, "mei": 5,
    "june": 6, "juni": 6, "jun": 6,
    "july": 7, "juli": 7, "jul": 7,
    "august": 8, "agustus": 8, "aug": 8,
    "september": 9, "sep": 9,
    "october": 10, "oktober": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "desember": 12, "dec": 12,
}

CURRENCY_REGEX = re.compile(
    r"\b(IDR|INR|USD|EUR|ZAR|GBP|JPY|CAD|AUD)\s*([0-9,]+(?:\.[0-9]+)?)\b",
    re.IGNORECASE,
)
PERCENT_REGEX = re.compile(r"(\d+(?:\.\d+)?)\s*%", re.IGNORECASE)
ISO_DATE_REGEX = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
TEXT_DATE_REGEX = re.compile(
    r"\b(\d{1,2})\s+([a-zA-Z]+)\s+(\d{4})\b",
    re.IGNORECASE,
)


def _extract_dates_from_text(text: str) -> list[date]:
    """Extract all valid dates (ISO and textual) from text in chronological order."""
    dates: list[date] = []
    # 1. ISO dates
    for m in ISO_DATE_REGEX.finditer(text):
        d = parse_date(m.group(1))
        if d and d not in dates:
            dates.append(d)

    # 2. Textual dates (e.g. 24 July 2026, 15 Agustus 2025)
    for m in TEXT_DATE_REGEX.finditer(text):
        day_str, month_name, year_str = m.group(1), m.group(2).lower(), m.group(3)
        month = MONTH_MAP.get(month_name)
        if month:
            try:
                d = date(int(year_str), month, int(day_str))
                if d not in dates:
                    dates.append(d)
            except ValueError:
                pass
    return dates


class MessageEvidenceExtractor:
    """Extracts structured, traceable financial facts from unstructured messages.

    Operates deterministically. Treats all message text as untrusted data.
    Embedded prompt injection or meta-instructions are ignored.
    """

    def extract(self, message: Message) -> list[FinancialEvidence]:
        """Convert a single Message into zero or more FinancialEvidence records."""
        text = message.message_text
        if not text or not text.strip():
            return []

        user_id = message.user_id
        msg_id = message.message_id
        req_id = message.request_id
        ev_id = message.related_event_id

        facts: list[FinancialEvidence] = []
        fact_idx = 0

        def add_evidence(
            fact_type: str,
            value: str | None = None,
            numeric_value: Decimal | None = None,
            currency: str | None = None,
            effective_date: date | None = None,
            confidence: Decimal = CONFIDENCE_HIGH,
        ) -> None:
            nonlocal fact_idx
            fact_idx += 1
            conf = validate_confidence(confidence)
            facts.append(
                FinancialEvidence(
                    evidence_id=f"ev_msg_{msg_id}_{fact_idx:02d}",
                    user_id=user_id,
                    source_type="message",
                    source_id=msg_id,
                    event_id=ev_id,
                    request_id=req_id,
                    fact_type=fact_type,
                    value=value,
                    numeric_value=numeric_value,
                    currency=currency,
                    effective_date=effective_date,
                    confidence=conf,
                    source_text=text,
                    source_path=None,
                )
            )

        # Pre-parse amounts and dates
        currencies_found: list[tuple[str, Decimal]] = []
        for match in CURRENCY_REGEX.finditer(text):
            cur = match.group(1).upper()
            val_str = match.group(2).replace(",", "")
            amt = parse_money(val_str)
            if amt is not None:
                currencies_found.append((cur, amt))

        dates_found = _extract_dates_from_text(text)
        primary_date = dates_found[0] if dates_found else None

        # 1. Check for untrusted / advance-fee prize scam messages
        if re.search(r"pay the (?:release|processing) charge|bayar biaya (?:pencairan|pemrosesan)", text, re.IGNORECASE):
            add_evidence(
                fact_type="untrusted_solicitation",
                value="Advance fee / scam solicitation detected. Untrusted evidence.",
                confidence=CONFIDENCE_UNTRUSTED,
            )
            return facts

        # 2. Employment termination / seasonal contract ended
        if re.search(r"seasonal contract has ended|kontrak musiman.*berakhir", text, re.IGNORECASE):
            add_evidence(
                fact_type="income_seasonal_contract_ended",
                value="Seasonal contract ended; no recurring off-season income",
                confidence=CONFIDENCE_HIGH,
            )
        elif re.search(r"employment has ended|hubungan kerja.*berakhir|terminated", text, re.IGNORECASE):
            add_evidence(
                fact_type="income_employment_ended",
                value="Employment ended; no regular salary scheduled after final settlement",
                confidence=CONFIDENCE_HIGH,
            )

        # 3. Rent changes (percentage increase or amount)
        if re.search(r"rent|sewa|lease", text, re.IGNORECASE):
            pct_m = PERCENT_REGEX.search(text)
            if pct_m:
                pct = Decimal(pct_m.group(1))
                add_evidence(
                    fact_type="expense_rent_increase",
                    value=f"Rent increase of {pct}%",
                    numeric_value=pct,
                    confidence=CONFIDENCE_HIGH,
                )
            elif currencies_found:
                cur, amt = currencies_found[0]
                add_evidence(
                    fact_type="expense_rent_amount",
                    value=f"Rent amount {cur} {amt}",
                    numeric_value=amt,
                    currency=cur,
                    confidence=CONFIDENCE_HIGH,
                )

        # 4. Salary / Payroll adjustments
        if re.search(r"salary|gaji|payroll|penggajian|pay\b", text, re.IGNORECASE):
            # Check for bonus pending review
            if re.search(r"bonus.*(?:menunggu|subject to|pending)", text, re.IGNORECASE):
                add_evidence(
                    fact_type="income_bonus_pending",
                    value="Quarterly bonus pending performance review; amount and date unapproved",
                    confidence=CONFIDENCE_HIGH,
                )
            # Check for salary raise / reduction / confirmation with amount
            elif currencies_found:
                cur, amt = currencies_found[0]
                if re.search(r"reduced to|temporary monthly pay|potongan|berkurang", text, re.IGNORECASE):
                    add_evidence(
                        fact_type="income_salary_reduction",
                        value=f"Reduced salary {cur} {amt}",
                        numeric_value=amt,
                        currency=cur,
                        effective_date=primary_date,
                        confidence=CONFIDENCE_HIGH,
                    )
                elif re.search(r"naik menjadi|increase|raise|first salary|resumes|confirmed", text, re.IGNORECASE):
                    add_evidence(
                        fact_type="income_salary_update",
                        value=f"Confirmed salary {cur} {amt}",
                        numeric_value=amt,
                        currency=cur,
                        effective_date=primary_date,
                        confidence=CONFIDENCE_HIGH,
                    )
                else:
                    add_evidence(
                        fact_type="income_salary_update",
                        value=f"Salary {cur} {amt}",
                        numeric_value=amt,
                        currency=cur,
                        effective_date=primary_date,
                        confidence=CONFIDENCE_HIGH,
                    )
            # Confirmed salary date change without explicit amount
            elif primary_date and re.search(r"now expected on|replaces the previous date|resumes on|confirmed.*date", text, re.IGNORECASE):
                add_evidence(
                    fact_type="date_salary_reschedule",
                    value=f"Salary payment rescheduled to {primary_date}",
                    effective_date=primary_date,
                    confidence=CONFIDENCE_HIGH,
                )
            elif re.search(r"sudah dikonfirmasi|slip gaji berikutnya", text, re.IGNORECASE):
                add_evidence(
                    fact_type="income_salary_confirmed",
                    value="Regular salary confirmed for next payroll",
                    confidence=CONFIDENCE_HIGH,
                )

        # 5. Service Provider / Invoices
        if re.search(r"invoice|faktur|client approved", text, re.IGNORECASE):
            if currencies_found:
                cur, amt = currencies_found[0]
                add_evidence(
                    fact_type="income_invoice_approved",
                    value=f"Client approved invoice {cur} {amt}",
                    numeric_value=amt,
                    currency=cur,
                    effective_date=primary_date,
                    confidence=CONFIDENCE_HIGH,
                )
            else:
                add_evidence(
                    fact_type="income_invoice_approved",
                    value="Invoice approved by client",
                    effective_date=primary_date,
                    confidence=CONFIDENCE_HIGH,
                )

        # 6. Gig payouts pending (QuickCrew, TaskLoop)
        if re.search(r"payout is still pending|tertunda|earnings.*can change", text, re.IGNORECASE):
            add_evidence(
                fact_type="income_gig_payout_pending",
                value="Gig payout pending; amounts subject to final settlement",
                confidence=CONFIDENCE_HIGH,
            )

        # 7. Failed debit attempt retry
        if re.search(r"previous debit attempt failed|debit.*gagal|bill is still open", text, re.IGNORECASE):
            add_evidence(
                fact_type="expense_debit_retry",
                value="Previous debit failed; bill still outstanding and debit will retry",
                confidence=CONFIDENCE_HIGH,
            )

        # 8. Refunds
        if re.search(r"refund|pengembalian dana", text, re.IGNORECASE):
            add_evidence(
                fact_type="refund_pending",
                value="Refund initiated but pending; not yet settled in account",
                confidence=CONFIDENCE_HIGH,
            )

        # 9. Internal transfers between user accounts
        if re.search(r"transfer between your (?:two )?accounts|transfer antar rekening|transfer antara dua rekening", text, re.IGNORECASE):
            add_evidence(
                fact_type="internal_transfer",
                value="Internal transfer between user's own accounts; not an external cash flow",
                confidence=CONFIDENCE_HIGH,
            )

        # 10. Portfolio market value / investments
        if re.search(r"portfolio.*market value|displayed (?:market )?value|nilai investasi yang ditampilkan", text, re.IGNORECASE):
            add_evidence(
                fact_type="portfolio_unrealized",
                value="Market value fluctuation; no units sold, no realized cash",
                confidence=CONFIDENCE_HIGH,
            )
        elif re.search(r"proceeds from your investment sale have settled", text, re.IGNORECASE):
            add_evidence(
                fact_type="investment_settled",
                value="Investment sale settled into cash account",
                confidence=CONFIDENCE_HIGH,
            )

        # 11. Prize claims (settled vs processing)
        if re.search(r"prize proceeds have reached your account", text, re.IGNORECASE):
            add_evidence(
                fact_type="prize_settled",
                value="Prize proceeds settled after withholding; claim closed, no further payments",
                confidence=CONFIDENCE_HIGH,
            )
        elif re.search(r"prize claim.*in payment processing|klaim hadiah.*proses pembayaran", text, re.IGNORECASE):
            add_evidence(
                fact_type="prize_pending",
                value="Prize claim verified but processing; funds have not cleared",
                confidence=CONFIDENCE_HIGH,
            )

        # 12. Expense reimbursements (one-off)
        if re.search(r"reimbursement for your earlier work expense|penggantian atas biaya kerja", text, re.IGNORECASE):
            add_evidence(
                fact_type="reimbursement_one_off",
                value="One-off work expense reimbursement; not regular salary",
                confidence=CONFIDENCE_HIGH,
            )

        # 13. Disputed card charges
        if re.search(r"extra card charge is still being investigated|dispute is open|tagihan kartu.*penyelidikan|sengketa masih terbuka", text, re.IGNORECASE):
            add_evidence(
                fact_type="dispute_open",
                value="Card charge dispute active; reversal has not posted",
                confidence=CONFIDENCE_HIGH,
            )

        # 14. Separate card minimum payment obligations
        if re.search(r"minimum payments due on two separate card accounts|minimums belong to separate accounts", text, re.IGNORECASE):
            add_evidence(
                fact_type="expense_separate_card_obligations",
                value="Separate card minimum payment obligations; payments do not cross-cover",
                confidence=CONFIDENCE_HIGH,
            )

        # 15. Foreign currency settlement notices
        if re.search(r"bill was charged in a foreign currency|settlement-date rate|final home-currency amount", text, re.IGNORECASE):
            add_evidence(
                fact_type="foreign_currency_settlement_notice",
                value="Foreign currency charge pending final home-currency settlement",
                confidence=CONFIDENCE_HIGH,
            )

        # 14. Fallback: If currency amounts were found but no fact captured yet
        if not facts and currencies_found:
            for cur, amt in currencies_found:
                add_evidence(
                    fact_type="amount_extracted",
                    value=f"Amount {cur} {amt}",
                    numeric_value=amt,
                    currency=cur,
                    effective_date=primary_date,
                    confidence=CONFIDENCE_MEDIUM,
                )

        # 15. Fallback: If dates were found but no fact captured yet
        if not facts and dates_found:
            for d in dates_found:
                add_evidence(
                    fact_type="date_fact",
                    value=f"Date noted: {d}",
                    effective_date=d,
                    confidence=CONFIDENCE_MEDIUM,
                )

        # Fallback for receipt references (e.g. "The receipt has the final INR amount")
        if not facts and re.search(r"receipt has the final|receipt contains the final", text, re.IGNORECASE):
            add_evidence(
                fact_type="receipt_amount_reference",
                value="Final payment confirmed via receipt",
                effective_date=primary_date,
                confidence=CONFIDENCE_MEDIUM,
            )

        return facts
