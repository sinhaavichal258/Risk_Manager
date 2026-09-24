"""
Curve Risk Manager
------------------
A local Streamlit app for stop-loss risk, EWMA-weighted
Pearson-correlation-adjusted portfolio risk, Monte Carlo VaR,
and Historical Simulation VaR.

The same calculations can be run against either bundled dataset:
- BRN_D_Flies_2018_2026.xlsx
- CL_BZ_Flybox.xlsx

Run with:
    streamlit run app.py
"""

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from pathlib import Path

st.set_page_config(page_title="Risk Manager", layout="wide")

APP_DIR = Path(__file__).parent

DATASETS = {
    "BRN D-Flies": {
        "id": "brn_d_flies",
        "file": APP_DIR / "BRN_D_Flies_2018_2026.xlsx",
        "position_file": APP_DIR / "saved_positions.csv",  # preserve existing BRN file
        "fly_label": "Generic D-Fly",
        "caption": "ICE Brent generic double-fly (D-fly) spreads.",
    },
    "CL/BZ Flybox": {
        "id": "cl_bz_flybox",
        "file": APP_DIR / "CL_BZ_Flybox.xlsx",
        "position_file": APP_DIR / "saved_positions_CL_BZ.csv",
        "fly_label": "CL/BZ Flybox",
        "caption": "CL/BZ flybox spreads.",
    },
}


@st.cache_data
def load_data(file):
    df = pd.read_excel(file, sheet_name=0)
    if "Date" not in df.columns:
        raise ValueError("The Excel file must contain a 'Date' column.")

    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date").reset_index(drop=True)

    fly_cols = [c for c in df.columns if c != "Date" and not str(c).startswith("Unnamed:")]
    if not fly_cols:
        raise ValueError("The Excel file must contain at least one fly-price column besides 'Date'.")

    return df


# ---------------------------------------------------------------------------
# Dataset selection / data source
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Dataset")
    selected_dataset = st.selectbox(
        "Select dataset",
        list(DATASETS.keys()),
        index=0,
        key="dataset_selector",
    )

dataset = DATASETS[selected_dataset]
dataset_id = dataset["id"]
DATA_FILE = dataset["file"]
POSITIONS_FILE = dataset["position_file"]

with st.sidebar:
    st.header("Data source")
    uploaded = st.file_uploader(
        f"Upload {selected_dataset} data (.xlsx) — optional, overrides the bundled file",
        type=["xlsx"],
        key=f"data_upload_{dataset_id}",
    )
    st.caption(
        f"Bundled file: {DATA_FILE.name}"
    )

if uploaded is not None:
    try:
        df = load_data(uploaded)
    except Exception as e:
        st.error(f"Could not read the uploaded Excel file: {e}")
        st.stop()
elif DATA_FILE.exists():
    try:
        df = load_data(DATA_FILE)
