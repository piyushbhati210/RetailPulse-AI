
"""Monthly revenue calculation for the AI review benchmark."""

import numpy as np
import pandas as pd


def monthly_revenue(transactions: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate revenue for each calendar month.

    Required columns:
        InvoiceDate: transaction date
        Revenue: transaction revenue

    Returns:
        DataFrame containing YearMonth and Revenue.
    """
    required = {"InvoiceDate", "Revenue"}
    missing = required.difference(transactions.columns)

    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")

    data = transactions[["InvoiceDate", "Revenue"]].copy()

    # Parse dates and provide a clear error for invalid values.
    try:
        dates = pd.to_datetime(data["InvoiceDate"], errors="raise")
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "InvoiceDate contains invalid date values"
        ) from exc

    if dates.isna().any():
        raise ValueError("InvoiceDate contains missing values")

    # Reject boolean values, including values in mixed-type columns.
    is_boolean = data["Revenue"].map(
        lambda value: isinstance(value, (bool, np.bool_))
    )

    if is_boolean.any():
        raise ValueError("Revenue must not contain boolean values")

    # Convert revenue to numeric values.
    try:
        revenue = pd.to_numeric(data["Revenue"], errors="raise")
    except (TypeError, ValueError) as exc:
        raise ValueError("Revenue must contain numeric values") from exc

    if revenue.isna().any():
        raise ValueError("Revenue contains missing values")

    if not np.isfinite(revenue.to_numpy(dtype="float64")).all():
        raise ValueError("Revenue must contain finite numeric values")

    data["InvoiceDate"] = dates
    data["Revenue"] = revenue

    # Preserve both year and month.
    data["YearMonth"] = dates.dt.to_period("M").astype(str)

    result = (
        data.groupby("YearMonth", as_index=False)["Revenue"]
        .sum()
        .sort_values("YearMonth")
        .reset_index(drop=True)
    )

    return result
