"""
BRN D-Fly Risk Manager
-----------------------
A local Streamlit app for stop-loss risk and Pearson-correlation-adjusted
portfolio risk across ICE Brent generic double-fly (D-fly) spreads.

Run with:
    streamlit run app.py
"""

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from pathlib import Path

st.set_page_config(page_title="BRN D-Fly Risk Manager", layout="wide")

DATA_FILE = Path(__file__).parent / "BRN_D_Flies_2018_2026.xlsx"


@st.cache_data
def load_data(file):
    df = pd.read_excel(file, sheet_name=0)
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date").reset_index(drop=True)
    return df


st.title("BRN D-Fly Risk Manager")
st.caption(
    "Stop-loss dollar risk and Pearson-correlation-adjusted portfolio risk "
    "across ICE Brent generic double-fly spreads."
)

# ---------------------------------------------------------------------------
# Data source
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Data source")
    uploaded = st.file_uploader(
        "Upload D-fly data (.xlsx) — optional, overrides the bundled file",
        type=["xlsx"],
    )
    st.caption(
        "By default the app loads BRN_D_Flies_2018_2026.xlsx from this folder."
    )

if uploaded is not None:
    df = load_data(uploaded)
elif DATA_FILE.exists():
    df = load_data(DATA_FILE)
else:
    st.warning("No data file found. Upload the BRN D-fly Excel file in the sidebar.")
    st.stop()

fly_cols = [c for c in df.columns if c != "Date"]
min_date, max_date = df["Date"].min().date(), df["Date"].max().date()

with st.sidebar:
    st.header("Dataset")
    st.write(f"**{len(df):,}** rows")
    st.write(f"**{min_date}** → **{max_date}**")
    st.write(f"**{len(fly_cols)}** generic D-flies")

# ---------------------------------------------------------------------------
# 1. Positions
# ---------------------------------------------------------------------------
st.header("1. Positions")
st.caption(
    "Add one row per position. Pick the generic D-fly from the dropdown, "
    "set entry/stop and lot size. Lots can be negative for a short. "
    "Use the ⋮ menu on a row, or the + at the bottom, to add / delete rows."
)

DEFAULT_POSITIONS = pd.DataFrame(
    [
        {
            "Fly": fly_cols[0],
            "Entry": 0.00,
            "Stop": 0.00,
            "Lots (+long/-short)": 1,
            "Tick Size": 0.01,
            "Tick Value ($)": 10.0,
        }
    ]
)

# NOTE: `value` is only used to seed the editor the very first time it runs
# for this `key`. After that, st.data_editor tracks all edits internally
# under st.session_state["positions_editor"] — do NOT also copy its output
# back into a separate session_state variable and feed that back in as
# `value`. Doing so creates a one-rerun lag where every edit needs to be
# entered twice before it registers.
edited = st.data_editor(
    DEFAULT_POSITIONS,
    num_rows="dynamic",
    use_container_width=True,
    column_config={
        "Fly": st.column_config.SelectboxColumn(
            "Generic D-Fly", options=fly_cols, required=True, default=fly_cols[0]
        ),
        "Entry": st.column_config.NumberColumn(
            "Entry Price", step=0.01, format="%.3f", default=0.0
        ),
        "Stop": st.column_config.NumberColumn(
            "Stop Price", step=0.01, format="%.3f", default=0.0
        ),
        "Lots (+long/-short)": st.column_config.NumberColumn(
            "Lots (+long/-short)", step=1, default=1
        ),
        "Tick Size": st.column_config.NumberColumn(
            "Tick Size", step=0.001, format="%.3f", default=0.01
        ),
        "Tick Value ($)": st.column_config.NumberColumn(
            "Tick Value ($)", step=1.0, default=10.0
        ),
    },
    key="positions_editor",
)

required_cols = ["Fly", "Entry", "Stop", "Lots (+long/-short)", "Tick Size", "Tick Value ($)"]
positions = edited.dropna(subset=required_cols).copy()
positions = positions[positions["Lots (+long/-short)"] != 0]
positions = positions[positions["Tick Size"] != 0]

incomplete = len(edited) - len(edited.dropna(subset=required_cols))
if incomplete > 0:
    st.caption(f"{incomplete} row(s) still have a blank field and are excluded until filled in.")

if positions.empty:
    st.info("Add at least one complete position above to see risk figures.")
    st.stop()

positions["SL Distance"] = (positions["Entry"] - positions["Stop"]).abs()
positions["Risk / Lot ($)"] = (
    positions["SL Distance"] / positions["Tick Size"] * positions["Tick Value ($)"]
)
positions["Signed $ Risk"] = positions["Lots (+long/-short)"] * positions["Risk / Lot ($)"]
positions["$ Risk (abs)"] = positions["Signed $ Risk"].abs()

