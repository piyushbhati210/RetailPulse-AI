import sqlite3

import numpy as np
import pandas as pd
import pytest

from src import retailpulse as rp

FULL_MAP = {
    "InvoiceNo": "InvoiceNo", "StockCode": "StockCode", "Description": "Description",
    "Quantity": "Quantity", "InvoiceDate": "InvoiceDate", "UnitPrice": "UnitPrice",
    "CustomerID": "CustomerID", "Country": "Country",
}


def raw_retail():
    return pd.DataFrame({
        "InvoiceNo": [1001, 1001, 1002, "C1003", 1004, 1005, 1005, 1006],
        "StockCode": ["A1", "B2", "A1", "A1", "B2", "A1", "A1", "C3"],
        "Description": ["Mug", "Plate", "Mug", "Mug", "Plate", "Mug", "Mug", "Bowl"],
        "Quantity": [2, 1, 3, -1, 0, 4, 4, 5],
        "InvoiceDate": ["2024-01-05", "2024-01-05", "2024-01-20", "2024-02-01",
                        "2024-02-03", "2024-02-10", "2024-02-10", "not a date"],
        "UnitPrice": [5.0, 10.0, 5.0, 5.0, 10.0, 5.0, 5.0, 2.0],
        "CustomerID": [1.0, 1.0, 2.0, 2.0, 3.0, 3.0, 3.0, None],
        "Country": ["UK", "UK", "FR", "FR", "UK", "FR", "FR", "UK"],
    })


# ---------------- column mapping ----------------
def test_detect_mapping_is_case_insensitive_and_alias_based():
    cols = ["Order ID", "SKU", "Product Name", "QTY", "Order Date", "Price", "Client ID", "Region"]
    m = rp.detect_column_mapping(cols)
    assert m["InvoiceNo"] == "Order ID"
    assert m["StockCode"] == "SKU"
    assert m["Description"] == "Product Name"
    assert m["Quantity"] == "QTY"
    assert m["InvoiceDate"] == "Order Date"
    assert m["UnitPrice"] == "Price"
    assert m["CustomerID"] == "Client ID"
    assert m["Country"] == "Region"


def test_a_column_is_never_mapped_twice():
    m = rp.detect_column_mapping(["Sales", "Price"])
    assert len(set(m.values())) == len(m)


def test_validate_mapping_requires_revenue_or_qty_and_price():
    assert rp.validate_mapping({"Quantity": "q"}, ["q"])
    assert rp.validate_mapping({"Revenue": "r"}, ["r"]) == []
    assert rp.validate_mapping({"Quantity": "q", "UnitPrice": "p"}, ["q", "p"]) == []
    assert rp.validate_mapping({"Revenue": "missing"}, ["r"])
    assert rp.validate_mapping({"Revenue": "r", "Quantity": "r"}, ["r"])  # same column twice


# ---------------- cleaning ----------------
def test_clean_counts_and_revenue_calculation():
    clean, q = rp.clean_dataset(raw_retail(), FULL_MAP)
    assert q["input_rows"] == 8
    assert q["duplicates_removed"] == 1
    assert q["cancellations_removed"] == 1
    assert q["non_positive_removed"] == 1  # quantity 0 row
    assert q["retained_rows"] + q["removed_rows"] == q["input_rows"]
    assert q["retained_rows"] == len(clean) == 5
    row = clean[(clean["InvoiceNo"] == "1001") & (clean["StockCode"] == "A1")].iloc[0]
    assert row["Revenue"] == pytest.approx(10.0)  # 2 x 5.0
    assert q["invalid_dates_kept"] == 1
    assert clean["CustomerID"].dropna().iloc[0] == "1"  # '1.0' becomes '1'


def test_cleaning_options_can_be_switched_off():
    clean, q = rp.clean_dataset(raw_retail(), FULL_MAP, remove_duplicates=False,
                                remove_cancellations=False, remove_nonpositive=False)
    assert q["removed_rows"] == 0 and len(clean) == 8


def test_revenue_column_only_and_missing_optional_columns():
    raw = pd.DataFrame({"Sales": ["$1,200.50", "300", "bad", None], "Mkt": ["US", "US", "UK", "DE"]})
    clean, q = rp.clean_dataset(raw, {"Revenue": "Sales", "Country": "Mkt"})
    assert clean["Revenue"].tolist() == [1200.5, 300.0]
    assert q["no_revenue_removed"] == 2
    f = q["features"]
    assert f["countries"] and not f["customers"] and not f["orders"] and not f["rfm"]
    assert not f["basket_analysis"] and not f["dates"]


def test_alternative_column_names_end_to_end():
    raw = pd.DataFrame({"Order ID": ["a", "b"], "Product": ["x", "y"], "Qty": [2, 3], "Price": [1.5, 2.0]})
    m = rp.detect_column_mapping(raw.columns)
    clean, _ = rp.clean_dataset(raw, m)
    assert clean["Revenue"].tolist() == [3.0, 6.0]


