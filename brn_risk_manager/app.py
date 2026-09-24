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


st.title(" Risk Manager")
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

POSITIONS_FILE = Path(__file__).parent / "saved_positions.csv"

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

# Seed the editor from a previously-saved file if one exists (so positions
# survive an app restart), falling back to the built-in default otherwise.
# `positions_seed` is only ever used to seed the widget — never written back
# to from `edited` — for the same reason described in the note below.
if "positions_seed" not in st.session_state:
    if POSITIONS_FILE.exists():
        try:
            st.session_state.positions_seed = pd.read_csv(POSITIONS_FILE)
        except Exception:
            st.session_state.positions_seed = DEFAULT_POSITIONS
    else:
        st.session_state.positions_seed = DEFAULT_POSITIONS

# NOTE: `value` is only used to seed the editor the very first time it runs
# for this `key`. After that, st.data_editor tracks all edits internally
# under st.session_state["positions_editor"] — do NOT also copy its output
# back into a separate session_state variable and feed that back in as
# `value`. Doing so creates a one-rerun lag where every edit needs to be
# entered twice before it registers.
edited = st.data_editor(
    st.session_state.positions_seed,
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

# --- Save / load positions (free, local — a CSV file next to the app) -----
required_cols = ["Fly", "Entry", "Stop", "Lots (+long/-short)", "Tick Size", "Tick Value ($)"]

with st.sidebar:
    st.header("Save / Load Positions")
    sv1, sv2 = st.columns(2)
    if sv1.button("💾 Save"):
        edited.to_csv(POSITIONS_FILE, index=False)
        st.success(f"Saved {len(edited)} position(s).")
    if sv2.button("🗑️ Clear saved"):
        if POSITIONS_FILE.exists():
            POSITIONS_FILE.unlink()
        st.success("Saved file cleared (current table is unaffected).")

    st.download_button(
        "⬇️ Download positions as CSV",
        data=edited.to_csv(index=False),
        file_name="positions.csv",
        mime="text/csv",
        help="Grab a copy you can keep, email, or load into another machine.",
    )

    upload = st.file_uploader(
        "⬆️ Load positions from CSV", type=["csv"], key="positions_csv_upload"
    )
    if upload is not None:
        file_sig = (upload.name, upload.size)
        if st.session_state.get("_last_loaded_positions_sig") != file_sig:
            try:
                loaded_df = pd.read_csv(upload)
                missing_cols = [c for c in required_cols if c not in loaded_df.columns]
                bad_flies = (
                    sorted(set(loaded_df["Fly"].dropna()) - set(fly_cols))
                    if "Fly" in loaded_df.columns else []
                )
                if missing_cols:
                    st.error(f"CSV is missing column(s): {', '.join(missing_cols)}")
                else:
                    if bad_flies:
                        st.warning(
                            f"Dropping row(s) with unrecognized D-fly name(s): "
                            f"{', '.join(bad_flies)}"
                        )
                        loaded_df = loaded_df[loaded_df["Fly"].isin(fly_cols)]
                    st.session_state.positions_seed = loaded_df
                    st.session_state["_last_loaded_positions_sig"] = file_sig
                    if "positions_editor" in st.session_state:
                        del st.session_state["positions_editor"]
                    st.success(f"Loaded {len(loaded_df)} position(s).")
                    st.rerun()
            except Exception as e:
                st.error(f"Couldn't read that CSV: {e}")

    if POSITIONS_FILE.exists():
        st.caption(f"Last saved file on disk: {POSITIONS_FILE.name}")
    else:
        st.caption("No saved file yet — click Save to create one.")

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
# 2. Correlation window — rolling Pearson + EWMA smoothing
# ---------------------------------------------------------------------------
st.header("2. EWMA-Weighted Correlation-Adjusted Portfolio Risk")
st.caption(
    "Method: compute a rolling Pearson correlation between each pair of "
    "D-flies over the lookback period (window length below), then apply "
    "RiskMetrics-style EWMA smoothing across that rolling series so recent "
    "windows count more than older ones — instead of one flat correlation "
    "over the whole lookback period."
)

# Allow picking dates well beyond the dataset's last available date; we
# validate below and tell the user plainly if a date isn't there, rather
# than silently clamping.
FAR_FUTURE = max_date + pd.Timedelta(days=730)

dc1, dc2, dc3 = st.columns([1.4, 1, 1])
with dc1:
    date_range = st.date_input(
        "Lookback period (start, end)",
        value=(max(min_date, max_date - pd.Timedelta(days=90)), max_date),
        min_value=min_date,
        max_value=FAR_FUTURE,
    )
with dc2:
    window_choice = st.selectbox(
        "Rolling correlation window",
        ["5-day", "10-day", "20-day", "30-day", "60-day", "Custom"],
        index=2,
    )
with dc3:
    lam = st.slider(
        "EWMA decay (λ)", min_value=0.60, max_value=0.99, value=0.94, step=0.01,
        help="Higher λ = slower decay = older rolling-correlation values still "
             "carry meaningful weight. RiskMetrics standard is 0.94.",
    )

if window_choice == "Custom":
    window = st.number_input("Custom window length (days)", min_value=2, max_value=250, value=20, step=1)
else:
    window = int(window_choice.split("-")[0])

if len(date_range) != 2:
    st.info("Pick both a start and an end date for the lookback period.")
    st.stop()
start_date, end_date = date_range

# --- Availability check: tell the user plainly, don't silently clamp ---
date_problem = None
if start_date < min_date:
    date_problem = f"{start_date} is not available — data starts {min_date}."
elif start_date > max_date:
    date_problem = f"{start_date} is not available — data only runs through {max_date}."
elif end_date > max_date:
    date_problem = f"{end_date} is not available — data only runs through {max_date}."
elif end_date < min_date:
    date_problem = f"{end_date} is not available — data starts {min_date}."

if date_problem:
    st.error(f"⚠️ {date_problem} Pick a date within {min_date} → {max_date}.")
    st.stop()

if start_date >= end_date:
    st.error("Start date must be before end date.")
    st.stop()

window_data = df[(df["Date"].dt.date >= start_date) & (df["Date"].dt.date <= end_date)]

legs_flies = positions["Fly"].tolist()
unique_flies = sorted(set(legs_flies))

min_needed = window + 2
if len(window_data) < min_needed:
    st.error(
        f"Only {len(window_data)} trading day(s) in this lookback period, but a "
        f"{window}-day rolling window needs at least {min_needed}. Widen the "
        f"lookback period or shorten the rolling window."
    )
    st.stop()


def ewma_corr_matrix(data: pd.DataFrame, flies: list[str], window: int, lam: float):
    """Rolling Pearson correlation per pair -> EWMA-smoothed final value."""
    n = len(flies)
    C = np.eye(n)
    rolling_series = {}
    fell_back = []
    for i in range(n):
        for j in range(i + 1, n):
            s1, s2 = data[flies[i]], data[flies[j]]
            roll = s1.rolling(window).corr(s2).dropna()
            if len(roll) == 0:
                val = s1.corr(s2)
                val = 0.0 if pd.isna(val) else float(val)
                fell_back.append((flies[i], flies[j]))
            else:
                ewma = roll.ewm(alpha=1 - lam, adjust=False).mean()
                val = float(ewma.iloc[-1])
            val = max(-1.0, min(1.0, val))
            C[i, j] = C[j, i] = val
            rolling_series[(flies[i], flies[j])] = roll
    return C, rolling_series, fell_back


C_unique, rolling_series, fell_back = ewma_corr_matrix(window_data, unique_flies, window, lam)
corr_unique = pd.DataFrame(C_unique, index=unique_flies, columns=unique_flies)

if fell_back:
    st.caption(
        "⚠️ Not enough rolling observations for: "
        + ", ".join(f"{a}/{b}" for a, b in fell_back)
        + " — used a flat Pearson correlation over the full lookback period for "
        "these pairs instead."
    )

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
m2.metric("EWMA Correlation-Adjusted $ Risk", f"${corr_adj_risk:,.0f}",
          delta=f"{corr_adj_risk - sum_abs_risk:,.0f}", delta_color="inverse")
m3.metric("Portfolio Correlation Risk (0–1)", f"{ratio:.2f}")

st.caption(
    "Correlation-adjusted risk = √(Rᵀ · C · R), where R is the vector of each "
    "position's signed stop-loss dollar risk (long +, short −) and C is now "
    f"the EWMA-smoothed ({window}-day rolling window, λ={lam}) correlation "
    "matrix rather than a single flat-period Pearson value. Because R is "
    "signed, a position long one fly and short a highly correlated fly nets "
    "down toward zero risk; two positions on the same side of correlated "
    "flies stack up toward the naive sum."
)

with st.expander("Show EWMA-adjusted correlation matrix (unique D-flies in this portfolio)"):
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
        f"{window}-day rolling Pearson correlation, EWMA-smoothed with λ={lam}, "
        f"over the lookback period {start_date} → {end_date} "
        f"({len(window_data)} trading days available)."
    )

