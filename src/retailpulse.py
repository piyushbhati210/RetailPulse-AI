"""RetailPulse AI - analytics core.

This module has NO Streamlit imports, so every function can be unit-tested
with plain pytest. app.py only handles the user interface.
"""
from __future__ import annotations

import io
import re
import sqlite3
import time
import warnings

import numpy as np
import pandas as pd
from scipy import stats

# --------------------------------------------------------------------------
# Standard schema and column detection
# --------------------------------------------------------------------------
CANONICAL_FIELDS = [
    "InvoiceNo", "StockCode", "Description", "Quantity", "InvoiceDate",
    "UnitPrice", "Revenue", "CustomerID", "Country", "Category",
]
TEXT_FIELDS = ["InvoiceNo", "StockCode", "Description", "CustomerID", "Country", "Category"]
ID_FIELDS = ["InvoiceNo", "StockCode", "CustomerID"]

FIELD_LABELS = {
    "InvoiceNo": "Order / invoice ID",
    "StockCode": "Product code (SKU)",
    "Description": "Product name",
    "Quantity": "Quantity",
    "InvoiceDate": "Order date",
    "UnitPrice": "Unit price",
    "Revenue": "Revenue / sales amount",
    "CustomerID": "Customer ID",
    "Country": "Country / region",
    "Category": "Product category",
}
FIELD_HELP = {
    "InvoiceNo": "Order, invoice, transaction or basket identifier.",
    "StockCode": "Product SKU or product identifier.",
    "Description": "Product name or description.",
    "Quantity": "Units purchased on the line.",
    "InvoiceDate": "Date or timestamp of the order.",
    "UnitPrice": "Price of one unit.",
    "Revenue": "Line total. If you leave this empty, Quantity x Unit price is used.",
    "CustomerID": "Customer identifier (needed for RFM).",
    "Country": "Country, region or market.",
    "Category": "Product category or department.",
}

ALIASES = {
    "InvoiceNo": ["invoiceno", "invoice", "invoicenumber", "orderid", "order", "ordernumber",
                  "orderno", "transactionid", "transaction", "basketid", "receiptno"],
    "StockCode": ["stockcode", "sku", "productid", "productcode", "itemcode", "itemid", "stockid"],
    "Description": ["description", "productname", "product", "itemname", "item", "title", "productdescription"],
    "Quantity": ["quantity", "qty", "units", "unitssold", "salesquantity", "quantitysold"],
    "InvoiceDate": ["invoicedate", "date", "orderdate", "transactiondate", "datetime", "timestamp", "purchasedate"],
    "UnitPrice": ["unitprice", "price", "unitcost", "sellingprice", "itemprice", "priceperunit"],
    "Revenue": ["revenue", "sales", "salesamount", "totalsales", "totalamount", "amount",
                "totalrevenue", "turnover", "linetotal", "total"],
    "CustomerID": ["customerid", "customer", "clientid", "userid", "custid", "customernumber"],
    "Country": ["country", "region", "market", "countryname", "territory"],
    "Category": ["category", "productcategory", "department", "producttype"],
}


def _normalize(value) -> str:
    return "".join(ch.lower() for ch in str(value) if ch.isalnum())


def detect_column_mapping(columns) -> dict:
    """Suggest {standard field: source column} using case-insensitive aliases."""
    lookup: dict[str, str] = {}
    for col in columns:
        lookup.setdefault(_normalize(col), col)
    used: set = set()
    result: dict = {}
    for field in CANONICAL_FIELDS:
        for alias in ALIASES[field]:
            col = lookup.get(_normalize(alias))
            if col is not None and col not in used:
                result[field] = col
                used.add(col)
                break
    return result


def validate_mapping(mapping: dict, columns) -> list[str]:
    """Return a list of human-readable problems (empty list = mapping is OK)."""
    problems: list[str] = []
    cols = set(columns)
    for field, col in mapping.items():
        if col not in cols:
            problems.append(f"Column '{col}' chosen for {FIELD_LABELS.get(field, field)} does not exist in the file.")
    seen: dict = {}
    for field, col in mapping.items():
        if col in seen:
            problems.append(
                f"Column '{col}' is used for both {FIELD_LABELS[seen[col]]} and {FIELD_LABELS[field]}. "
                "Please pick a different column for one of them."
            )
        seen.setdefault(col, field)
    has_revenue = bool(mapping.get("Revenue"))
    has_qty_price = bool(mapping.get("Quantity")) and bool(mapping.get("UnitPrice"))
    if not (has_revenue or has_qty_price):
        problems.append("Map either a Revenue/sales column, or BOTH Quantity and Unit price.")
    return problems