def test_invalid_mapping_raises():
    with pytest.raises(ValueError):
        rp.clean_dataset(raw_retail(), {"Quantity": "Quantity"})


def test_read_table_csv_and_semicolon():
    assert rp.read_table(b"a,b\n1,2\n", "x.csv").shape == (1, 2)
    assert rp.read_table(b"a;b\n1;2\n", "x.csv").shape == (1, 2)
    with pytest.raises(ValueError):
        rp.read_table(b"abc", "x.txt")


# ---------------- analytics and filters ----------------
@pytest.fixture
def clean():
    return rp.clean_dataset(raw_retail(), FULL_MAP)[0]


def test_kpis_and_tables(clean):
    k = rp.compute_kpis(clean)
    assert k["total_revenue"] == pytest.approx(clean["Revenue"].sum())
    assert k["orders"] == clean["InvoiceNo"].nunique()
    assert k["avg_order_value"] == pytest.approx(k["total_revenue"] / k["orders"])
    assert rp.monthly_sales(clean)["Revenue"].sum() <= k["total_revenue"] + 1e-9
    assert rp.top_products(clean, 2).iloc[0]["Product"] in {"Mug", "Plate", "Bowl"}
    assert set(rp.country_sales(clean)["Country"]) <= {"UK", "FR"}


def test_filters(clean):
    assert set(rp.filter_data(clean, countries=["FR"])["Country"]) == {"FR"}
    assert rp.filter_data(clean, countries=[]).empty
    f = rp.filter_data(clean, date_range=("2024-01-01", "2024-01-31"))
    assert f["InvoiceDate"].dt.month.eq(1).all() and not f.empty
    assert set(rp.filter_data(clean, product_query="mug")["Description"]) == {"Mug"}
    assert rp.filter_data(clean, product_query="zzz").empty
    assert len(rp.filter_data(clean)) == len(clean)


def test_empty_dataframe_does_not_crash(clean):
    empty = clean.iloc[0:0]
    assert rp.compute_kpis(empty)["total_revenue"] == 0.0
    assert rp.monthly_sales(empty).empty
    assert rp.top_products(empty).empty
    assert rp.country_sales(empty).empty


# ---------------- RFM ----------------
def rfm_frame():
    rows = []
    base = pd.Timestamp("2024-01-01")
    for i in range(10):  # customer i: (i+1) orders, more recent for bigger i
        for j in range(i + 1):
            rows.append({"CustomerID": f"c{i}", "InvoiceNo": f"o{i}_{j}",
                         "InvoiceDate": base + pd.Timedelta(days=i * 10 + j), "Revenue": 10.0 * (i + 1)})
    return pd.DataFrame(rows)


def test_rfm_values_and_segments():
    df = rfm_frame()
    rfm = rp.compute_rfm(df)
    assert len(rfm) == 10
    assert rfm["Monetary"].sum() == pytest.approx(df["Revenue"].sum())
    top = rfm[rfm["CustomerID"] == "c9"].iloc[0]
    low = rfm[rfm["CustomerID"] == "c0"].iloc[0]
    assert top["Frequency"] == 10 and top["Segment"] == "Champions"
    assert low["Frequency"] == 1 and low["Segment"] == "Hibernating"
    assert top["Recency"] < low["Recency"]
    summary = rp.rfm_segment_summary(rfm)
    assert summary["Customers"].sum() == 10
    assert summary["RevenueShare"].sum() == pytest.approx(1.0)


def test_rfm_needs_data():
    with pytest.raises(ValueError):
        rp.compute_rfm(rfm_frame().iloc[:3])  # fewer than 5 customers
    with pytest.raises(ValueError):
        rp.compute_rfm(rfm_frame().assign(CustomerID=None))


# ---------------- SQL safety ----------------
@pytest.mark.parametrize("sql", [
    "SELECT * FROM sales", "select 1;", "WITH x AS (SELECT 1) SELECT * FROM x",
    "SELECT * FROM sales WHERE Description LIKE '%update%'",
    "SELECT replace(Description, 'a', 'b') FROM sales",
    "SELECT '--' AS dash",
])
def test_sql_allowed(sql):
    assert rp.validate_sql(sql)[0]


@pytest.mark.parametrize("sql", [
    "", "   ", "DROP TABLE sales", "DELETE FROM sales", "UPDATE sales SET Revenue = 0",
    "INSERT INTO sales VALUES (1)", "CREATE TABLE x (a int)", "ATTACH DATABASE 'x' AS y",
    "PRAGMA query_only = OFF", "SELECT 1; DROP TABLE sales",
    "WITH x AS (SELECT 1) DELETE FROM sales", "SELECT '--'; DROP TABLE sales",
    "/* hi */ DROP TABLE sales", "REPLACE INTO sales VALUES (1)", "EXPLAIN SELECT 1",
])
def test_sql_rejected(sql):
    assert not rp.validate_sql(sql)[0]


