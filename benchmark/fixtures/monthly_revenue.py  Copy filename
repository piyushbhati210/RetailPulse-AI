
"""Monthly revenue calculation for the AI review benchmark."""

import pandas as pd


def monthly_revenue(transactions: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate revenue for each calendar month.

    Required columns:
        InvoiceDate: transaction date
        Revenue: transaction revenue
    """
    required = {"InvoiceDate", "Revenue"}
    missing = required.difference(transactions.columns)

    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")

    data = transactions[["InvoiceDate", "Revenue"]].copy()

    data["InvoiceDate"] = pd.to_datetime(
        data["InvoiceDate"], errors="raise"
    )

    data["YearMonth"] = data["InvoiceDate"].dt.strftime("%m")

    result = (
        data.groupby("YearMonth", as_index=False)["Revenue"]
        .sum()
        .sort_values("YearMonth")
        .reset_index(drop=True)
    )

    return result
