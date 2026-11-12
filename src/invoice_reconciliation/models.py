"""Domain models for imported invoice and payment data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class MoneyAmount:
    """Normalized money amount and currency."""

    value: Decimal
    currency: str


@dataclass(frozen=True, slots=True)
class InvoiceRecord:
    """Validated invoice input row."""

    invoice_id: str
    customer_name: str
    invoice_date: date
    due_date: date
    invoice_amount: MoneyAmount
    source_row: int


@dataclass(frozen=True, slots=True)
class PaymentRecord:
    """Validated payment input row."""

    payment_id: str
    customer_name: str
    payment_date: date
    payment_amount: MoneyAmount
    payment_reference: str
    source_row: int


@dataclass(frozen=True, slots=True)
class ValidationError:
    """Stable row-level validation diagnostic."""

    source: str
    row_number: int
    field: str
    error_code: str
    message: str

    def to_dict(self) -> dict[str, int | str]:
        """Return a deterministic serializable representation."""
        return {
            "source": self.source,
            "row_number": self.row_number,
            "field": self.field,
            "error_code": self.error_code,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class ImportDiagnostics:
    """Summary of a single import attempt."""

    source: str
    rows_seen: int
    valid_rows: int
    invalid_rows: int
    errors: tuple[ValidationError, ...]


@dataclass(frozen=True, slots=True)
class ImportResult[TRecord]:
    """Imported records and diagnostics."""

    records: tuple[TRecord, ...]
    diagnostics: ImportDiagnostics

@dataclass(frozen=True, slots=True)
class CustomerOrderRecord:
    """Customer order and outstanding payment information."""

    order_id: str
    customer_name: str
    order_total: MoneyAmount
    deposit_received: MoneyAmount
    balance_due: MoneyAmount
    status: str
    source_row: int
    completion_date: date | None = None
    reminder_dates: tuple[date, ...] = ()


@dataclass(frozen=True, slots=True)
class SupplierInvoiceLine:
    """Individual item on a supplier invoice."""

    order_reference: str
    description: str
    net_amount: MoneyAmount
    review_required: bool = False
    review_note: str | None = None


@dataclass(frozen=True, slots=True)
class SupplierInvoiceRecord:
    """Supplier invoice with line items and VAT information."""

    supplier_name: str
    supplier_invoice_id: str
    invoice_date: date
    due_date: date
    lines: tuple[SupplierInvoiceLine, ...]
    subtotal: MoneyAmount
    vat_amount: MoneyAmount
    total_amount: MoneyAmount
    source_row: int