# --------------------------------------------------------------------------
# Reading and cleaning
# --------------------------------------------------------------------------
def read_table(file_bytes: bytes, filename: str) -> pd.DataFrame:
    """Read a CSV / XLS / XLSX upload into a DataFrame."""
    name = filename.lower()
    if name.endswith(".csv"):
        df = pd.read_csv(io.BytesIO(file_bytes), encoding_errors="replace")
        if df.shape[1] == 1:  # probably a ';' or tab separated file
            try:
                alt = pd.read_csv(io.BytesIO(file_bytes), sep=None, engine="python", encoding_errors="replace")
                if alt.shape[1] > 1:
                    df = alt
            except Exception:
                pass
        return df
    if name.endswith((".xlsx", ".xls")):
        return pd.read_excel(io.BytesIO(file_bytes))
    raise ValueError("Unsupported file type. Please upload a .csv, .xls or .xlsx file.")


def _to_numeric(series: pd.Series) -> pd.Series:
    """Convert numbers and currency-formatted text ('$1,234.50') to float; bad values become NaN."""
    if pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series):
        return pd.to_numeric(series, errors="coerce").astype("float64")
    cleaned = series.astype("string").str.replace(r"[^\d.\-eE+]", "", regex=True)
    return pd.to_numeric(cleaned, errors="coerce").astype("float64")


def clean_dataset(raw: pd.DataFrame, mapping: dict, remove_duplicates: bool = True,
                  remove_cancellations: bool = True, remove_nonpositive: bool = True):
    """Map a raw dataset onto the standard schema and clean it.

    Returns (clean_df, quality_report). Every removal step is counted so the
    user can see exactly why rows were dropped.
    """
    problems = validate_mapping(mapping, raw.columns)
    if problems:
        raise ValueError(" ".join(problems))

    out = pd.DataFrame(index=raw.index)
    for field in CANONICAL_FIELDS:
        src = mapping.get(field)
        out[field] = raw[src] if src else pd.NA

    for field in TEXT_FIELDS:
        s = out[field].astype("string").str.strip()
        if field in ID_FIELDS:  # Excel often stores IDs as 17850.0
            s = s.str.replace(r"^(\d+)\.0+$", r"\1", regex=True)
        out[field] = s.mask((s == "").fillna(False))

    for field in ["Quantity", "UnitPrice", "Revenue"]:
        out[field] = _to_numeric(out[field])

    raw_dates_present = out["InvoiceDate"].notna()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        out["InvoiceDate"] = pd.to_datetime(out["InvoiceDate"], errors="coerce")
    invalid_dates = int((raw_dates_present & out["InvoiceDate"].isna()).sum())

    # Revenue: use the Revenue column where valid, otherwise Quantity x UnitPrice.
    out["Revenue"] = out["Revenue"].fillna(out["Quantity"] * out["UnitPrice"])

    input_rows = len(out)
    removed = {"duplicates": 0, "no_revenue": 0, "cancellations": 0, "non_positive": 0}

    if remove_duplicates:
        dup = out.duplicated()
        removed["duplicates"] = int(dup.sum())
        out = out.loc[~dup]

    bad_revenue = ~np.isfinite(out["Revenue"])
    removed["no_revenue"] = int(bad_revenue.sum())
    out = out.loc[~bad_revenue]

    if remove_cancellations and mapping.get("InvoiceNo"):
        # Only IDs like 'C536379' (letter C followed by a digit) are treated as cancellations.
        is_cancel = out["InvoiceNo"].fillna("").str.upper().str.match(r"^C\d").astype(bool)
        removed["cancellations"] = int(is_cancel.sum())
        out = out.loc[~is_cancel]

    if remove_nonpositive:
        bad = (out["Quantity"] <= 0) | (out["UnitPrice"] <= 0) | (out["Revenue"] <= 0)
        removed["non_positive"] = int(bad.sum())
        out = out.loc[~bad]

    out = out.reset_index(drop=True)

    has = lambda col: bool(out[col].notna().any())  # noqa: E731
    features = {
        "sales": has("Revenue"),
        "orders": has("InvoiceNo"),
        "products": has("Description") or has("StockCode"),
        "dates": has("InvoiceDate"),
        "customers": has("CustomerID"),
        "countries": has("Country"),
        "quantity": has("Quantity"),
        "categories": has("Category"),
    }
    features["basket_analysis"] = features["orders"] and features["products"]
    features["rfm"] = features["customers"] and features["orders"] and features["dates"]

    quality = {
        "input_rows": int(input_rows),
        "retained_rows": int(len(out)),
        "removed_rows": int(input_rows - len(out)),
        "duplicates_removed": removed["duplicates"],
        "no_revenue_removed": removed["no_revenue"],
        "cancellations_removed": removed["cancellations"],
        "non_positive_removed": removed["non_positive"],
        "invalid_dates_kept": invalid_dates,
        "missing_customer_rows": int(out["CustomerID"].isna().sum()) if len(out) else 0,
        "features": features,
    }
    return out, quality


