import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from finagent.state import PortfolioStore  # noqa: E402

st.set_page_config(page_title="FinAgent Portfolio Lab", layout="wide")
st.title("FinAgent Portfolio Lab")
st.caption("Research and paper simulation only. Not investment advice.")

ARTIFACTS = Path("artifacts")

runs = sorted(ARTIFACTS.glob("run-*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
if not runs:
    st.info("Run `finagent decide` to create an auditable decision artifact.")
    st.stop()

data = json.loads(runs[0].read_text(encoding="utf-8"))
decision = data["decision"]

overview, holdings, history, backtest_tab, views_tab = st.tabs(
    ["Overview", "Holdings", "Decision history", "Backtest", "Agent views"]
)

with overview:
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Latest action", decision["action"])
    col2.metric("Net improvement (bps)", f"{decision['net_improvement_bps']:.1f}")
    col3.metric("Est. cost (bps)", f"{decision['estimated_transaction_cost_bps']:.1f}")
    col4.metric("Weekly turnover", f"{decision['weekly_turnover']:.2%}")
    st.write(f"Week #{data.get('week_number', '?')} · universe `{data.get('universe_version')}`")
    st.write("Reason codes:", ", ".join(f"`{code}`" for code in decision["reason_codes"]))
    if data.get("thesis_statuses"):
        weakened = {s: t for s, t in data["thesis_statuses"].items() if t != "intact"}
        if weakened:
            st.warning(f"Theses needing attention: {weakened}")
    with st.expander("Raw decision JSON"):
        st.json(decision)

with holdings:
    left, right = st.columns(2)
    applied = data.get("applied", data["candidate"])
    current_weights = pd.Series(data["current"]["weights"], name="current")
    applied_weights = pd.Series(applied["weights"], name="applied")
    frame = pd.concat([current_weights, applied_weights], axis=1).fillna(0.0)
    left.subheader("Weights: current vs applied")
    left.bar_chart(frame)
    right.subheader("Applied portfolio")
    right.dataframe(
        frame.sort_values("applied", ascending=False).style.format("{:.2%}"),
        use_container_width=True,
    )

with history:
    state_file = ARTIFACTS / "portfolio.sqlite"
    if state_file.exists():
        records = PortfolioStore(str(state_file)).decision_history(52)
        if records:
            table = pd.DataFrame(
                [
                    {
                        "week": item["week_number"],
                        "as_of": item["as_of"][:10],
                        "action": item["action"],
                        "turnover": item["weekly_turnover"],
                        "net_improvement_bps": item["net_improvement_bps"],
                        "cost_bps": item["estimated_cost_bps"],
                        "reasons": ", ".join(item["reason_codes"]),
                    }
                    for item in records
                ]
            )
            st.dataframe(table, use_container_width=True)
            st.bar_chart(table.set_index("week")["turnover"])
        else:
            st.info("No decisions recorded yet.")
    else:
        st.info("State database not found; run `finagent decide` first.")

with backtest_tab:
    report_file = Path("artifacts/backtest/backtest-report.json")
    if report_file.exists():
        report = json.loads(report_file.read_text(encoding="utf-8"))
        metrics = report["metrics"]
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Cumulative return", f"{metrics['cumulative_return']:.2%}")
        col2.metric("Sharpe", f"{metrics['sharpe']:.2f}")
        col3.metric("Max drawdown", f"{metrics['max_drawdown']:.2%}")
        col4.metric("HOLD ratio", f"{metrics['hold_ratio']:.0%}")
        curve = pd.DataFrame(report["equity_curve"])
        if not curve.empty:
            st.line_chart(curve.set_index("as_of")["equity"])
            st.bar_chart(curve.set_index("as_of")["turnover"])
        st.write("Actions:", report["actions"])
    else:
        st.info("Run `finagent backtest` to generate a pipeline-driven backtest report.")

with views_tab:
    st.subheader("Aggregated views")
    aggregated = pd.DataFrame(data["aggregated_views"]).T
    if not aggregated.empty:
        st.dataframe(
            aggregated[["score", "confidence", "disagreement", "contributors"]],
            use_container_width=True,
        )
    st.subheader(f"Evidence items: {len(data.get('evidence', []))}")
    with st.expander("Agent views (raw)"):
        st.json(data["agent_views"])
