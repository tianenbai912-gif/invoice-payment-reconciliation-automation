from datetime import date
from decimal import Decimal

from invoice_reconciliation.models import (
    CustomerOrderRecord,
    MoneyAmount,
    PaymentRecord,
)
from invoice_reconciliation.matching import (
    VossPaymentStatus,
    reconcile_voss_payments,
)


def money(value):
    return MoneyAmount(Decimal(value), "GBP")


def make_order(
    order_id,
    customer,
    total,
    deposit,
    balance,
    completion_date=None,
    reminder_dates=(),
    status="open",
):
    return CustomerOrderRecord(
        order_id=order_id,
        customer_name=customer,
        order_total=money(total),
        deposit_received=money(deposit),
        balance_due=money(balance),
        status=status,
        source_row=2,
        completion_date=completion_date,
        reminder_dates=reminder_dates,
    )


def make_payment(payment_id, customer, amount, reference):
    return PaymentRecord(
        payment_id=payment_id,
        customer_name=customer,
        payment_date=date(2026, 9, 24),
        payment_amount=money(amount),
        payment_reference=reference,
        source_row=2,
    )


def test_okoro_deposit_is_matched():
    order = make_order(
        "VC-2026-034", "J Okoro", "3000", "1000", "2000"
    )
    payment = make_payment(
        "P001", "J Okoro", "1000", "VC-2026-034 DEPOSIT"
    )

    result = reconcile_voss_payments([order], [payment])

    assert len(result.deposit_matches) == 1
    assert result.deposit_matches[0].status == VossPaymentStatus.DEPOSIT_MATCHED


def test_doyle_duplicate_payments_are_flagged():
    order = make_order(
        "VC-2026-035", "H Doyle", "3000", "1000", "2000"
    )
    payments = [
        make_payment("P002", "H Doyle", "1000", "VC2026035"),
        make_payment("P003", "H Doyle", "1000", "VC-2026-035 deposit"),
    ]

    result = reconcile_voss_payments([order], payments)

    assert len(result.potential_duplicates) == 1
    assert len(result.potential_duplicates[0].payments) == 2


def test_tom_hale_balance_is_suggested_for_approval():
    order = make_order(
        "VC-2026-029", "Tom Hale", "3850", "1000", "2850"
    )
    payment = make_payment("P004", "Tom Hale", "2850", "balance - Tom")

    result = reconcile_voss_payments([order], [payment])

    assert len(result.suggested_matches) == 1
    assert result.suggested_matches[0].requires_human_approval is True


def test_unrecognised_payment_remains_unallocated():
    order = make_order(
        "VC-2026-034", "J Okoro", "3000", "1000", "2000"
    )
    payment = make_payment("P005", "Unknown", "500", "UNKNOWN REF")

    result = reconcile_voss_payments([order], [payment])

    assert len(result.unallocated_payments) == 1


def test_aoife_byrne_balance_is_3230():
    order = make_order(
        "VC-2026-028", "Aoife Byrne", "4230", "1000", "3230"
    )

    assert order.balance_due.value == Decimal("3230")


def test_disputed_respray_line_can_be_flagged():
    from invoice_reconciliation.models import SupplierInvoiceLine

    line = SupplierInvoiceLine(
        order_reference="VC-2026-026",
        description="Re-spray colour correction",
        net_amount=money("180"),
        review_required=True,
        review_note="Supplier charge disputed due to colour error.",
    )

    assert line.review_required is True
    assert line.net_amount.value == Decimal("180")
def test_chris_adeyemi_requires_manual_escalation():
    order = make_order(
        "VC-2026-027",
        "Chris Adeyemi",
        "3400",
        "1000",
        "2400",
        completion_date=date(2026, 9, 4),
        reminder_dates=(
            date(2026, 9, 8),
            date(2026, 9, 18),
        ),
        status="complete",
    )

    result = reconcile_voss_payments([order], [])

    assert len(result.manual_escalations) == 1
    assert result.manual_escalations[0].assigned_to == "Nadia"
    assert result.manual_escalations[0].order.balance_due.value == Decimal("2400")
    
def test_aoife_balance_invoice_and_vat_review_hold():
    from csv import DictReader
    from pathlib import Path
    from invoice_reconciliation.ingestion import load_invoice_file

    invoice_path = Path("sample-data/voss-balance-invoice.csv")
    result = load_invoice_file(invoice_path)

    assert len(result.records) == 1
    assert len(result.diagnostics.errors) == 0
    assert result.records[0].customer_name == "Aoife Byrne"
    assert result.records[0].invoice_amount.value == Decimal("3230")

    vat_path = Path("sample-data/voss-vat-review.csv")
    with vat_path.open(newline="", encoding="utf-8") as file:
        review = next(DictReader(file))

    assert review["review_status"] == "PENDING"
    assert review["dispatch_status"] == "ON HOLD"