with st.expander("Show rolling correlation history for a pair"):
    if len(unique_flies) < 2:
        st.write("Add positions in at least two different D-flies to see a pair.")
    else:
        pc1, pc2 = st.columns(2)
        fly_a = pc1.selectbox("Fly A", unique_flies, index=0, key="pair_a")
        fly_b = pc2.selectbox("Fly B", unique_flies, index=min(1, len(unique_flies) - 1), key="pair_b")
        if fly_a == fly_b:
            st.write("Pick two different D-flies.")
        else:
            key = (fly_a, fly_b) if (fly_a, fly_b) in rolling_series else (fly_b, fly_a)
            roll = rolling_series.get(key)
            if roll is None or roll.empty:
                st.write("Not enough data to show a rolling series for this pair.")
            else:
                ewma_line = roll.ewm(alpha=1 - lam, adjust=False).mean()
                plot_df = pd.DataFrame(
                    {"Rolling Pearson": roll, "EWMA-smoothed": ewma_line}
                )
                st.line_chart(plot_df)
                st.caption(
                    f"Final EWMA-smoothed value used in the matrix: "
                    f"{ewma_line.iloc[-1]:.2f} (flat full-period Pearson for "
                    f"comparison: {window_data[fly_a].corr(window_data[fly_b]):.2f})"
                )

