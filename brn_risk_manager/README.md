# BRN D-Fly Risk Manager

A local Streamlit app: stop-loss dollar risk plus Pearson-correlation-adjusted
portfolio risk across ICE Brent generic double-fly (D-fly) spreads, using your
`BRN_D_Flies_2018_2026.xlsx` history (2018 → 2026, all 11 generic D-flies:
CO1-2-3-4 through CO11-12-13-14).

## 1. One-time setup

You need Python 3.9+ installed. Then, in this folder:

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## 2. Run it

```bash
streamlit run app.py
```

This opens the app in your browser at `http://localhost:8501`.

## 3. Share it with another PC on your network

Streamlit's local URL only works on the machine running it by default. To let
another PC on the same network (or same office LAN) open it:

```bash
streamlit run app.py --server.address 0.0.0.0
```

Then find your machine's local IP (`ipconfig` on Windows, `ifconfig`/`ip a` on
Mac/Linux) and share `http://<your-ip>:8501` — anyone on the same network can
open that link while your instance keeps running.

## How it works

1. **Positions** — add rows in the table: pick a generic D-fly from the
   dropdown, set entry price, stop price, signed lots (negative = short),
   tick size and tick value. The app computes each position's stop-loss
   dollar risk and sums it (undiversified total).
2. **Correlation window** — pick any date range inside 2018–2026. The app
   pulls that slice of the D-fly history and computes the Pearson correlation
   matrix between the D-flies you're actually positioned in.
3. **Correlation-adjusted risk** — builds the signed risk vector `R` (long
   positions positive, shorts negative) and the correlation matrix `C`, then
   computes `√(Rᵀ · C · R)`. Because `R` is signed, opposite-side positions in
   correlated D-flies net down; same-side positions in correlated D-flies
   stack up — exactly as they should economically.

## Updating the data

Drop a newer `BRN_D_Flies_2018_2026.xlsx` (same column layout: `Date` +
one column per generic D-fly) into this folder to replace the bundled file,
or use the "Upload D-fly data" box in the sidebar to point at a different
file for a session without overwriting anything.
