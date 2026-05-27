"""PTBot Streamlit Dashboard — deal database explorer and sweep launcher."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from . import db as _db
from .runners import kill_cloud_run

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
    ["📊 Dashboard", "🔍 Deal Browser", "🚀 Request Industries", "☁️ Cloud Control"],
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
            d.quality_signals,
            d.dedup_key,
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
    df["multiples_list"] = df["multiples"].apply(lambda x: json.loads(x) if x else [])
    df["source_list"] = df["source_urls"].apply(lambda x: json.loads(x) if x else [])
    df["year"] = df["year"].astype(str)
    df["qualified"] = df["qualified"].astype(bool)

    # Parse quality signals (quality-signals-001)
    def _parse_quality(qs: str | None) -> dict[str, Any]:
        if not qs:
            return {}
        try:
            data: Any = json.loads(qs)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    df["quality"] = df["quality_signals"].apply(_parse_quality)
    df["confidence"] = df["quality"].apply(
        lambda q: q.get("human_confidence_override") or q.get("overall_confidence") or "—"
    )
    df["has_human_override"] = df["quality"].apply(
        lambda q: bool(q.get("human_confidence_override"))
    )
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
            input_tokens,
            output_tokens,
            estimated_cost_usd,
            COALESCE(cost_model, 'oz-default') AS cost_model,
            timestamp
        FROM runs
        ORDER BY timestamp DESC
        """,
        conn,
    )
    conn.close()
    # Ensure numeric for cost math even on old schema rows
    for col in ("input_tokens", "output_tokens", "estimated_cost_usd"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
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
        sector_df = df.groupby(["sector", "qualified"]).size().reset_index(name="count")
        sector_df["label"] = sector_df["qualified"].map({True: "Qualified", False: "Unqualified"})
        fig = px.bar(
            sector_df,
            x="sector",
            y="count",
            color="label",
            color_discrete_map={"Qualified": "#2563eb", "Unqualified": "#94a3b8"},
            barmode="stack",
            labels={"sector": "Sector", "count": "Deals", "label": ""},
        )
        fig.update_layout(legend={"orientation": "h", "y": -0.2}, margin={"t": 10})
        st.plotly_chart(fig, use_container_width=True)

    # Deals by year
    with col_right:
        st.subheader("Deals by Year")
        year_df = df.groupby(["year", "qualified"]).size().reset_index(name="count")
        year_df["label"] = year_df["qualified"].map({True: "Qualified", False: "Unqualified"})
        fig2 = px.line(
            year_df[year_df["label"] == "Qualified"],
            x="year",
            y="count",
            color="sector" if "sector" in year_df.columns else None,
            markers=True,
            labels={"year": "Year", "count": "Qualified Deals"},
        )
        fig2.update_layout(margin={"t": 10})
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

    # --- Basic cost surface per vBRIEF ca-4 (non-breaking addition) ---
    st.divider()
    st.subheader("💰 Cost & Per-Industry Budget (cost-accounting-001)")
    try:
        runs_df = load_runs(str(db_path))  # cached (db_path from module sidebar)
    except Exception:
        runs_df = pd.DataFrame()
    if runs_df.empty or "estimated_cost_usd" not in runs_df.columns:
        st.caption("No cost data yet (runs before cost tracking or empty DB).")
    else:
        total_cost = float(runs_df["estimated_cost_usd"].sum())
        avg_cost = float(runs_df["estimated_cost_usd"].mean()) if len(runs_df) else 0.0
        run_count = len(runs_df)
        # Group by industry (sector+geo)
        runs_df["industry"] = runs_df["sector"].fillna("") + " / " + runs_df["geography"].fillna("")
        ind = (
            runs_df.groupby("industry")
            .agg(cost=("estimated_cost_usd", "sum"), runs=("run_id", "count"))
            .reset_index()
            .sort_values("cost", ascending=False)
        )
        over_budget = ind[ind["cost"] > 50.0]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Cost (all runs)", f"${total_cost:,.2f}")
        c2.metric("Runs Tracked", f"{run_count:,}")
        c3.metric("Avg Cost / Run", f"${avg_cost:,.2f}")
        c4.metric("Industries >$50", len(over_budget), delta_color="inverse")

        st.caption("Target: $50 per industry (sector + geography). Soft warnings in CLI/sweep.")
        if not ind.empty:
            st.dataframe(
                ind.assign(over=lambda x: x["cost"] > 50).rename(
                    columns={"industry": "Industry", "cost": "Cost (USD)", "runs": "Runs"}
                ),
                use_container_width=True,
                hide_index=True,
            )
        if not over_budget.empty:
            st.warning(f"{len(over_budget)} industry(ies) over the $50 soft target.")


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
        mask = filtered["target"].str.contains(search, case=False, na=False) | filtered[
            "acquirer"
        ].str.contains(search, case=False, na=False)
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

        # --- Structured Quality Signals + Human Feedback (quality-signals-001) ---
        st.markdown("### 🛡️ Quality & Confidence Signals")
        q = row.get("quality") or {}
        if q:
            eff = q.get("human_confidence_override") or q.get("overall_confidence", "—")
            score = q.get("confidence_score", "—")
            c1, c2 = st.columns(2)
            c1.metric("Effective Confidence", str(eff).upper())
            c2.metric(
                "Agent Score", f"{float(score):.2f}" if isinstance(score, (int, float)) else score
            )

            bd = q.get("breakdown", {})
            if bd:
                st.caption("Breakdown (QC criteria)")
                for k, v in bd.items():
                    if v:
                        st.markdown(f"- **{k.replace('_', ' ').title()}**: {v}")

            if q.get("citations"):
                st.markdown("**Quality Citations:** " + "; ".join(q.get("citations", [])[:3]))
            flags = q.get("flags", []) or []
            if flags:
                st.markdown("**Flags:** " + ", ".join(flags))
            tags = q.get("methodology_tags", []) or []
            if tags:
                st.markdown("**Methodology:** " + ", ".join(tags))
            if q.get("human_notes"):
                st.info(f"Human note: {q['human_notes']}")
        else:
            st.caption("No structured quality signals yet (pre-001 data or QC fallback).")

        # Human feedback form (persists override back to SQLite)
        with st.expander("✍️ Record Human Feedback / Override", expanded=False):
            fb_col1, fb_col2 = st.columns([1, 2])
            with fb_col1:
                new_conf = st.selectbox(
                    "Override Confidence",
                    ["(keep agent)", "HIGH", "MEDIUM", "LOW"],
                    index=0,
                    key=f"conf_{row['deal_id']}",
                )
            with fb_col2:
                new_notes = st.text_area(
                    "Notes (why the override?)",
                    value=q.get("human_notes", ""),
                    height=80,
                    key=f"notes_{row['deal_id']}",
                    placeholder="e.g. Verified vs 8-K; higher source quality.",
                )
            reviewer_name = st.text_input(
                "Reviewer", value="dashboard-user", key=f"rev_{row['deal_id']}"
            )
            if st.button("Save Human Override", key=f"save_{row['deal_id']}"):
                try:
                    override = None if new_conf == "(keep agent)" else new_conf
                    payload = dict(q)  # copy
                    if override:
                        payload["human_confidence_override"] = override
                    if new_notes.strip():
                        payload["human_notes"] = new_notes.strip()
                    if reviewer_name.strip():
                        payload["reviewer"] = reviewer_name.strip()
                    # ISO timestamp
                    from datetime import UTC, datetime

                    payload["reviewed_at"] = datetime.now(UTC).isoformat()

                    conn = sqlite3.connect(str(db_path))
                    conn.execute(
                        "UPDATE deals SET quality_signals = ? WHERE deal_id = ?",
                        (json.dumps(payload), row["deal_id"]),
                    )
                    conn.commit()
                    conn.close()
                    st.success("Feedback saved. Reload page or re-run query to see update.")
                    st.cache_data.clear()
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Failed to save feedback: {exc}")


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
            years_back = st.number_input("Years back", min_value=1, max_value=20, value=10)
        with col2:
            max_workers = st.number_input("Parallel runs", min_value=1, max_value=5, value=3)

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

    # Build TOML config (cloud line computed outside f-string to be Python 3.11 + black safe)
    markets_block = "\n".join(
        f'[[markets]]\nsector = "{s}"\ngeography = "{geography}"\n' for s in sectors
    )
    cloud_line = f'cloud_environment = "{environment_id}"' if environment_id else ""
    toml_content = f"""# PTBot sweep — generated from dashboard
[sweep]
years_back = {years_back}
db_path = "{db_path_form}"
output_base_dir = "./precedent-txn-output"
min_multiples = 1
timeout = 900
max_workers = {max_workers}
{cloud_line}

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
            st.error("`ptbot-sweep` not found. Make sure PTBot is installed: " "`pip install -e .`")


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

if not db_path.exists() and page != "🚀 Request Industries":
    st.warning(
        f"Database not found at `{db_path}`. " "Use **Request Industries** to run your first sweep."
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
elif page == "☁️ Cloud Control":
    page_cloud_control()


# ---------------------------------------------------------------------------
# Cloud Control Plane page (cloud-control-001)
# ---------------------------------------------------------------------------


def page_cloud_control() -> None:
    """Cloud execution control plane visibility + revocation.

    Shows the registry persisted in the DB (survives parent death).
    Active runs are prominent; kill buttons attempt oz revocation then
    mark the registry revoked.
    """
    st.title("☁️ Cloud Control Plane & Revocation")
    st.markdown(
        "Registry of every **oz agent run-cloud** dispatch. "
        "This table survives the death of the parent sweep, dashboard, or CLI process "
        "(the 2026-05 firedrill scenario). Use to observe and terminate orphan swarms."
    )

    db_str = str(db_path)
    try:
        conn = _db.open_db(db_path)
        runs = _db.list_cloud_runs(conn, active_only=False)
        conn.close()
    except Exception as exc:
        st.error(f"Failed to load cloud_runs registry: {exc}")
        return

    if not runs:
        st.info("No cloud agent runs recorded yet. Launch a sweep with --cloud or via the Request Industries form.")
        return

    active = [r for r in runs if r.get("status") in ("dispatched", "running")]
    terminal = [r for r in runs if r.get("status") not in ("dispatched", "running")]

    st.subheader(f"Active / In-Flight ({len(active)})")
    if active:
        for r in active:
            with st.container(border=True):
                cols = st.columns([3, 2, 2, 1])
                with cols[0]:
                    st.code(r["oz_run_id"], language=None)
                    st.caption(f"parent: {r.get('parent','')} | env: {r.get('environment','(default)')}")
                with cols[1]:
                    st.write(f"**status:** `{r['status']}`")
                    if r.get("dispatched_at"):
                        st.caption(f"dispatched: {r['dispatched_at'][:19]}")
                with cols[2]:
                    if r.get("cost_estimate_usd") is not None:
                        st.metric("Est. cost (USD)", f"${r['cost_estimate_usd']:.2f}")
                    if r.get("run_url"):
                        st.link_button("Open in Oz", r["run_url"], type="secondary")
                with cols[3]:
                    if st.button("KILL", key=f"kill_{r['oz_run_id']}", type="primary"):
                        with st.spinner("Revoking..."):
                            ok, msg = kill_cloud_run(r["oz_run_id"], r.get("run_url", ""))
                            st.write(msg)
                            if ok or st.session_state.get(f"force_{r['oz_run_id']}", False):
                                try:
                                    conn2 = _db.open_db(db_path)
                                    _db.mark_cloud_run_revoked(conn2, r["oz_run_id"])
                                    conn2.close()
                                    st.success("Marked revoked in registry.")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Registry update failed: {e}")
                            else:
                                st.warning("Use force below if the oz CLI surface is not yet available.")
                    if st.checkbox("force mark", key=f"force_{r['oz_run_id']}"):
                        pass
    else:
        st.caption("No active cloud runs.")

    with st.expander(f"Terminal / Historical ({len(terminal)})"):
        for r in terminal[:20]:  # bound
            st.write(
                f"{r['oz_run_id'][:16]}... | {r['status']} | {r.get('dispatched_at','')[:16]} "
                f"{'cost $' + str(round(r['cost_estimate_usd'],2)) if r.get('cost_estimate_usd') else ''}"
            )

    st.caption("Registry is the source of truth for cloud work. All --cloud dispatches (sweep + dashboard) are recorded here via the runners layer.")
