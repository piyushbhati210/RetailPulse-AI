
import pandas as pd
import pytest

from benchmark.fixtures.monthly_revenue import monthly_revenue


def test_monthly_revenue_rejects_missing_required_columns():
    transactions = pd.DataFrame({
        "InvoiceDate": ["2024-01-10"]
    })

    with pytest.raises(ValueError, match="Revenue"):
        monthly_revenue(transactions)


@pytest.mark.xfail(
    strict=True,
    reason="Known benchmark defect: year is missing from the grouping key"
)
def test_monthly_revenue_separates_same_month_across_years():
    transactions = pd.DataFrame({
        "InvoiceDate": [
            "2024-01-10",
            "2025-01-10"
        ],
        "Revenue": [100, 200]
    })

    actual = monthly_revenue(transactions)

    expected = pd.DataFrame({
        "YearMonth": ["2024-01", "2025-01"],
        "Revenue": [100, 200]
    })

    pd.testing.assert_frame_equal(actual, expected)
