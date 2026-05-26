"""PTBot Streamlit Dashboard — deal database explorer and sweep launcher."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="PTBot — Deal Database",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Sidebar — global controls
# ---------------------------------------------------------------------------

st.sidebar.title("PTBot")
st.sidebar.caption("Precedent Transaction Database")

db_path_input = st.sidebar.text_input(
    "Database path",
    value="~/.ptbot/ptbot.db",
    help="Path to the SQLite deal database",
)
db_path = Path(db_path_input).expanduser()

page = st.sidebar.radio(
    "Navigate",
    ["📊 Dashboard", "🔍 Deal Browser", "🚀 Request Industries"],
)

st.sidebar.divider()
st.sidebar.caption(f"DB: `{db_path}`")
if db_path.exists():
    size_mb = db_path.stat().st_size / 1024 / 1024
    st.sidebar.caption(f"Size: {size_mb:.2f} MB")
else:
    st.sidebar.warning("Database not found")


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

@st.cache_data(ttl=30)
def load_deals(db_path_str: str) -> pd.DataFrame:
    """Load all deals joined with run params into a DataFrame."""
    conn = sqlite3.connect(db_path_str)
    df = pd.read_sql_query(
        """
        SELECT
            d.deal_id,
            d.target,
            d.acquirer,
            d.date,
            d.deal_value,
            d.multiples_disclosed,
            d.computed_multiples_available,
            d.multiples,
            d.source_urls,
            d.qualified,
            json_extract(r.params, '$.sector')     AS sector,
            json_extract(r.params, '$.geography')  AS geography,
            substr(json_extract(r.params, '$.start_date'), 1, 4) AS year
        FROM deals d
        JOIN runs r ON d.run_id = r.run_id
        ORDER BY d.date DESC
        """,
        conn,
    )
    conn.close()
    df["multiples_list"] = df["multiples"].apply(
        lambda x: json.loads(x) if x else []
    )
    df["source_list"] = df["source_urls"].apply(
        lambda x: json.loads(x) if x else []
    )
    df["year"] = df["year"].astype(str)
    df["qualified"] = df["qualified"].astype(bool)
    return df


@st.cache_data(ttl=30)
def load_runs(db_path_str: str) -> pd.DataFrame:
    """Load all run records."""
    conn = sqlite3.connect(db_path_str)
    df = pd.read_sql_query(
        """
        SELECT
            run_id,
            json_extract(params, '$.sector')     AS sector,
            json_extract(params, '$.geography')  AS geography,
            json_extract(params, '$.start_date') AS start_date,
            json_extract(params, '$.end_date')   AS end_date,
            timestamp
        FROM runs
        ORDER BY timestamp DESC
        """,
        conn,
    )
    conn.close()
    return df


# ---------------------------------------------------------------------------
# Page: Dashboard
# ---------------------------------------------------------------------------

def page_dashboard(df: pd.DataFrame) -> None:
    st.title("📊 Dashboard")

    if df.empty:
        st.info("No deals in the database yet. Use **Request Industries** to start a sweep.")
        return

    # KPI row
    total = len(df)
    qualified = df["qualified"].sum()
    sectors = df["sector"].nunique()
    years = df["year"].nunique()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Deals", f"{total:,}")
    c2.metric("Qualified (multiples)", f"{qualified:,}", f"{qualified/total*100:.0f}%")
    c3.metric("Sectors", sectors)
    c4.metric("Years Covered", years)

    st.divider()

    col_left, col_right = st.columns(2)

    # Deals by sector
    with col_left:
        st.subheader("Deals by Sector")
        sector_df = (
            df.groupby(["sector", "qualified"])
            .size()
            .reset_index(name="count")
        )
        sector_df["label"] = sector_df["qualified"].map(
            {True: "Qualified", False: "Unqualified"}
        )
        fig = px.bar(
            sector_df,
            x="sector",
            y="count",
            color="label",
            color_discrete_map={"Qualified": "#2563eb", "Unqualified": "#94a3b8"},
            barmode="stack",
            labels={"sector": "Sector", "count": "Deals", "label": ""},
        )
        fig.update_layout(legend=dict(orientation="h", y=-0.2), margin=dict(t=10))
        st.plotly_chart(fig, use_container_width=True)

    # Deals by year
    with col_right:
        st.subheader("Deals by Year")
        year_df = (
            df.groupby(["year", "qualified"])
            .size()
            .reset_index(name="count")
        )
        year_df["label"] = year_df["qualified"].map(
            {True: "Qualified", False: "Unqualified"}
        )
        fig2 = px.line(
            year_df[year_df["label"] == "Qualified"],
            x="year",
            y="count",
            color="sector" if "sector" in year_df.columns else None,
            markers=True,
            labels={"year": "Year", "count": "Qualified Deals"},
        )
        fig2.update_layout(margin=dict(t=10))
        st.plotly_chart(fig2, use_container_width=True)

    st.divider()

    # Qualification rate table
    st.subheader("Qualification Rate by Sector")
    qual_table = (
        df.groupby("sector")
        .agg(total=("deal_id", "count"), qualified=("qualified", "sum"))
        .assign(rate=lambda x: (x["qualified"] / x["total"] * 100).round(1))
        .sort_values("total", ascending=False)
        .reset_index()
    )
    qual_table.columns = ["Sector", "Total Deals", "Qualified", "Rate (%)"]
    st.dataframe(qual_table, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Page: Deal Browser
# ---------------------------------------------------------------------------

def page_deal_browser(df: pd.DataFrame) -> None:
    st.title("🔍 Deal Browser")

    if df.empty:
        st.info("No deals in the database yet.")
        return

    # Filters
    with st.expander("🔧 Filters", expanded=True):
        f1, f2, f3 = st.columns(3)

        with f1:
            sectors = ["All"] + sorted(df["sector"].dropna().unique().tolist())
            selected_sector = st.selectbox("Sector", sectors)

        with f2:
            years = sorted(df["year"].dropna().unique().tolist())
            selected_years = st.multiselect("Year", years, default=years)

        with f3:
            qual_filter = st.radio(
                "Multiples", ["All", "Qualified only", "Unqualified only"], horizontal=True
            )

        search = st.text_input("Search target / acquirer", placeholder="e.g. Acme, HealthTech")

    # Apply filters
    filtered = df.copy()
    if selected_sector != "All":
        filtered = filtered[filtered["sector"] == selected_sector]
    if selected_years:
        filtered = filtered[filtered["year"].isin(selected_years)]
    if qual_filter == "Qualified only":
        filtered = filtered[filtered["qualified"]]
    elif qual_filter == "Unqualified only":
        filtered = filtered[~filtered["qualified"]]
    if search:
        mask = (
            filtered["target"].str.contains(search, case=False, na=False)
            | filtered["acquirer"].str.contains(search, case=False, na=False)
        )
        filtered = filtered[mask]

    st.caption(f"Showing {len(filtered):,} of {len(df):,} deals")

    # Display table
    display_cols = ["target", "acquirer", "date", "deal_value", "sector", "year", "qualified"]
    display_df = filtered[display_cols].copy()
    display_df.columns = ["Target", "Acquirer", "Date", "Deal Value", "Sector", "Year", "Qualified"]

    selected_rows = st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
    )

    # Detail panel for selected row
    if selected_rows and selected_rows.selection.rows:
        idx = selected_rows.selection.rows[0]
        row = filtered.iloc[idx]
        st.divider()
        st.subheader(f"📋 {row['target']} — acquired by {row['acquirer']}")

        d1, d2, d3, d4 = st.columns(4)
        d1.metric("Date", row["date"] or "—")
        d2.metric("Deal Value", row["deal_value"] or "—")
        d3.metric("Sector", row["sector"] or "—")
        d4.metric("Qualified", "✅ Yes" if row["qualified"] else "❌ No")

        if row["multiples_list"]:
            st.markdown("**Multiples:**")
            for m in row["multiples_list"]:
                st.markdown(f"- {m}")
        else:
            st.caption("No multiples disclosed.")

        if row["source_list"]:
            st.markdown("**Sources:**")
            for url in row["source_list"]:
                st.markdown(f"- [{url}]({url})")


# ---------------------------------------------------------------------------
# Page: Request Industries
# ---------------------------------------------------------------------------

def page_request_industries() -> None:
    st.title("🚀 Request Industries")
    st.markdown(
        "Define a new set of markets to sweep. PTBot will fan out parallel agents "
        "to discover M&A transactions and persist results to the database."
    )

    with st.form("sweep_form"):
        st.subheader("Markets")

        raw_input = st.text_area(
            "Sectors (one per line)",
            placeholder="Cybersecurity\nEdTech\nInsurTech",
            height=150,
            help="Each line becomes one (sector, geography) sweep target.",
        )

        geography = st.text_input("Geography", value="United States")

        col1, col2 = st.columns(2)
        with col1:
            years_back = st.number_input(
                "Years back", min_value=1, max_value=20, value=10
            )
        with col2:
            max_workers = st.number_input(
                "Parallel runs", min_value=1, max_value=5, value=3
            )

        st.subheader("Execution")
        use_cloud = st.toggle("Use cloud agents (oz agent run-cloud)", value=True)
        environment_id = st.text_input(
            "Oz Environment ID (optional)",
            placeholder="fEBJDgnT6nfHXm6y2DjLGR",
            help="Leave blank to use cloud agents without a specific environment.",
        )

        db_path_form = st.text_input("Database path", value="~/.ptbot/ptbot.db")

        submitted = st.form_submit_button("Launch Sweep", type="primary")

    if not submitted:
        return

    sectors = [s.strip() for s in raw_input.splitlines() if s.strip()]
    if not sectors:
        st.error("Enter at least one sector.")
        return

    # Build TOML config
    markets_block = "\n".join(
        f'[[markets]]\nsector = "{s}"\ngeography = "{geography}"\n'
        for s in sectors
    )
    toml_content = f"""# PTBot sweep — generated from dashboard
