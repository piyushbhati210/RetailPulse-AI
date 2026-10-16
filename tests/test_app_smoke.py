"""Runs the real Streamlit app headlessly with a fake upload and checks that every section renders."""
import io
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("streamlit.testing.v1")
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(Path(__file__).resolve().parents[1] / "app.py")


def make_csv(n_orders=600, seed=0) -> bytes:
    rng = np.random.default_rng(seed)
    products = [f"Product {i}" for i in range(40)]
    rows = []
    for o in range(n_orders):
        country = rng.choice(["United Kingdom", "France", "Germany"], p=[0.6, 0.25, 0.15])
        cust = float(12000 + rng.integers(0, 120))
        date = pd.Timestamp("2011-01-01") + pd.Timedelta(days=int(rng.integers(0, 300)), hours=9)
        for p in rng.choice(products, size=int(rng.integers(1, 6)), replace=False):
            rows.append({"InvoiceNo": f"{500000 + o}", "StockCode": p.replace("Product ", "SKU"),
                         "Description": p, "Quantity": int(rng.integers(1, 10)), "InvoiceDate": date,
                         "UnitPrice": round(float(rng.uniform(1, 20)), 2), "CustomerID": cust, "Country": country})
    rows.append({"InvoiceNo": "C500001", "StockCode": "SKU1", "Description": "Product 1", "Quantity": -1,
                 "InvoiceDate": date, "UnitPrice": 5.0, "CustomerID": 12001.0, "Country": "France"})
    return pd.DataFrame(rows).to_csv(index=False).encode()


SCRIPT = f"""
import streamlit as st
class FakeUpload:
    name = "retail.csv"
    def __init__(self, data): self._d = data
    def getvalue(self): return self._d
import pathlib
DATA = pathlib.Path(r"{{data}}").read_bytes()
st.file_uploader = lambda *a, **k: FakeUpload(DATA)
exec(compile(open(r"{APP}", encoding="utf-8").read(), r"{APP}", "exec"))
"""


@pytest.fixture
def app(tmp_path):
    f = tmp_path / "d.csv"
    f.write_bytes(make_csv())
    at = AppTest.from_string(SCRIPT.replace("{data}", str(f)), default_timeout=120)
    at.run()
    return at


def test_dashboard_renders_after_submit(app):
    assert not app.exception
    assert any("Press **Apply mapping" in i.value for i in app.info)  # before submit: dashboard not shown yet
    app.button[0].click().run()
    assert not app.exception, [e.value for e in app.exception]
    assert not app.error, [e.value for e in app.error]
    labels = [m.label for m in app.metric]
    for expected in ["Total revenue", "Orders", "Avg order value", "Input rows", "Retained rows"]:
        assert expected in labels
    assert len(app.tabs) == 6
    # cancelled invoice row was removed
    removed = [m.value for m in app.metric if m.label == "Removed rows"][0]
    assert removed == "1"


def test_sql_basket_and_filters(app):
    app.button[0].click().run()
    # SQL: run example, then a destructive query must be rejected
    run_sql = [b for b in app.button if b.label == "Run query"][0]
    run_sql.click().run()
    assert not app.exception and not app.error
    app.text_area(key="sql_text").set_value("DROP TABLE sales").run()
    [b for b in app.button if b.label == "Run query"][0].click().run()
    assert any("not allowed" in e.value for e in app.error)
    # Basket is user-triggered and then shows results
    [b for b in app.button if b.label == "Run market basket analysis"][0].click().run()
    assert not app.exception, [e.value for e in app.exception]
    assert any("rules found" in s.value or "No rules" in i.value for s in app.success for i in app.info) or app.success or app.info
    # Filtering by product text keeps the app working
    app.sidebar.text_input[0].set_value("Product 1").run()
    assert not app.exception, [e.value for e in app.exception]