# --------------------------------------------------------------------------
# Sales analytics
# --------------------------------------------------------------------------
def product_column(df: pd.DataFrame):
    """Best column for naming products: Description, else StockCode, else None."""
    for col in ("Description", "StockCode"):
        if col in df.columns and df[col].notna().any():
            return col
    return None


def filter_data(df: pd.DataFrame, countries=None, date_range=None, product_query: str = "") -> pd.DataFrame:
    """Apply sidebar filters. Pass None to skip a filter."""
    mask = pd.Series(True, index=df.index)
    if countries is not None:
        mask &= df["Country"].isin(list(countries))
    if date_range is not None:
        start = pd.Timestamp(date_range[0])
        end = pd.Timestamp(date_range[1]) + pd.Timedelta(days=1)
        mask &= (df["InvoiceDate"] >= start) & (df["InvoiceDate"] < end)
    query = (product_query or "").strip()
    if query:
        hit = pd.Series(False, index=df.index)
        for col in ("Description", "StockCode"):
            hit |= df[col].fillna("").str.contains(query, case=False, regex=False).astype(bool)
        mask &= hit
    return df.loc[mask].reset_index(drop=True)


def compute_kpis(df: pd.DataFrame) -> dict:
    total = float(df["Revenue"].sum()) if len(df) else 0.0
    orders = int(df["InvoiceNo"].nunique()) if df["InvoiceNo"].notna().any() else None
    return {
        "total_revenue": total,
        "orders": orders,
        "avg_order_value": (total / orders) if orders else None,
        "customers": int(df["CustomerID"].nunique()) if df["CustomerID"].notna().any() else None,
        "units": float(df["Quantity"].sum()) if df["Quantity"].notna().any() else None,
        "rows": int(len(df)),
    }


def monthly_sales(df: pd.DataFrame) -> pd.DataFrame:
    d = df.dropna(subset=["InvoiceDate"])
    if d.empty:
        return pd.DataFrame(columns=["Month", "Revenue", "Orders"])
    grouped = d.groupby(d["InvoiceDate"].dt.to_period("M")).agg(
        Revenue=("Revenue", "sum"), Orders=("InvoiceNo", "nunique"))
    grouped.index = grouped.index.to_timestamp()
    return grouped.rename_axis("Month").reset_index()