with st.expander("Show risk vector R and full leg-level correlation matrix C"):
    st.write("**R — signed $ risk per position**")
    st.dataframe(
        pd.DataFrame(
            {"Fly": legs_flies, "Signed $ Risk": R.flatten()}
        ).style.format({"Signed $ Risk": "${:,.0f}"}),
        use_container_width=True,
    )
    st.write("**C — position-level EWMA-adjusted correlation matrix**")
    st.dataframe(
        pd.DataFrame(C, index=legs_flies, columns=legs_flies).style.format("{:.2f}"),
        use_container_width=True,
    )

st.divider()

# ---------------------------------------------------------------------------
# 3. Monte Carlo VaR
# ---------------------------------------------------------------------------
st.header("3. Monte Carlo VaR")
st.caption(
    "Uses the same signed $ risk vector R and EWMA-adjusted correlation "
    "matrix C from Section 2. Draws independent shocks per leg from your "
    "chosen distribution, correlates them via a Cholesky decomposition of C, "
    "then prices each simulated draw against R to build a simulated $ P&L "
    "distribution: L = cholesky(C); simulated_returns = L @ draws; "
    "simulated_pnl = Rᵀ @ simulated_returns. VaR is read off as a percentile "
    "of that distribution."
)


def nearest_psd_correlation(mat: np.ndarray) -> np.ndarray:
    """Project a matrix onto the nearest valid (positive semi-definite)
    correlation matrix so Cholesky always succeeds, even if the pairwise
    EWMA-built matrix isn't exactly PSD."""
    sym = (mat + mat.T) / 2
    eigvals, eigvecs = np.linalg.eigh(sym)
    eigvals = np.clip(eigvals, 1e-10, None)
    psd = eigvecs @ np.diag(eigvals) @ eigvecs.T
    d = np.sqrt(np.diag(psd))
    d[d == 0] = 1e-10
    psd = psd / np.outer(d, d)
    np.fill_diagonal(psd, 1.0)
    return psd


mc1, mc2, mc3 = st.columns(3)
n_sims = mc1.number_input("Number of simulations", min_value=1000, max_value=200000, value=20000, step=1000)
confidence = mc2.slider("Confidence level (%)", min_value=90, max_value=99, value=95, step=1)
dist_choice = mc3.selectbox("Shock distribution", ["Normal", "Uniform"])

if dist_choice == "Normal":
    nd1, nd2 = st.columns(2)
    dist_mean = nd1.number_input("Mean", value=0.0, step=0.1, format="%.3f")
    dist_std = nd2.number_input("Standard deviation", value=1.0, min_value=0.0001, step=0.1, format="%.3f")
else:
    ud1, ud2 = st.columns(2)
    dist_lo = ud1.number_input("Uniform min", value=-1.0, step=0.1, format="%.3f")
    dist_hi = ud2.number_input("Uniform max", value=1.0, step=0.1, format="%.3f")
    if dist_hi <= dist_lo:
        st.error("Uniform max must be greater than uniform min.")
        st.stop()

sc1, sc2 = st.columns([1, 2])
fix_seed = sc1.checkbox("Fix random seed", value=True, help="Same seed = reproducible simulation on rerun.")
seed_val = sc2.number_input("Seed", value=42, step=1, disabled=not fix_seed)

