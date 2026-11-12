"""Deterministic payment-to-invoice matching for normalized records."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum

from .models import CustomerOrderRecord, InvoiceRecord, PaymentRecord


class MatchStatus(StrEnum):
    """Client-readable reconciliation status values."""

    MATCHED = "matched"
    UNMATCHED_INVOICE = "unmatched_invoice"
    UNMATCHED_PAYMENT = "unmatched_payment"
    AMOUNT_MISMATCH = "amount_mismatch"
    CURRENCY_MISMATCH = "currency_mismatch"
    AMBIGUOUS_REFERENCE = "ambiguous_reference"


class AmbiguousReferenceReason(StrEnum):
    """Stable reasons for references that cannot be matched one-to-one."""

    DUPLICATE_INVOICE_REFERENCE = "duplicate_invoice_reference"
    DUPLICATE_PAYMENT_REFERENCE = "duplicate_payment_reference"
    DUPLICATE_INVOICE_AND_PAYMENT_REFERENCE = "duplicate_invoice_and_payment_reference"


@dataclass(frozen=True, slots=True)
class MatchedPair:
    """Invoice and payment records that satisfy all Phase 2 matching rules."""

    reference: str
    invoice: InvoiceRecord
    payment: PaymentRecord
    status: MatchStatus = field(default=MatchStatus.MATCHED, init=False)


@dataclass(frozen=True, slots=True)
class UnmatchedInvoice:
    """Invoice record without a corresponding payment reference."""

    reference: str
    invoice: InvoiceRecord
    status: MatchStatus = field(default=MatchStatus.UNMATCHED_INVOICE, init=False)


@dataclass(frozen=True, slots=True)
class UnmatchedPayment:
    """Payment record without a corresponding invoice reference."""

    reference: str
    payment: PaymentRecord
    status: MatchStatus = field(default=MatchStatus.UNMATCHED_PAYMENT, init=False)


@dataclass(frozen=True, slots=True)
class AmountMismatch:
    """Invoice and payment share a reference and currency but not an amount."""

    reference: str
    invoice: InvoiceRecord
    payment: PaymentRecord
    status: MatchStatus = field(default=MatchStatus.AMOUNT_MISMATCH, init=False)


@dataclass(frozen=True, slots=True)
class CurrencyMismatch:
    """Invoice and payment share a reference but not a currency."""

    reference: str
    invoice: InvoiceRecord
    payment: PaymentRecord
    status: MatchStatus = field(default=MatchStatus.CURRENCY_MISMATCH, init=False)


@dataclass(frozen=True, slots=True)
class AmbiguousReference:
    """Duplicate invoice or payment references that need manual review."""

    reference: str
    invoices: tuple[InvoiceRecord, ...]
    payments: tuple[PaymentRecord, ...]
    reason: AmbiguousReferenceReason
    status: MatchStatus = field(default=MatchStatus.AMBIGUOUS_REFERENCE, init=False)


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    """Categorized deterministic matching output."""

    matched_pairs: tuple[MatchedPair, ...]
    unmatched_invoices: tuple[UnmatchedInvoice, ...]
    unmatched_payments: tuple[UnmatchedPayment, ...]
    amount_mismatches: tuple[AmountMismatch, ...]
    currency_mismatches: tuple[CurrencyMismatch, ...]
    ambiguous_references: tuple[AmbiguousReference, ...]


def match_invoices_to_payments(
    invoices: Iterable[InvoiceRecord],
    payments: Iterable[PaymentRecord],
) -> ReconciliationResult:
    """Match normalized invoice and payment records using Phase 2 rules."""
    invoice_groups = _group_invoices(invoices)
    payment_groups = _group_payments(payments)

    matched_pairs: list[MatchedPair] = []
    unmatched_invoices: list[UnmatchedInvoice] = []
    unmatched_payments: list[UnmatchedPayment] = []
    amount_mismatches: list[AmountMismatch] = []
    currency_mismatches: list[CurrencyMismatch] = []
    ambiguous_references: list[AmbiguousReference] = []

    for reference, grouped_invoices in invoice_groups.items():
        grouped_payments = payment_groups.get(reference, ())

        if len(grouped_invoices) > 1 or len(grouped_payments) > 1:
            ambiguous_references.append(
                AmbiguousReference(
                    reference=reference,
                    invoices=grouped_invoices,
                    payments=grouped_payments,
                    reason=_ambiguous_reason(grouped_invoices, grouped_payments),
                )
            )
            continue

        invoice = grouped_invoices[0]
        if not grouped_payments:
            unmatched_invoices.append(
                UnmatchedInvoice(reference=reference, invoice=invoice)
            )
            continue

        payment = grouped_payments[0]
        if invoice.invoice_amount.currency != payment.payment_amount.currency:
            currency_mismatches.append(
                CurrencyMismatch(
                    reference=reference,
                    invoice=invoice,
                    payment=payment,
                )
            )
            continue

        if invoice.invoice_amount.value != payment.payment_amount.value:
            amount_mismatches.append(
                AmountMismatch(
                    reference=reference,
                    invoice=invoice,
                    payment=payment,
                )
            )
            continue

        matched_pairs.append(
            MatchedPair(reference=reference, invoice=invoice, payment=payment)
        )

    for reference, grouped_payments in payment_groups.items():
        if reference in invoice_groups:
            continue

        if len(grouped_payments) > 1:
            ambiguous_references.append(
                AmbiguousReference(
                    reference=reference,
                    invoices=(),
                    payments=grouped_payments,
                    reason=AmbiguousReferenceReason.DUPLICATE_PAYMENT_REFERENCE,
                )
            )
            continue

        unmatched_payments.append(
            UnmatchedPayment(reference=reference, payment=grouped_payments[0])
        )

    return ReconciliationResult(
        matched_pairs=tuple(matched_pairs),
        unmatched_invoices=tuple(unmatched_invoices),
        unmatched_payments=tuple(unmatched_payments),
        amount_mismatches=tuple(amount_mismatches),
        currency_mismatches=tuple(currency_mismatches),
        ambiguous_references=tuple(ambiguous_references),
    )


def _group_invoices(
    invoices: Iterable[InvoiceRecord],
) -> dict[str, tuple[InvoiceRecord, ...]]:
    grouped: dict[str, list[InvoiceRecord]] = {}
    for invoice in invoices:
        grouped.setdefault(invoice.invoice_id, []).append(invoice)
    return {reference: tuple(records) for reference, records in grouped.items()}


def _group_payments(
    payments: Iterable[PaymentRecord],
) -> dict[str, tuple[PaymentRecord, ...]]:
    grouped: dict[str, list[PaymentRecord]] = {}
    for payment in payments:
        grouped.setdefault(payment.payment_reference, []).append(payment)
    return {reference: tuple(records) for reference, records in grouped.items()}


def _ambiguous_reason(
    invoices: tuple[InvoiceRecord, ...],
    payments: tuple[PaymentRecord, ...],
) -> AmbiguousReferenceReason:
    has_duplicate_invoices = len(invoices) > 1
    has_duplicate_payments = len(payments) > 1

    if has_duplicate_invoices and has_duplicate_payments:
        return AmbiguousReferenceReason.DUPLICATE_INVOICE_AND_PAYMENT_REFERENCE
    if has_duplicate_invoices:
        return AmbiguousReferenceReason.DUPLICATE_INVOICE_REFERENCE
    return AmbiguousReferenceReason.DUPLICATE_PAYMENT_REFERENCE

# ---------------------------------------------------------
# VOSS CYCLES: Customer payment reconciliation extensions
# ---------------------------------------------------------

class VossPaymentStatus(StrEnum):
    DEPOSIT_MATCHED = "deposit_matched"
    POTENTIAL_DUPLICATE = "potential_duplicate"
    SUGGESTED_MATCH_REQUIRES_APPROVAL = "suggested_match_requires_approval"
    UNALLOCATED = "unallocated"


@dataclass(frozen=True, slots=True)
class VossDepositMatch:
    order: CustomerOrderRecord
    payment: PaymentRecord
    status: VossPaymentStatus = field(
        default=VossPaymentStatus.DEPOSIT_MATCHED,
        init=False,
    )


@dataclass(frozen=True, slots=True)
class VossDuplicatePayment:
    order: CustomerOrderRecord
    payments: tuple[PaymentRecord, ...]
    status: VossPaymentStatus = field(
        default=VossPaymentStatus.POTENTIAL_DUPLICATE,
        init=False,
    )


@dataclass(frozen=True, slots=True)
class VossSuggestedMatch:
    order: CustomerOrderRecord
    payment: PaymentRecord
    reason: str
    requires_human_approval: bool = True
    status: VossPaymentStatus = field(
        default=VossPaymentStatus.SUGGESTED_MATCH_REQUIRES_APPROVAL,
        init=False,
    )


@dataclass(frozen=True, slots=True)
class VossUnallocatedPayment:
    payment: PaymentRecord
    reason: str
    status: VossPaymentStatus = field(
        default=VossPaymentStatus.UNALLOCATED,
        init=False,
    )


@dataclass(frozen=True, slots=True)
class VossPaymentResult:
    deposit_matches: tuple[VossDepositMatch, ...]
    potential_duplicates: tuple[VossDuplicatePayment, ...]
    suggested_matches: tuple[VossSuggestedMatch, ...]
    unallocated_payments: tuple[VossUnallocatedPayment, ...]


def reconcile_voss_payments(
    orders: Iterable[CustomerOrderRecord],
    payments: Iterable[PaymentRecord],
) -> VossPaymentResult:

    order_list = tuple(orders)
    payment_list = tuple(payments)

    deposit_matches = []
    potential_duplicates = []
    suggested_matches = []
    unallocated_payments = []

    processed_payment_ids = set()

    for order in order_list:
        normalized_order_ref = _normalize_voss_reference(order.order_id)

        related_payments = tuple(
            payment
            for payment in payment_list
            if normalized_order_ref
            in _normalize_voss_reference(payment.payment_reference)
        )

        if len(related_payments) > 1:
            potential_duplicates.append(
                VossDuplicatePayment(order, related_payments)
            )
            processed_payment_ids.update(
                payment.payment_id for payment in related_payments
            )
            continue

        if len(related_payments) == 1:
            payment = related_payments[0]

            if (
                payment.payment_amount.currency
                == order.deposit_received.currency
                and payment.payment_amount.value
                == order.deposit_received.value
            ):
                deposit_matches.append(
                    VossDepositMatch(order, payment)
                )
                processed_payment_ids.add(payment.payment_id)

    for payment in payment_list:
        if payment.payment_id in processed_payment_ids:
            continue

        reference = payment.payment_reference.casefold()

        candidates = [
            order
            for order in order_list
            if order.customer_name.split()[0].casefold() in reference
            and order.balance_due.currency == payment.payment_amount.currency
            and order.balance_due.value == payment.payment_amount.value
        ]

        if len(candidates) == 1:
            suggested_matches.append(
                VossSuggestedMatch(
                    candidates[0],
                    payment,
                    "Customer name and balance amount match; human approval required.",
                )
            )
            processed_payment_ids.add(payment.payment_id)

    for payment in payment_list:
        if payment.payment_id not in processed_payment_ids:
            unallocated_payments.append(
                VossUnallocatedPayment(
                    payment,
                    "No reliable automatic payment match found.",
                )
            )

    return VossPaymentResult(
        tuple(deposit_matches),
        tuple(potential_duplicates),
        tuple(suggested_matches),
        tuple(unallocated_payments),
    )


def _normalize_voss_reference(reference: str) -> str:
    return "".join(
        character.lower()
        for character in reference
        if character.isalnum()
    )