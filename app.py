"""RetailPulse AI - Adaptive Retail Intelligence and Consumer Analytics.

Run with:  streamlit run app.py
"""
from __future__ import annotations

import hashlib
import html
import sqlite3
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from src import retailpulse as rp

APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "data" / "retailpulse.db"
NOT_AVAILABLE = "(not available)"

st.set_page_config(page_title="RetailPulse AI", page_icon="📊", layout="wide")
PALETTE = ["#4F8BF9", "#00C2A8", "#FFB000", "#FF6B6B", "#9B8CFF", "#5FD068"]

st.markdown(
    """
    <style>
    footer {visibility: hidden;}
    .block-container {padding-top: 2.2rem; max-width: 1400px;}
    section[data-testid="stSidebar"] {border-right: 1px solid rgba(128,128,128,0.2);}
    .rp-title {font-size: 2.3rem; font-weight: 800; line-height: 1.15;
        background: linear-gradient(90deg, #4F8BF9, #00C2A8); -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;}
    .rp-sub {opacity: 0.7; margin-bottom: 0.6rem;}
    .rp-chips {margin: 0.2rem 0 1.1rem 0;}
    .rp-chip {display: inline-block; padding: 4px 12px; margin: 0 8px 6px 0; border-radius: 999px;
        font-size: 0.82rem; background: rgba(79,139,249,0.14); border: 1px solid rgba(79,139,249,0.35);}
    div[data-testid="stMetric"] {
        background: linear-gradient(135deg, rgba(79,139,249,0.14), rgba(128,128,128,0.05));
        border: 1px solid rgba(128,128,128,0.22); border-left: 4px solid #4F8BF9;
        border-radius: 12px; padding: 14px 18px;}
    div[data-testid="stMetricLabel"] p {opacity: 0.75; font-size: 0.78rem; text-transform: uppercase;
        letter-spacing: 0.05em;}
    div[data-testid="stMetricValue"] {font-size: 1.85rem; font-weight: 700;}
    .rp-insight {border: 1px solid rgba(128,128,128,0.22); border-radius: 12px; padding: 12px 16px;
        background: rgba(128,128,128,0.06); margin: 0.9rem 0 0.4rem 0;}
    .rp-i-t {font-size: 0.78rem; opacity: 0.7;}
    .rp-i-v {font-size: 1.15rem; font-weight: 700; margin: 2px 0;}
    .rp-i-s {font-size: 0.82rem; opacity: 0.75;}
    button[data-baseweb="tab"] {font-weight: 600;}
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Cached helpers. Arguments starting with "_" are not hashed (too slow for big
# tables); a small string `key` identifies the data instead.
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner="Reading file...")
def load_file(file_bytes: bytes, filename: str):
    return rp.read_table(file_bytes, filename)


@st.cache_data(show_spinner="Validating and cleaning dataset...")
def clean_cached(_raw, file_sig: str, mapping_items: tuple, option_items: tuple):
    return rp.clean_dataset(_raw, dict(mapping_items), **dict(option_items))


@st.cache_data(show_spinner=False)
def kpis_cached(_df, key: str):
    return rp.compute_kpis(_df)


@st.cache_data(show_spinner=False)
def monthly_cached(_df, key: str):
    return rp.monthly_sales(_df)


@st.cache_data(show_spinner=False)
def products_cached(_df, key: str, n: int):
    return rp.top_products(_df, n)


@st.cache_data(show_spinner=False)
def countries_cached(_df, key: str):
    return rp.country_sales(_df)


@st.cache_data(show_spinner="Calculating RFM...")
def rfm_cached(_df, key: str):
    rfm = rp.compute_rfm(_df)
    return rfm, rp.rfm_segment_summary(rfm)


@st.cache_data(show_spinner="Running statistical test...")
def compare_cached(_df, key: str, min_group: int, max_groups: int):
    return rp.compare_regions(_df, min_group_size=min_group, max_groups=max_groups)


@st.cache_data(show_spinner="Preparing CSV...")
def csv_cached(_df, key: str):
    return _df.to_csv(index=False).encode("utf-8")


@st.cache_resource(show_spinner="Loading data into SQLite...")
def connection_cached(_df, key: str, persistent: bool):
    if persistent:
        DB_PATH.parent.mkdir(exist_ok=True)
        return rp.load_to_sqlite(_df, str(DB_PATH))
    return rp.load_to_sqlite(_df, ":memory:")


def show_chart(fig, height: int = 380):
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=50, b=10), showlegend=False)
    st.plotly_chart(fig, width="stretch")


def fmt_money(value) -> str:
    return "n/a" if value is None else f"{value:,.2f}"


def fmt_compact(value) -> str:
    """12,345,678 -> 12.35M so KPI cards never get cut off."""
    if value is None:
        return "n/a"
    a = abs(value)
    for div, suffix in ((1e9, "B"), (1e6, "M")):
        if a >= div:
            return f"{value / div:,.2f}{suffix}"
    return f"{value:,.0f}" if float(value).is_integer() else f"{value:,.2f}"


def fmt_int(value) -> str:
    return "n/a" if value is None else f"{value:,.0f}"


def fmt_p(p: float) -> str:
    return "< 0.0001" if p < 1e-4 else f"{p:.4f}"


# ---------------------------------------------------------------------------
# Header and upload
# ---------------------------------------------------------------------------
st.markdown(
    '<div class="rp-title">📊 RetailPulse AI</div>'
    '<div class="rp-sub">Adaptive retail intelligence and consumer analytics</div>',
    unsafe_allow_html=True,
)

with st.sidebar:
    st.subheader("Data")
    uploaded = st.file_uploader("Retail or sales file", type=["csv", "xlsx", "xls"])
    st.caption("Workflow: upload → map columns → validate → analyze → filter → export")

if uploaded is None:
    st.info("Upload a CSV or Excel file in the sidebar to begin.")
    st.markdown(
        "**What you can do here**\n"
        "- Upload any transaction-level retail file and map its columns\n"
        "- See revenue, orders, monthly trends, top products and regions\n"
        "- Run SQL queries (read-only) on the cleaned data\n"
        "- Segment customers with RFM, find products bought together, and compare regions\n"
        "- Filter the data and download it as CSV\n\n"
        "Your file needs a revenue column, **or** both quantity and unit price. "
        "Customer, product, date and region columns are optional; sections that need them switch off automatically."
    )
    st.stop()

file_bytes = uploaded.getvalue()
file_sig = hashlib.sha256(file_bytes).hexdigest() + "|" + uploaded.name
sig8 = file_sig[:8]

# A genuinely different file resets everything that belongs to the old file.
if st.session_state.get("file_sig") != file_sig:
    st.session_state["file_sig"] = file_sig
    st.session_state["active_mapping"] = None
    st.session_state["active_options"] = None
    st.session_state["basket"] = None
    st.session_state.pop("sql_text", None)

try:
    raw = load_file(file_bytes, uploaded.name)
except Exception as exc:  # noqa: BLE001 - show the real reason to the user
    st.error(f"Could not read the uploaded file: {exc}")
    st.stop()
if raw.empty:
    st.error("The uploaded file has no data rows.")
    st.stop()

# ---------------------------------------------------------------------------
# 1. Dataset overview
# ---------------------------------------------------------------------------
setup = st.expander("⚙️ Data setup: preview, column mapping and quality",
                   expanded=st.session_state.get("active_mapping") is None)

with setup:
    st.subheader("1. Dataset overview")
    c1, c2 = st.columns(2)
    c1.metric("Source rows", f"{len(raw):,}")
    c2.metric("Source columns", f"{raw.shape[1]:,}")
    with st.expander("Preview uploaded data and column names"):
        st.dataframe(raw.head(20), width="stretch")
        st.write("Original column names:", raw.columns.tolist())

    # ---------------------------------------------------------------------------
    # 2. Column mapping (a form, so all dropdowns are submitted together)
    # ---------------------------------------------------------------------------
    st.subheader("2. Map your columns")
    st.write("Check the suggested matches, change anything that is wrong, then press the button.")
    suggested = rp.detect_column_mapping(raw.columns)
    current = st.session_state.get("active_mapping") or suggested
    current_opts = st.session_state.get("active_options") or {}
    choices = [NOT_AVAILABLE] + list(raw.columns)

    with st.form("mapping_form"):
        grid = st.columns(2)
        picks = {}
        for i, field in enumerate(rp.CANONICAL_FIELDS):
            default = current.get(field)
            index = choices.index(default) if default in choices else 0
            picks[field] = grid[i % 2].selectbox(
                rp.FIELD_LABELS[field], choices, index=index, help=rp.FIELD_HELP[field], key=f"map_{sig8}_{field}"
            )
        st.markdown("**Cleaning rules** (turn off any rule that does not fit your data)")
        opt_dup = st.checkbox("Remove exact duplicate rows", value=current_opts.get("remove_duplicates", True),
                              key=f"opt_dup_{sig8}")
        opt_cancel = st.checkbox("Remove cancelled invoices (IDs like C536379)",
                                 value=current_opts.get("remove_cancellations", True), key=f"opt_cancel_{sig8}")
        opt_pos = st.checkbox("Remove rows with zero or negative quantity, price or revenue",
                              value=current_opts.get("remove_nonpositive", True), key=f"opt_pos_{sig8}")
        submitted = st.form_submit_button("Apply mapping and analyze", type="primary")

    if submitted:
        mapping = {f: c for f, c in picks.items() if c != NOT_AVAILABLE}
        problems = rp.validate_mapping(mapping, raw.columns)
        if problems:
            for p in problems:
                st.error(p)
        else:
            st.session_state["active_mapping"] = mapping
            st.session_state["active_options"] = {
                "remove_duplicates": opt_dup, "remove_cancellations": opt_cancel, "remove_nonpositive": opt_pos,
            }
            st.session_state["basket"] = None

mapping = st.session_state.get("active_mapping")
options = st.session_state.get("active_options")
if not mapping:
    st.info("Press **Apply mapping and analyze** to continue. The rest of the dashboard appears after that.")
    st.stop()

try:
    clean, quality = clean_cached(raw, file_sig, tuple(sorted(mapping.items())), tuple(sorted(options.items())))
except ValueError as exc:
    st.error(f"Cleaning failed: {exc}")
    st.stop()
except Exception as exc:  # noqa: BLE001
    st.error(f"Unexpected error while cleaning the data: {exc}")
    st.stop()

# ---------------------------------------------------------------------------
# 3. Validation report
# ---------------------------------------------------------------------------
with setup:
    st.subheader("3. Data quality")
    q1, q2, q3 = st.columns(3)
    q1.metric("Input rows", f"{quality['input_rows']:,}")
    q2.metric("Retained rows", f"{quality['retained_rows']:,}")
    q3.metric("Removed rows", f"{quality['removed_rows']:,}")
    with st.expander("Why were rows removed? What is available?"):
        st.table({
            "Reason": ["Exact duplicates", "Missing or non-numeric revenue", "Cancelled invoices",
                       "Zero / negative quantity, price or revenue"],
            "Rows removed": [quality["duplicates_removed"], quality["no_revenue_removed"],
                             quality["cancellations_removed"], quality["non_positive_removed"]],
        })
        if quality["invalid_dates_kept"]:
            st.warning(f"{quality['invalid_dates_kept']:,} rows have an unreadable date. They were kept but are "
                       "left out of date-based charts.")
        if quality["missing_customer_rows"] and quality["features"]["customers"]:
            st.info(f"{quality['missing_customer_rows']:,} retained rows have no customer ID. "
                    "They count in sales totals but not in RFM.")
        labels = {"sales": "Revenue", "orders": "Order IDs", "products": "Products", "dates": "Dates",
                  "customers": "Customer IDs", "countries": "Countries / regions",
                  "basket_analysis": "Market basket analysis", "rfm": "RFM segmentation"}
        st.write(" · ".join(f"{'✅' if quality['features'][k] else '❌'} {v}" for k, v in labels.items()))

if clean.empty:
    st.error("No rows are left after cleaning. Check the column mapping or switch off some cleaning rules.")
    st.stop()
features = quality["features"]
dk = hashlib.md5(repr((file_sig, sorted(mapping.items()), sorted(options.items()))).encode()).hexdigest()[:10]

# ---------------------------------------------------------------------------
# Sidebar filters
# ---------------------------------------------------------------------------
with st.sidebar:
    st.subheader("Filters")
    countries_filter = None
    if features["countries"]:
        all_countries = sorted(clean["Country"].dropna().unique().tolist())
        chosen = st.multiselect("Country / region", all_countries, default=[], placeholder="All countries",
                                key=f"country_{dk}")
        countries_filter = chosen or None
    date_filter = None
    if features["dates"]:
        dmin, dmax = clean["InvoiceDate"].min().date(), clean["InvoiceDate"].max().date()
        picked = st.date_input("Date range", value=(dmin, dmax), min_value=dmin, max_value=dmax, key=f"date_{dk}")
        if isinstance(picked, (tuple, list)) and len(picked) == 2:
            if (picked[0], picked[1]) != (dmin, dmax):
                date_filter = (picked[0], picked[1])
        else:
            st.caption("Pick an end date to apply the range.")
    product_query = ""
    if features["products"]:
        product_query = st.text_input("Product name or code contains", key=f"prod_{dk}")

filtered = rp.filter_data(clean, countries_filter, date_filter, product_query)
filter_key = repr((countries_filter, date_filter, product_query.strip().lower()))
data_key = f"{dk}|{hashlib.md5(filter_key.encode()).hexdigest()[:10]}"
with st.sidebar:
    st.caption(f"{len(filtered):,} of {len(clean):,} rows match the filters.")

if filtered.empty:
    st.warning("No rows match the current filters. Widen the filters in the sidebar.")
    st.stop()

# ---------------------------------------------------------------------------
# 4. Analysis
# ---------------------------------------------------------------------------
chips = [f"📄 {html.escape(uploaded.name)}", f"🧾 {len(filtered):,} of {len(clean):,} rows"]
if features["dates"]:
    chips.append(f"📅 {clean['InvoiceDate'].min():%d %b %Y} → {clean['InvoiceDate'].max():%d %b %Y}")
if len(filtered) != len(clean):
    chips.append("🔎 filters active")
st.markdown('<div class="rp-chips">' + "".join(f'<span class="rp-chip">{c}</span>' for c in chips) + "</div>",
            unsafe_allow_html=True)
tab_sales, tab_sql, tab_rfm, tab_basket, tab_stats, tab_export = st.tabs(
    ["📈 Sales", "🗄️ SQL", "👥 Customers (RFM)", "🧺 Market basket", "📐 Regional test", "⬇️ Export"]
)

# ----- Sales -----
with tab_sales:
    k = kpis_cached(filtered, data_key)
    m = st.columns(5)
    m[0].metric("Total revenue", fmt_compact(k["total_revenue"]), help=f"Exact: {k['total_revenue']:,.2f}")
    m[1].metric("Orders", fmt_compact(k["orders"]))
    m[2].metric("Avg order value", fmt_compact(k["avg_order_value"]))
    m[3].metric("Customers", fmt_compact(k["customers"]))
    m[4].metric("Units sold", fmt_compact(k["units"]))

    monthly = monthly_cached(filtered, data_key) if features["dates"] else None
    tp1 = products_cached(filtered, data_key, 1) if features["products"] else None
    cs_all = countries_cached(filtered, data_key) if features["countries"] else None
    total = k["total_revenue"] or 1
    cards = []
    if monthly is not None and not monthly.empty:
        best = monthly.loc[monthly["Revenue"].idxmax()]
        cards.append(("🏆 Best month", f"{best['Month']:%b %Y}", f"{fmt_compact(best['Revenue'])} revenue"))
    if tp1 is not None and not tp1.empty:
        r = tp1.iloc[0]
        cards.append(("🛍️ Top product", html.escape(str(r["Product"])), f"{r['Revenue'] / total:.1%} of revenue"))
    if cs_all is not None and not cs_all.empty:
        r = cs_all.iloc[0]
        cards.append(("🌍 Top region", html.escape(str(r["Country"])), f"{r['Revenue'] / total:.1%} of revenue"))
    if cards:
        for col, (title, value, sub) in zip(st.columns(len(cards)), cards):
            col.markdown(f'<div class="rp-insight"><div class="rp-i-t">{title}</div>'
                         f'<div class="rp-i-v">{value}</div><div class="rp-i-s">{sub}</div></div>',
                         unsafe_allow_html=True)

    if features["dates"]:
        if monthly.empty:
            st.info("No valid dates in the current selection, so no monthly trend is shown.")
        else:
            fig = px.area(monthly, x="Month", y="Revenue", markers=True, title="Monthly revenue",
                          hover_data={"Orders": True}, color_discrete_sequence=[PALETTE[0]])
            fig.update_traces(fillcolor="rgba(79,139,249,0.18)")
            last = filtered["InvoiceDate"].max()
            if len(monthly) > 1 and last.normalize() != (last + pd.offsets.MonthEnd(0)).normalize():
                fig.add_annotation(x=monthly["Month"].iloc[-1], y=monthly["Revenue"].iloc[-1],
                                   text=f"partial month (data ends {last:%d %b})", showarrow=True,
                                   arrowhead=2, ax=-60, ay=-40)
            show_chart(fig, height=400)
    else:
        st.info("Monthly trends need an order date column.")

    left, right = st.columns(2)
    with left:
        if features["products"]:
            top_n = st.slider("Top products to show", 5, 30, 10)
            tp = products_cached(filtered, data_key, top_n)
            fig = px.bar(tp.sort_values("Revenue"), x="Revenue", y="Product", orientation="h",
                         color_discrete_sequence=[PALETTE[1]],
                         title=f"Top {top_n} products by revenue", hover_data={"Units": True, "Orders": True})
            fig.update_yaxes(title=None)
            show_chart(fig, height=max(380, 26 * top_n + 120))
        else:
            st.info("Top products need a product name or code column.")
    with right:
        if features["countries"]:
            cs = countries_cached(filtered, data_key).head(15)
            fig = px.bar(cs, x="Country", y="Revenue", title="Revenue by country / region (top 15)",
                         color_discrete_sequence=[PALETTE[2]],
                         hover_data={"Orders": True})
            show_chart(fig)
        else:
            st.info("Regional comparison needs a country or region column.")

# ----- SQL -----
with tab_sql:
    st.subheader("SQL analytics")
    persistent = st.checkbox(f"Also save a persistent copy to data/{DB_PATH.name}", value=False,
                             help="Off = temporary in-memory database that disappears when the app stops.")
    st.caption(
        "Database: " + (f"**persistent file** `data/{DB_PATH.name}`" if persistent
                        else "**temporary, in memory** (disappears when the app stops)")
        + ". Table name: `sales`. It holds the whole cleaned dataset (the sidebar filters do not apply here; "
          "use WHERE in your query). Only read-only SELECT / WITH queries are accepted."
    )
    conn = connection_cached(clean, dk, persistent)
    try:
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({rp.SQL_TABLE})")]
        st.write("Columns:", ", ".join(cols))
    except sqlite3.Error:
        pass

    examples = rp.example_queries(features)

    def _load_example():
        st.session_state["sql_text"] = examples[st.session_state["sql_example"]]

    if "sql_text" not in st.session_state:
        st.session_state["sql_text"] = next(iter(examples.values()))
    st.selectbox("Example queries", list(examples), key="sql_example", on_change=_load_example)
    st.text_area("Your SQL", key="sql_text", height=200)
    if st.button("Run query", type="primary"):
        try:
            with st.spinner("Running query..."):
                result, truncated = rp.run_query(conn, st.session_state["sql_text"])
            st.success(f"{len(result):,} rows returned.")
            if truncated:
                st.warning("Only the first 5,000 rows are shown. Add LIMIT or a filter for a smaller result.")
            st.dataframe(result, width="stretch")
        except ValueError as exc:
            st.error(f"Query not allowed: {exc}")
        except sqlite3.Error as exc:
            st.error(f"SQL error: {exc}")

# ----- RFM -----
with tab_rfm:
    st.subheader("Customer segmentation (RFM)")
    if not features["rfm"]:
        missing = [name for flag, name in (("customers", "customer IDs"), ("orders", "order IDs"),
                                           ("dates", "valid order dates")) if not features[flag]]
        st.info("RFM is switched off because this dataset has no " + ", ".join(missing) + ".")
    else:
        with st.expander("What do R, F and M mean?"):
            st.markdown(
                "- **Recency**: days since the customer's last order (lower is better).\n"
                "- **Frequency**: number of distinct orders.\n"
                "- **Monetary**: total revenue from the customer.\n\n"
                "Each is scored 1-5 by percentile rank within the current selection (5 = best). "
                "Segments combine R and F scores, e.g. **Champions** = R≥4 and F≥4, "
                "**At Risk** = R≤2 but F≥3, **Hibernating** = R≤2 and F≤2. "
                "Recency is measured from one day after the latest order in the selection."
            )
        try:
            rfm, summary = rfm_cached(filtered, data_key)
        except ValueError as exc:
            st.warning(str(exc))
        else:
            a, b = st.columns(2)
            with a:
                fig = px.bar(summary, x="Segment", y="Customers", title="Customers per segment", color="Segment",
                             color_discrete_sequence=PALETTE)
                show_chart(fig)
            with b:
                fig = px.bar(summary, x="Segment", y="Revenue", title="Revenue per segment", color="Segment",
                             color_discrete_sequence=PALETTE,
                             hover_data={"RevenueShare": ":.1%"})
                show_chart(fig)
            st.dataframe(
                summary, width="stretch", hide_index=True,
                column_config={
                    "Revenue": st.column_config.NumberColumn(format="%.2f"),
                    "AvgRecencyDays": st.column_config.NumberColumn("Avg recency (days)", format="%.0f"),
                    "AvgOrders": st.column_config.NumberColumn("Avg orders", format="%.1f"),
                    "AvgSpend": st.column_config.NumberColumn("Avg spend", format="%.2f"),
                    "CustomerShare": st.column_config.NumberColumn("Customer share", format="percent"),
                    "RevenueShare": st.column_config.NumberColumn("Revenue share", format="percent"),
                },
            )
            with st.expander("Customer-level RFM table"):
                st.dataframe(rfm.sort_values("Monetary", ascending=False).head(1000), width="stretch",
                             hide_index=True)
                st.caption("Showing the top 1,000 customers by revenue.")

# ----- Market basket -----
with tab_basket:
    st.subheader("Market basket analysis")
    if not features["basket_analysis"]:
        st.info("Market basket analysis is switched off: it needs order IDs and product names or codes.")
    else:
        st.write("Finds products that appear in the same order. It runs only when you press the button.")
        s1, s2, s3 = st.columns(3)
        min_sup = s1.slider("Minimum support (% of orders)", 0.1, 5.0, 1.0, 0.1) / 100
        min_conf = s2.slider("Minimum confidence (%)", 5, 90, 20, 5) / 100
        top_items = s3.slider("Most frequent products to use", 20, 200, 100, 10)
        basket_key = f"{data_key}|{min_sup}|{min_conf}|{top_items}"
        if st.button("Run market basket analysis", type="primary"):
            try:
                with st.spinner("Finding product pairs..."):
                    rules, info = rp.market_basket(filtered, min_sup, min_conf, top_items)
                st.session_state["basket"] = {"key": basket_key, "rules": rules, "info": info}
            except ValueError as exc:
                st.session_state["basket"] = None
                st.error(str(exc))
        result = st.session_state.get("basket")
        if result and result["key"] == basket_key:
            info, rules = result["info"], result["rules"]
            st.caption(f"Orders analysed: {info['orders_used']:,}"
                       + (f" (random sample of {info['orders_total']:,})" if info["sampled"] else "")
                       + f" · products considered: {info['items_considered']:,}")
            if rules.empty:
                st.info(info["message"] or "No rules found.")
            else:
                st.success(f"{len(rules):,} rules found, sorted by lift.")
                st.dataframe(
                    rules, width="stretch", hide_index=True,
                    column_config={
                        "AntecedentOrders": "Orders with A", "ConsequentOrders": "Orders with B",
                        "PairOrders": "Orders with A and B",
                        "Support": st.column_config.NumberColumn(format="percent"),
                        "Confidence": st.column_config.NumberColumn(format="percent"),
                        "Lift": st.column_config.NumberColumn(format="%.2f"),
                    },
                )
                st.caption("Support: share of all orders containing both. Confidence: share of orders with A that "
                           "also contain B. Lift above 1 means A and B are bought together more often than chance "
                           "would suggest. These are co-occurrence patterns, not proof that one product causes "
                           "the purchase of the other.")
        elif result:
            st.info("Settings or filters changed since the last run. Press the button to update the results.")

# ----- Statistical comparison -----
with tab_stats:
    st.subheader("Order value across regions")
    if not (features["countries"] and features["orders"]):
        st.info("This test needs country / region and order ID columns.")
    else:
        t1, t2 = st.columns(2)
        min_group = t1.slider("Minimum orders per region", 10, 200, 30, 10)
        max_groups = t2.slider("Maximum regions to compare", 2, 15, 10)
        res = compare_cached(filtered, data_key, min_group, max_groups)
        if res["status"] != "ok":
            st.info(res["message"])
        else:
            st.markdown(f"**Test used:** {res['test']} on {res['groups']} regions "
                        f"({res['orders_compared']:,} orders).")
            r = st.columns(3)
            r[0].metric("Test statistic", f"{res['statistic']:,.2f}")
            r[1].metric("p-value", fmt_p(res["p_value"]))
            r[2].metric(res["effect_name"], f"{res['effect_size']:.3f}", help=f"Effect size: {res['effect_label']}")
            st.info(res["interpretation"])
            st.dataframe(res["group_table"], width="stretch", hide_index=True,
                         column_config={"MedianOrderValue": st.column_config.NumberColumn("Median order value", format="%.2f"),
                                        "MeanOrderValue": st.column_config.NumberColumn("Mean order value", format="%.2f")})
            fig = px.box(res["order_values"], x="Country", y="Revenue", log_y=True,
                         title="Order value distribution by region (log scale)", points=False,
                         color_discrete_sequence=PALETTE)
            show_chart(fig)
            if res["excluded_regions"]:
                st.caption(f"{res['excluded_regions']} regions were left out (too few orders or over the limit).")
            with st.expander("Assumptions and cautions"):
                for line in res["assumptions"]:
                    st.markdown(f"- {line}")

# ----- Export -----
with tab_export:
    st.subheader("Export cleaned data")
    st.write(f"{len(filtered):,} rows match the current filters.")
    st.dataframe(filtered.head(100), width="stretch")
    st.download_button("Download cleaned, filtered data (CSV)", data=csv_cached(filtered, data_key),
                       file_name="retailpulse_cleaned_filtered.csv", mime="text/csv", type="primary")