C_psd = nearest_psd_correlation(C)
adj_norm = float(np.linalg.norm(C_psd - C))
if adj_norm > 1e-6:
    st.caption(
        "⚠️ The EWMA-built correlation matrix wasn't exactly a valid "
        "(positive semi-definite) correlation matrix, so it was projected "
        "onto the nearest valid one before running the simulation "
        f"(adjustment size: {adj_norm:.4f})."
    )

L = np.linalg.cholesky(C_psd)

rng = np.random.default_rng(int(seed_val) if fix_seed else None)
n_legs = len(legs_flies)
if dist_choice == "Normal":
    draws = rng.normal(loc=dist_mean, scale=dist_std, size=(int(n_sims), n_legs))
else:
    draws = rng.uniform(low=dist_lo, high=dist_hi, size=(int(n_sims), n_legs))

# simulated_returns = L @ draws (per draw) -> vectorized as draws @ L.T
simulated_returns = draws @ L.T
simulated_pnl = simulated_returns @ R.flatten()

var_percentile = 100 - confidence
var_value = float(np.percentile(simulated_pnl, var_percentile))
cvar_value = float(simulated_pnl[simulated_pnl <= var_value].mean()) if np.any(simulated_pnl <= var_value) else var_value

v1, v2, v3, v4 = st.columns(4)
v1.metric("Simulated Mean $ P&L", f"${simulated_pnl.mean():,.0f}")
v2.metric(f"Monte Carlo VaR ({confidence}%)", f"${abs(var_value):,.0f}")
v3.metric(f"Expected Shortfall (CVaR, {confidence}%)", f"${abs(cvar_value):,.0f}")
v4.metric("Worst Simulated $ P&L", f"${simulated_pnl.min():,.0f}")

st.caption(
    f"VaR reads as: over {int(n_sims):,} simulated scenarios using your "
    f"{dist_choice.lower()} shocks correlated via C, there's a {var_percentile}% "
    f"chance of a loss at least this large. Expected Shortfall is the average "
    f"loss across just the scenarios beyond that VaR threshold — a view of "
    f"how bad the tail gets, not just where it starts."
)

hist_fig = px.histogram(
    simulated_pnl,
    nbins=80,
    labels={"value": "Simulated $ P&L"},
    title="Simulated Portfolio P&L Distribution",
)
hist_fig.add_vline(
    x=var_value,
    line_dash="dash",
    line_color="red",
    annotation_text=f"VaR ({confidence}%): ${var_value:,.0f}",
    annotation_position="top",
)
hist_fig.update_layout(showlegend=False, height=420)
st.plotly_chart(hist_fig, use_container_width=True)

with st.expander("Show Cholesky factor L used for correlating the shocks"):
    st.dataframe(
        pd.DataFrame(L, index=legs_flies, columns=legs_flies).style.format("{:.3f}"),
        use_container_width=True,
    )
    st.caption("L is the lower-triangular Cholesky factor such that L @ Lᵀ = C.")

st.divider()

# ---------------------------------------------------------------------------
# 4. Historical Simulation VaR
# ---------------------------------------------------------------------------
st.header("4. Historical Simulation VaR")
st.caption(
    "No distribution assumed — replays actual historical daily price moves "
    "through your current positions. For each day in the chosen range: "
    "daily $ P&L = Σᵢ (lotsᵢ × daily price changeᵢ, converted to dollars via "
    "each leg's tick size/tick value). VaR is the chosen percentile of that "
    "daily $ P&L distribution — e.g. 95% VaR is the 5th percentile, the loss "
    "level exceeded on only 5% of historical days for the book you have on "
    "right now."
)

hist_mode = st.radio(
    "Date range to use",
    ["Use full dataset", "Custom date range"],
    horizontal=True,
    key="hist_var_mode",
)

if hist_mode == "Custom date range":
    hist_date_range = st.date_input(
        "Historical VaR date range (start, end)",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=FAR_FUTURE,
        key="hist_var_dates",
    )
    if len(hist_date_range) != 2:
        st.info("Pick both a start and an end date.")
        st.stop()
    hist_start_date, hist_end_date = hist_date_range

    hist_problem = None
    if hist_start_date < min_date:
        hist_problem = f"{hist_start_date} is not available — data starts {min_date}."
    elif hist_start_date > max_date:
        hist_problem = f"{hist_start_date} is not available — data only runs through {max_date}."
    elif hist_end_date > max_date:
        hist_problem = f"{hist_end_date} is not available — data only runs through {max_date}."
    elif hist_end_date < min_date:
        hist_problem = f"{hist_end_date} is not available — data starts {min_date}."

    if hist_problem:
        st.error(f"⚠️ {hist_problem} Pick a date within {min_date} → {max_date}.")
        st.stop()
    if hist_start_date >= hist_end_date:
        st.error("Start date must be before end date.")
        st.stop()