[sweep]
years_back = {years_back}
db_path = "{db_path_form}"
output_base_dir = "./precedent-txn-output"
min_multiples = 1
timeout = 900
max_workers = {max_workers}
{"cloud_environment = \"" + environment_id + "\"" if environment_id else ""}

{markets_block}"""

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".toml", delete=False, prefix="ptbot-sweep-"
    ) as tmp:
        tmp.write(toml_content)
        config_path = tmp.name

    st.code(toml_content, language="toml")

    cmd = ["ptbot-sweep", "--config", config_path]
    if use_cloud:
        cmd += ["--cloud"]
    if environment_id:
        cmd += ["--environment", environment_id]

    st.markdown(f"**Command:** `{' '.join(cmd)}`")

    output_area = st.empty()
    log_lines: list[str] = []

    with st.spinner("Running sweep…"):
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            assert proc.stdout is not None
            for line in proc.stdout:
                log_lines.append(line.rstrip())
                output_area.code("\n".join(log_lines[-40:]), language="bash")
            proc.wait()
            if proc.returncode == 0:
                st.success("Sweep complete! Reload the Dashboard to see new deals.")
                st.cache_data.clear()
            else:
                st.error(f"Sweep exited with code {proc.returncode}.")
        except FileNotFoundError:
            st.error(
                "`ptbot-sweep` not found. Make sure PTBot is installed: "
                "`pip install -e .`"
            )


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

if not db_path.exists():
    if page != "🚀 Request Industries":
        st.warning(
            f"Database not found at `{db_path}`. "
            "Use **Request Industries** to run your first sweep."
        )

df_deals: pd.DataFrame = pd.DataFrame()
if db_path.exists():
    try:
        df_deals = load_deals(str(db_path))
    except Exception as exc:
        st.error(f"Failed to load database: {exc}")

if page == "📊 Dashboard":
    page_dashboard(df_deals)
elif page == "🔍 Deal Browser":
    page_deal_browser(df_deals)
elif page == "🚀 Request Industries":
    page_request_industries()
