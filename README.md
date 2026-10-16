# RetailPulse AI — Adaptive Retail Intelligence and Consumer Analytics

🚀 **Live Demo:** [Open RetailPulse AI Dashboard](https://retailpulse-ai21.streamlit.app/)

An interactive retail analytics dashboard built with Python, Pandas, SQLite, SciPy, Plotly and Streamlit. Upload a retail transaction file (CSV/XLS/XLSX), map its columns, and explore sales, SQL, RFM customer segments, market baskets and regional order-value tests.


## Features
- **Flexible upload**: auto-detects column names (case-insensitive aliases) and lets you map them by hand in a form.
  Needs a revenue column, or both quantity and unit price. Customer, product, date and region columns are optional.
- **Transparent cleaning**: shows input / retained / removed rows and the reason. Duplicate, cancellation and
  non-positive-value rules can each be switched off.
- **Sales analytics**: revenue, orders, average order value, monthly trend, top products, revenue by country.
- **SQL**: cleaned data loaded into SQLite (table `sales`), example queries, read-only custom SQL
  (only one SELECT/WITH statement; the database is also opened with `PRAGMA query_only`).
  The database is temporary (in memory) unless you tick the persistent option (`data/retailpulse.db`).
- **RFM segmentation**: Recency / Frequency / Monetary scores and six segments, with sizes and revenue share.
- **Market basket**: pairwise association rules (support, confidence, lift). Runs only when you press the button.
- **Statistical test**: Mann-Whitney U (2 regions) or Kruskal-Wallis (3+) on order values, with p-value,
  effect size, group sizes and cautious wording.
- **Filters and export**: country, date range and product filters; download the cleaned, filtered CSV.

## Project structure
```
RetailPulse_AI_SQL_Upgrade/
├── app.py                  Streamlit interface
├── src/retailpulse.py      All analytics (no Streamlit code, easy to test)
├── tests/                  pytest unit tests + a headless app smoke test
├── data/                   Put your dataset here (and the optional SQLite file)
├── requirements.txt
└── pytest.ini
```

## Run it (Windows, VS Code, PowerShell)
Open the project folder in VS Code, then open a terminal (Terminal → New Terminal) and run:

```powershell
cd "D:\Piyush Work\RetailPulse_AI\RetailPulse_AI_SQL_Upgrade"
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m compileall app.py src tests
python -m pytest
streamlit run app.py
```
Then open http://localhost:8501 and upload `Online Retail.xlsx`.
If PowerShell blocks activation, run once: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.
The first load of the 540,000-row Excel file can take about a minute (reading .xlsx is slow); later steps are cached.

## Tested vs. not tested
Tested automatically (44 tests): column detection, cleaning counts, revenue calculation, optional columns,
filters, RFM, SQL safety and read-only behaviour, association-rule maths (checked against hand-calculated numbers),
statistical tests, and a headless run of the real app (upload → form submit → all tabs).
Timed on synthetic data of the same size as Online Retail (541,909 rows). Not tested: the real `Online Retail.xlsx`
file, other browsers, or Windows itself (tests ran on Linux).
This is an analytics dashboard, not a predictive model, so no accuracy metrics are reported.