else:
    hist_start_date, hist_end_date = min_date, max_date

hist_confidence = st.slider(
    "Confidence level (%)", min_value=90, max_value=99, value=95, step=1,
    key="hist_var_confidence",
)

hist_window = df[
    (df["Date"].dt.date >= hist_start_date) & (df["Date"].dt.date <= hist_end_date)
].sort_values("Date").reset_index(drop=True)

portfolio_daily_pnl = pd.Series(0.0, index=hist_window.index)
for _, row in positions.iterrows():
    fly = row["Fly"]
    lots = row["Lots (+long/-short)"]
    tick_size = row["Tick Size"]
    tick_value = row["Tick Value ($)"]
    price_change = hist_window[fly].diff()
    dollar_change_per_lot = price_change / tick_size * tick_value
    portfolio_daily_pnl = portfolio_daily_pnl.add(lots * dollar_change_per_lot, fill_value=0.0)

portfolio_daily_pnl.index = hist_window["Date"]
portfolio_daily_pnl = portfolio_daily_pnl.dropna()

if len(portfolio_daily_pnl) < 5:
    st.warning(
        f"Only {len(portfolio_daily_pnl)} usable trading day(s) of daily "
        f"P&L in {hist_start_date} → {hist_end_date} — too few for a "
        f"meaningful historical VaR. Widen the date range."
    )
else:
    hist_var_pct = 100 - hist_confidence
    hist_var_value = float(np.percentile(portfolio_daily_pnl.to_numpy(), hist_var_pct))
    tail = portfolio_daily_pnl[portfolio_daily_pnl <= hist_var_value]
    hist_cvar_value = float(tail.mean()) if len(tail) > 0 else hist_var_value
    worst_date = portfolio_daily_pnl.idxmin()
    worst_pnl = float(portfolio_daily_pnl.min())

    h1, h2, h3, h4 = st.columns(4)
    h1.metric("Trading Days Used", f"{len(portfolio_daily_pnl):,}")
    h2.metric(f"Historical VaR ({hist_confidence}%)", f"${abs(hist_var_value):,.0f}")
    h3.metric(f"Historical Expected Shortfall ({hist_confidence}%)", f"${abs(hist_cvar_value):,.0f}")
    h4.metric("Worst Historical Day", f"${worst_pnl:,.0f}")

    st.caption(
        f"Worst single day for this exact book of positions was "
        f"{worst_date.date()}, at ${worst_pnl:,.0f}. VaR reads as: over "
        f"{hist_start_date} → {hist_end_date} ({len(portfolio_daily_pnl):,} "
        f"trading days), {hist_var_pct}% of days saw a loss at least this "
        f"large for your current positions. Expected Shortfall is the "
        f"average loss across just the days beyond that VaR threshold."
    )

    hist_hist_fig = px.histogram(
        portfolio_daily_pnl,
        nbins=min(80, max(10, len(portfolio_daily_pnl) // 3)),
        labels={"value": "Daily $ P&L"},
        title="Historical Daily P&L Distribution (current positions replayed through history)",
    )
    hist_hist_fig.add_vline(
        x=hist_var_value,
        line_dash="dash",
        line_color="red",
        annotation_text=f"VaR ({hist_confidence}%): ${hist_var_value:,.0f}",
        annotation_position="top",
    )
    hist_hist_fig.update_layout(showlegend=False, height=420)
    st.plotly_chart(hist_hist_fig, use_container_width=True)

    with st.expander("Show daily $ P&L time series"):
        st.line_chart(portfolio_daily_pnl)
        st.caption(
            "Daily $ P&L your current position sizes would have produced on "
            "each historical day, given actual price moves — not a "
            "simulation, this replays what really happened."
        )

    with st.expander("Show daily $ P&L table"):
        pnl_table = portfolio_daily_pnl.reset_index()
        pnl_table.columns = ["Date", "Daily $ P&L"]
        st.dataframe(
            pnl_table.sort_values("Date", ascending=False)
            .style.format({"Daily $ P&L": "${:,.0f}"}),
            use_container_width=True,
            height=300,
        )
