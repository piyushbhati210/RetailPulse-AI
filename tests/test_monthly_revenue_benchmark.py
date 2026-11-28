
import pandas as pd
import pytest

from benchmark.fixtures.monthly_revenue import monthly_revenue


@pytest.mark.parametrize(
    ("transactions", "expected_message"),
    [
        (
            pd.DataFrame({"InvoiceDate": ["2024-01-10"]}),
            "Missing columns: ['Revenue']",
        ),
        (
            pd.DataFrame({"Revenue": [100]}),
            "Missing columns: ['InvoiceDate']",
        ),
        (
            pd.DataFrame(),
            "Missing columns: ['InvoiceDate', 'Revenue']",
        ),
    ],
)
def test_monthly_revenue_rejects_missing_columns(
    transactions, expected_message
):
    with pytest.raises(ValueError) as exc_info:
        monthly_revenue(transactions)

    assert str(exc_info.value) == expected_message


def test_monthly_revenue_sums_transactions_in_same_month():
    transactions = pd.DataFrame({
        "InvoiceDate": ["2024-01-10", "2024-01-15"],
        "Revenue": [100, 50],
    })

    actual = monthly_revenue(transactions)

    expected = pd.DataFrame({
        "YearMonth": ["2024-01"],
        "Revenue": [150],
    })

    pd.testing.assert_frame_equal(actual, expected)


def test_monthly_revenue_separates_different_years():
    transactions = pd.DataFrame({
        "InvoiceDate": ["2024-01-10", "2025-01-10"],
        "Revenue": [100, 200],
    })

    actual = monthly_revenue(transactions)

    expected = pd.DataFrame({
        "YearMonth": ["2024-01", "2025-01"],
        "Revenue": [100, 200],
    })

    pd.testing.assert_frame_equal(actual, expected)


def test_monthly_revenue_sorts_chronologically():
    transactions = pd.DataFrame({
        "InvoiceDate": ["2024-01-10", "2023-12-10"],
        "Revenue": [200, 100],
    })

    actual = monthly_revenue(transactions)

    assert actual["YearMonth"].tolist() == [
        "2023-12",
        "2024-01",
    ]


def test_monthly_revenue_rejects_missing_dates():
    transactions = pd.DataFrame({
        "InvoiceDate": ["2024-01-10", None],
        "Revenue": [100, 200],
    })

    with pytest.raises(
        ValueError, match="InvoiceDate contains missing values"
    ):
        monthly_revenue(transactions)


def test_monthly_revenue_rejects_invalid_dates():
    transactions = pd.DataFrame({
        "InvoiceDate": ["not-a-date"],
        "Revenue": [100],
    })

    with pytest.raises(
        ValueError, match="InvoiceDate contains invalid date values"
    ):
        monthly_revenue(transactions)


def test_monthly_revenue_rejects_missing_revenue():
    transactions = pd.DataFrame({
        "InvoiceDate": ["2024-01-10"],
        "Revenue": [None],
    })

    with pytest.raises(ValueError, match="Revenue contains missing values"):
        monthly_revenue(transactions)


def test_monthly_revenue_rejects_non_numeric_revenue():
    transactions = pd.DataFrame({
        "InvoiceDate": ["2024-01-10"],
        "Revenue": ["invalid"],
    })

    with pytest.raises(ValueError, match="Revenue must contain numeric"):
        monthly_revenue(transactions)


@pytest.mark.parametrize("invalid_revenue", [float("inf"), float("-inf")])
def test_monthly_revenue_rejects_infinite_revenue(invalid_revenue):
    transactions = pd.DataFrame({
        "InvoiceDate": ["2024-01-10"],
        "Revenue": [invalid_revenue],
    })

    with pytest.raises(ValueError, match="finite"):
        monthly_revenue(transactions)


@pytest.mark.parametrize(
    "revenues",
    [
        [True],
        [100, True],
    ],
)
def test_monthly_revenue_rejects_boolean_revenue(revenues):
    transactions = pd.DataFrame({
        "InvoiceDate": pd.date_range(
            "2024-01-01", periods=len(revenues)
        ),
        "Revenue": revenues,
    })

    with pytest.raises(ValueError, match="boolean"):
        monthly_revenue(transactions)


def test_monthly_revenue_does_not_modify_input():
    transactions = pd.DataFrame({
        "InvoiceDate": ["2024-01-10"],
        "Revenue": [100],
    })

    original = transactions.copy(deep=True)

    monthly_revenue(transactions)

    pd.testing.assert_frame_equal(transactions, original)