def top_products(df: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    col = product_column(df)
    if col is None or df.empty:
        return pd.DataFrame(columns=["Product", "Revenue", "Units", "Orders"])
    g = df.groupby(col).agg(Revenue=("Revenue", "sum"), Units=("Quantity", "sum"),
                            Orders=("InvoiceNo", "nunique"))
    return g.nlargest(n, "Revenue").rename_axis("Product").reset_index()


def country_sales(df: pd.DataFrame) -> pd.DataFrame:
    d = df.dropna(subset=["Country"])
    if d.empty:
        return pd.DataFrame(columns=["Country", "Revenue", "Orders"])
    g = d.groupby("Country").agg(Revenue=("Revenue", "sum"), Orders=("InvoiceNo", "nunique"))
    return g.sort_values("Revenue", ascending=False).reset_index()


# --------------------------------------------------------------------------
# SQL analytics (SQLite) - read-only by design
# --------------------------------------------------------------------------
SQL_TABLE = "sales"
_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|ATTACH|DETACH|PRAGMA|VACUUM|REINDEX|TRUNCATE|"
    r"BEGIN|COMMIT|ROLLBACK|SAVEPOINT|RELEASE|LOAD_EXTENSION)\b|\bREPLACE\s+INTO\b",
    re.IGNORECASE,
)
_TOKEN = re.compile(r"'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"|--[^\n]*|/\*.*?\*/", re.DOTALL)


def _mask_literals_and_comments(sql: str) -> str:
    def repl(m):
        t = m.group(0)
        if t.startswith("'"):
            return "''"
        if t.startswith('"'):
            return '""'
        return " "
    return _TOKEN.sub(repl, sql)


def validate_sql(sql: str):
    """Return (ok, message). Only a single SELECT / WITH statement is allowed."""
    if not sql or not sql.strip():
        return False, "Please type a query first."
    body = _mask_literals_and_comments(sql).strip().rstrip(";").strip()
    if not body:
        return False, "The query is empty."
    if ";" in body:
        return False, "Only one SQL statement is allowed."
    if not re.match(r"^(SELECT|WITH)\b", body, re.IGNORECASE):
        return False, "Only read-only queries that start with SELECT or WITH are allowed."
    hit = _FORBIDDEN.search(body)
    if hit:
        return False, f"'{hit.group(0).upper()}' is not allowed. This SQL box is read-only."
    return True, ""


def load_to_sqlite(df: pd.DataFrame, path: str = ":memory:") -> sqlite3.Connection:
    """Load the cleaned data into table `sales`. path=':memory:' is temporary."""
    data = df.copy()
    data = data.loc[:, data.notna().any()] if len(data) else data
    if "InvoiceDate" in data.columns:
        data["YearMonth"] = data["InvoiceDate"].dt.strftime("%Y-%m")
        data["InvoiceDate"] = data["InvoiceDate"].dt.strftime("%Y-%m-%d %H:%M:%S")
    for col in data.columns:
        if not pd.api.types.is_numeric_dtype(data[col]):
            data[col] = data[col].astype(object).where(data[col].notna(), None)
    conn = sqlite3.connect(path, check_same_thread=False)
    data.to_sql(SQL_TABLE, conn, if_exists="replace", index=False, chunksize=50_000)
    for col in ("InvoiceNo", "CustomerID", "Country", "YearMonth"):
        if col in data.columns:
            conn.execute(f'CREATE INDEX IF NOT EXISTS idx_{SQL_TABLE}_{col} ON {SQL_TABLE}("{col}")')
    conn.commit()
    conn.execute("PRAGMA query_only = ON")  # second safety layer: database refuses writes
    return conn


def run_query(conn: sqlite3.Connection, sql: str, max_rows: int = 5000, timeout_s: float = 20.0):
    """Run a validated read-only query. Returns (DataFrame, was_truncated)."""
    ok, message = validate_sql(sql)
    if not ok:
        raise ValueError(message)
    start = time.time()
    conn.set_progress_handler(lambda: 1 if time.time() - start > timeout_s else 0, 10_000)
    try:
        cur = conn.execute(sql.strip().rstrip(";"))
        if cur.description is None:
            raise ValueError("The query did not return any columns.")
        columns = [d[0] for d in cur.description]
        rows = cur.fetchmany(max_rows + 1)
    finally:
        conn.set_progress_handler(None, 0)
    truncated = len(rows) > max_rows
    return pd.DataFrame(rows[:max_rows], columns=columns), truncated


def example_queries(features: dict) -> dict:
    """Example queries that only use columns that exist in this dataset."""
    t = SQL_TABLE
    pcol = "Description" if features.get("products") else None
    orders = ", COUNT(DISTINCT InvoiceNo) AS orders" if features.get("orders") else ""
    q = {
        "Sales summary": (
            f"SELECT COUNT(*) AS line_items{orders},\n"
            f"       ROUND(SUM(Revenue), 2) AS total_revenue\nFROM {t};"
        )
    }
    if features.get("dates"):
        q["Monthly sales"] = (
            f"SELECT YearMonth, ROUND(SUM(Revenue), 2) AS revenue{orders}\nFROM {t}\n"
            "WHERE YearMonth IS NOT NULL\nGROUP BY YearMonth\nORDER BY YearMonth;"
        )
    if pcol:
        q["Top 10 products"] = (
            f"SELECT {pcol}, ROUND(SUM(Revenue), 2) AS revenue\nFROM {t}\n"
            f"WHERE {pcol} IS NOT NULL\nGROUP BY {pcol}\nORDER BY revenue DESC\nLIMIT 10;"
        )
    if features.get("countries"):
        q["Regional performance"] = (
            f"SELECT Country, ROUND(SUM(Revenue), 2) AS revenue{orders}\nFROM {t}\n"
            "WHERE Country IS NOT NULL\nGROUP BY Country\nORDER BY revenue DESC;"
        )
    if features.get("customers") and features.get("orders"):
        q["Repeat customers"] = (
            "WITH per_customer AS (\n"
            "  SELECT CustomerID, COUNT(DISTINCT InvoiceNo) AS orders, SUM(Revenue) AS revenue\n"
            f"  FROM {t}\n  WHERE CustomerID IS NOT NULL\n  GROUP BY CustomerID\n)\n"
            "SELECT CASE WHEN orders > 1 THEN 'Repeat' ELSE 'One-time' END AS customer_type,\n"
            "       COUNT(*) AS customers, ROUND(SUM(revenue), 2) AS revenue\n"
            "FROM per_customer\nGROUP BY customer_type;"
        )
    return q


# --------------------------------------------------------------------------
# RFM customer segmentation
# --------------------------------------------------------------------------
SEGMENT_ORDER = ["Champions", "Loyal", "New / Promising", "Needs Attention", "At Risk", "Hibernating"]


def _score(values: pd.Series) -> pd.Series:
    """1-5 score from percentile rank (higher value = higher score; ties share a score)."""
    pct = values.rank(method="average", pct=True)
    return np.ceil(np.round(pct * 5, 9)).clip(1, 5).astype(int)


def compute_rfm(df: pd.DataFrame, snapshot_date=None) -> pd.DataFrame:
    """One row per customer with Recency (days), Frequency (orders), Monetary (revenue)."""
    d = df.dropna(subset=["CustomerID", "InvoiceNo", "InvoiceDate"])
    if d.empty:
        raise ValueError("RFM needs rows that have a customer ID, an order ID and a valid date.")
    snapshot = pd.Timestamp(snapshot_date) if snapshot_date is not None else d["InvoiceDate"].max().normalize() + pd.Timedelta(days=1)
    rfm = d.groupby("CustomerID").agg(
        LastPurchase=("InvoiceDate", "max"),
        Frequency=("InvoiceNo", "nunique"),
        Monetary=("Revenue", "sum"),
    )
    if len(rfm) < 5:
        raise ValueError("RFM needs at least 5 customers in the current selection.")
    rfm["Recency"] = (snapshot - rfm["LastPurchase"]).dt.days
    rfm["R"] = _score(-rfm["Recency"])  # recent buyers get a HIGH score
    rfm["F"] = _score(rfm["Frequency"])
    rfm["M"] = _score(rfm["Monetary"])
    r, f = rfm["R"], rfm["F"]
    conditions = [
        (r >= 4) & (f >= 4),
        (r >= 3) & (f >= 3),
        (r >= 4) & (f <= 2),
        (r <= 2) & (f >= 3),
        (r <= 2) & (f <= 2),
    ]
    labels = ["Champions", "Loyal", "New / Promising", "At Risk", "Hibernating"]
    rfm["Segment"] = np.select(conditions, labels, default="Needs Attention")
    return rfm.reset_index()[["CustomerID", "Recency", "Frequency", "Monetary", "R", "F", "M", "Segment"]]


def rfm_segment_summary(rfm: pd.DataFrame) -> pd.DataFrame:
    g = rfm.groupby("Segment").agg(
        Customers=("CustomerID", "count"),
        Revenue=("Monetary", "sum"),
        AvgRecencyDays=("Recency", "mean"),
        AvgOrders=("Frequency", "mean"),
        AvgSpend=("Monetary", "mean"),
    )
    g["CustomerShare"] = g["Customers"] / g["Customers"].sum()
    g["RevenueShare"] = g["Revenue"] / g["Revenue"].sum() if g["Revenue"].sum() else 0.0
    g = g.reindex([s for s in SEGMENT_ORDER if s in g.index])
    return g.reset_index()


# --------------------------------------------------------------------------
# Market basket analysis (association rules, implemented with NumPy)
# --------------------------------------------------------------------------
RULE_COLUMNS = ["Antecedent", "Consequent", "AntecedentOrders", "ConsequentOrders",
                "PairOrders", "Support", "Confidence", "Lift"]


def market_basket(df: pd.DataFrame, min_support: float = 0.01, min_confidence: float = 0.2,
                  top_items: int = 100, max_orders: int = 100_000, max_rules: int = 500, seed: int = 42):
    """Pairwise association rules A -> B.

    support    = share of all orders containing both A and B
    confidence = share of orders with A that also contain B
    lift       = confidence / share of all orders containing B (>1 = bought together more than chance)

    To keep it fast, only the `top_items` most frequent products are used and,
    for very large datasets, at most `max_orders` randomly sampled orders.
    Returns (rules_df, info_dict).
    """
    empty = pd.DataFrame(columns=RULE_COLUMNS)
    item_col = product_column(df)
    if item_col is None or not df["InvoiceNo"].notna().any():
        raise ValueError("Market basket analysis needs order IDs and product names or codes.")
    d = df.loc[df["InvoiceNo"].notna() & df[item_col].notna(), ["InvoiceNo", item_col]].drop_duplicates()
    info = {"item_column": item_col, "orders_total": int(d["InvoiceNo"].nunique()), "orders_used": 0,
            "items_considered": 0, "sampled": False, "message": ""}

    ids = d["InvoiceNo"].unique()
    if len(ids) > max_orders:
        keep = np.random.default_rng(seed).choice(ids, size=max_orders, replace=False)
        d = d[d["InvoiceNo"].isin(keep)]
        info["sampled"] = True
    n_orders = int(d["InvoiceNo"].nunique())
    info["orders_used"] = n_orders
    if n_orders < 20:
        info["message"] = "Not enough orders (need at least 20) for reliable association rules."
        return empty, info

    item_orders = d.groupby(item_col)["InvoiceNo"].nunique().sort_values(ascending=False).head(top_items)
    info["items_considered"] = int(len(item_orders))
    d = d[d[item_col].isin(item_orders.index)]
    d = d[d.groupby("InvoiceNo")[item_col].transform("size") >= 2]
    if d.empty:
        info["message"] = "No orders contain two or more of the most frequent products."
        return empty, info

    o_codes, o_uni = pd.factorize(d["InvoiceNo"])
    i_codes, i_uni = pd.factorize(d[item_col])
    matrix = np.zeros((len(o_uni), len(i_uni)), dtype=np.float32)
    matrix[o_codes, i_codes] = 1.0
    co = matrix.T @ matrix
    np.fill_diagonal(co, 0)
    cnt = item_orders.reindex(i_uni).to_numpy(dtype=float)
    a, b = np.nonzero(co)
    pair = co[a, b].astype(float)
    support = pair / n_orders
    confidence = pair / cnt[a]
    lift = confidence / (cnt[b] / n_orders)
    keep = (support >= min_support) & (confidence >= min_confidence)
    if not keep.any():
        info["message"] = "No rules met the support and confidence thresholds. Try lowering them."
        return empty, info
    names = np.asarray(i_uni, dtype=object)
    rules = pd.DataFrame({
        "Antecedent": names[a[keep]], "Consequent": names[b[keep]],
        "AntecedentOrders": cnt[a[keep]].astype(int), "ConsequentOrders": cnt[b[keep]].astype(int),
        "PairOrders": pair[keep].astype(int), "Support": support[keep],
        "Confidence": confidence[keep], "Lift": lift[keep],
    })
    rules = rules.sort_values(["Lift", "Support"], ascending=False).head(max_rules).reset_index(drop=True)
    return rules, info


# --------------------------------------------------------------------------
# Statistical comparison of order values across regions
# --------------------------------------------------------------------------
ASSUMPTIONS = [
    "Each order is one observation, and orders are treated as independent. Repeat orders from the same customer are not independent, so p-values may look more convincing than they should.",
    "Order values are usually heavily right-skewed, so rank-based tests (Mann-Whitney U / Kruskal-Wallis) are used instead of t-test / ANOVA. They do not assume normality.",
    "The tests compare whole distributions (typical rank), not exactly the average.",
    "With many orders, even tiny differences become 'significant'. Always read the effect size and the group medians too.",
    "This is observational data. A difference does not show what causes it.",
]


def _effect_label(eps: float) -> str:
    if eps < 0.01:
        return "negligible"
    if eps < 0.08:
        return "small"
    if eps < 0.26:
        return "moderate"
    return "large"


def compare_regions(df: pd.DataFrame, min_group_size: int = 30, max_groups: int = 10, alpha: float = 0.05) -> dict:
    """Compare order values between regions (Mann-Whitney U for 2 groups, Kruskal-Wallis for 3+)."""
    d = df.dropna(subset=["Country", "InvoiceNo"])
    if d.empty:
        return {"status": "insufficient", "message": "Region and order IDs are needed for this comparison."}
    orders = d.groupby(["InvoiceNo", "Country"], as_index=False)["Revenue"].sum()
    counts = orders.groupby("Country").size().sort_values(ascending=False)
    eligible = counts[counts >= min_group_size]
    if len(eligible) < 2:
        return {"status": "insufficient",
                "message": f"Need at least 2 regions with {min_group_size}+ orders each; found {len(eligible)}."}
    chosen = eligible.head(max_groups).index.tolist()
    orders = orders[orders["Country"].isin(chosen)]
    samples = [orders.loc[orders["Country"] == c, "Revenue"].to_numpy() for c in chosen]
    n_total = int(sum(len(s) for s in samples))

    if len(samples) == 2:
        res = stats.mannwhitneyu(samples[0], samples[1], alternative="two-sided")
        test, statistic, p = "Mann-Whitney U test", float(res.statistic), float(res.pvalue)
        effect_name = "Rank-biserial correlation"
        effect = float(2 * res.statistic / (len(samples[0]) * len(samples[1])) - 1)
        effect_text = _effect_label(abs(effect) ** 2)
    else:
        res = stats.kruskal(*samples)
        test, statistic, p = "Kruskal-Wallis H test", float(res.statistic), float(res.pvalue)
        effect_name = "Epsilon-squared"
        effect = max(0.0, float((statistic - len(samples) + 1) / (n_total - len(samples))))
        effect_text = _effect_label(effect)

    table = orders.groupby("Country")["Revenue"].agg(
        Orders="size", MedianOrderValue="median", MeanOrderValue="mean").reindex(chosen).reset_index()
    if p < alpha:
        interpretation = (
            f"The order-value distributions differ between these regions (p = {p:.3g}, below {alpha}). "
            f"The effect size is {effect_text}. This does not explain why the regions differ, "
            "and with many orders small differences can reach significance."
        )
    else:
        interpretation = (
            f"No statistically significant difference was detected (p = {p:.3g}, not below {alpha}). "
            "This does not prove the regions are the same; the data may simply be too limited to show a difference."
        )
    return {
        "status": "ok", "test": test, "statistic": statistic, "p_value": p,
        "effect_name": effect_name, "effect_size": effect, "effect_label": effect_text,
        "groups": len(chosen), "orders_compared": n_total,
        "excluded_regions": int(len(counts) - len(chosen)),
        "group_table": table, "order_values": orders[["Country", "Revenue"]],
        "interpretation": interpretation, "assumptions": ASSUMPTIONS,
    }