def test_sqlite_load_query_and_read_only(clean):
    conn = rp.load_to_sqlite(clean)
    df, truncated = rp.run_query(conn, "SELECT COUNT(*) AS n, SUM(Revenue) AS r FROM sales")
    assert df.loc[0, "n"] == len(clean) and not truncated
    assert df.loc[0, "r"] == pytest.approx(clean["Revenue"].sum())
    ym, _ = rp.run_query(conn, "SELECT DISTINCT YearMonth FROM sales WHERE YearMonth IS NOT NULL")
    assert not ym.empty
    # even if validation were bypassed, the database itself refuses writes
    with pytest.raises(sqlite3.Error):
        conn.execute("DELETE FROM sales")
    with pytest.raises(ValueError):
        rp.run_query(conn, "DELETE FROM sales")
    with pytest.raises(sqlite3.Error):
        rp.run_query(conn, "SELECT nope FROM sales")
    limited, truncated = rp.run_query(conn, "SELECT * FROM sales", max_rows=2)
    assert len(limited) == 2 and truncated


def test_example_queries_run(clean):
    feats = rp.clean_dataset(raw_retail(), FULL_MAP)[1]["features"]
    conn = rp.load_to_sqlite(clean)
    ex = rp.example_queries(feats)
    assert {"Sales summary", "Monthly sales", "Top 10 products", "Regional performance", "Repeat customers"} <= set(ex)
    for sql in ex.values():
        rp.run_query(conn, sql)


# ---------------- market basket ----------------
def basket_frame():
    rows, n = [], 0
    for items, times in ((("A", "B"), 40), (("A",), 30), (("C",), 20), (("B", "C"), 10)):
        for _ in range(times):
            n += 1
            rows += [{"InvoiceNo": f"o{n}", "Description": it, "StockCode": it} for it in items]
    return pd.DataFrame(rows)


def test_market_basket_metrics_are_correct():
    rules, info = rp.market_basket(basket_frame(), min_support=0.05, min_confidence=0.1)
    assert info["orders_used"] == 100
    ab = rules[(rules["Antecedent"] == "A") & (rules["Consequent"] == "B")].iloc[0]
    assert ab["Support"] == pytest.approx(0.40)
    assert ab["Confidence"] == pytest.approx(40 / 70)
    assert ab["Lift"] == pytest.approx((40 / 70) / 0.5)
    bc = rules[(rules["Antecedent"] == "B") & (rules["Consequent"] == "C")].iloc[0]
    assert bc["Lift"] == pytest.approx(0.2 / 0.3)
    assert rules["Lift"].is_monotonic_decreasing


def test_market_basket_empty_cases():
    rules, info = rp.market_basket(basket_frame(), min_support=0.9, min_confidence=0.9)
    assert rules.empty and info["message"]
    rules, info = rp.market_basket(basket_frame().head(6))
    assert rules.empty and "Not enough orders" in info["message"]
    with pytest.raises(ValueError):
        rp.market_basket(pd.DataFrame({"InvoiceNo": [None], "Description": [None], "StockCode": [None]}))


# ---------------- statistics ----------------
def region_frame(shift=0.0, n=60, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for country, mult in (("UK", 1.0), ("FR", 1.0 + shift)):
        for i in range(n):
            rows.append({"InvoiceNo": f"{country}{i}", "Country": country,
                         "Revenue": float(rng.lognormal(3, 0.5) * mult)})
    return pd.DataFrame(rows)


def test_compare_regions_detects_difference():
    big = rp.compare_regions(region_frame(shift=2.0))
    assert big["status"] == "ok" and big["p_value"] < 0.001 and big["groups"] == 2
    assert big["group_table"]["Orders"].tolist() == [60, 60]
    assert "differ" in big["interpretation"]


def test_compare_regions_no_difference_is_worded_cautiously():
    same = rp.compare_regions(region_frame(shift=0.0, seed=1))
    assert same["status"] == "ok"
    if same["p_value"] >= 0.05:
        assert "No statistically significant" in same["interpretation"]


def test_compare_regions_three_groups_and_insufficient():
    third = region_frame(0.0, seed=3).assign(Country="DE")
    third["InvoiceNo"] = "D" + third["InvoiceNo"]
    res = rp.compare_regions(pd.concat([region_frame(0.5), third]))
    assert res["test"].startswith("Kruskal") and res["groups"] == 3
    assert rp.compare_regions(region_frame(n=5))["status"] == "insufficient"
    empty = pd.DataFrame({"InvoiceNo": [], "Country": [], "Revenue": []})
    assert rp.compare_regions(empty)["status"] == "insufficient"