st.dataframe(
    positions[
        [
            "Fly",
            "Entry",
            "Stop",
            "Lots (+long/-short)",
            "SL Distance",
            "Risk / Lot ($)",
            "Signed $ Risk",
        ]
    ].style.format(
        {
            "Entry": "{:.3f}",
            "Stop": "{:.3f}",
            "SL Distance": "{:.3f}",
            "Risk / Lot ($)": "${:,.0f}",
            "Signed $ Risk": "${:,.0f}",
        }
    ),
    use_container_width=True,
)

sum_abs_risk = positions["$ Risk (abs)"].sum()
c1, c2 = st.columns(2)
c1.metric("Total Stop-Loss Dollar Risk (undiversified)", f"${sum_abs_risk:,.0f}")
c2.metric("Net Signed $ Exposure", f"${positions['Signed $ Risk'].sum():,.0f}")

st.divider()

# ---------------------------------------------------------------------------
# 2. Correlation window
# ---------------------------------------------------------------------------
st.header("2. Correlation-Adjusted Portfolio Risk")

cc1, cc2 = st.columns([2, 1])
with cc1:
    date_range = st.date_input(
        "Correlation lookback window",
        value=(max(min_date, max_date - pd.Timedelta(days=30)), max_date),
        min_value=min_date,
        max_value=max_date,
    )
with cc2:
    use_changes = st.checkbox(
        "Use day-over-day changes instead of price levels",
        value=False,
        help=(
            "Off (default): Pearson correlation of the raw D-fly price levels "
            "over the window, as requested. On: correlation of daily changes, "
            "a common alternative for already-mean-reverting spread series."
        ),
    )

if len(date_range) != 2:
    st.stop()
start_date, end_date = date_range

window = df[(df["Date"].dt.date >= start_date) & (df["Date"].dt.date <= end_date)]
if len(window) < 3:
    st.warning("Selected window has fewer than 3 observations — widen the date range.")
    st.stop()

legs_flies = positions["Fly"].tolist()
unique_flies = sorted(set(legs_flies))

series = window[unique_flies]
if use_changes:
    series = series.diff().dropna()

corr_unique = series.corr(method="pearson")

# Build the full n x n correlation matrix, one row/col per POSITION (not per
# unique fly) — so two positions in the same fly correctly show corr = 1,
# and the matrix aligns 1:1 with the signed risk vector below.
n = len(positions)
C = np.ones((n, n))
for i in range(n):
    for j in range(n):
        C[i, j] = corr_unique.loc[legs_flies[i], legs_flies[j]]

R = positions["Signed $ Risk"].to_numpy().reshape(-1, 1)

variance = float((R.T @ C @ R).item())
corr_adj_risk = float(np.sqrt(max(variance, 0.0)))
ratio = corr_adj_risk / sum_abs_risk if sum_abs_risk > 0 else 0.0

m1, m2, m3 = st.columns(3)
m1.metric("Naive Sum $ Risk (no correlation)", f"${sum_abs_risk:,.0f}")
m2.metric("Correlation-Adjusted $ Risk", f"${corr_adj_risk:,.0f}",
          delta=f"{corr_adj_risk - sum_abs_risk:,.0f}", delta_color="inverse")
m3.metric("Portfolio Correlation Risk (0–1)", f"{ratio:.2f}")

st.caption(
    "Correlation-adjusted risk = √(Rᵀ · C · R), where R is the vector of each "
    "position's signed stop-loss dollar risk (long +, short −) and C is the "
    "Pearson correlation matrix of the selected D-flies over the chosen window. "
    "Because R is signed, a position that's long one fly and short a highly "
    "correlated fly nets down toward zero risk; two positions on the same side "
    "of correlated flies stack up toward the naive sum."
)

with st.expander("Show correlation matrix (unique D-flies in this portfolio)"):
    fig = px.imshow(
        corr_unique,
        text_auto=".2f",
        color_continuous_scale="RdBu",
        zmin=-1,
        zmax=1,
        aspect="auto",
    )
    fig.update_layout(height=400 + 20 * len(unique_flies))
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        f"Pearson correlation over {start_date} → {end_date} "
        f"({len(series)} observations), "
        f"{'daily changes' if use_changes else 'price levels'}."
    )

with st.expander("Show risk vector R and full leg-level correlation matrix C"):
    st.write("**R — signed $ risk per position**")
    st.dataframe(
        pd.DataFrame(
            {"Fly": legs_flies, "Signed $ Risk": R.flatten()}
        ).style.format({"Signed $ Risk": "${:,.0f}"}),
        use_container_width=True,
    )
    st.write("**C — position-level correlation matrix**")
    st.dataframe(
        pd.DataFrame(C, index=legs_flies, columns=legs_flies).style.format("{:.2f}"),
        use_container_width=True,
    )