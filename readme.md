# EcoVoyage — Dashboard Integration Guide

This document is for whoever builds the frontend/dashboard.
It covers the only two functions the dashboard needs to call, what they
return, and how to trigger a new prediction. The dashboard should never
need to import from `models/`, `optimizer/`, or `data/` directly, and
never needs to write SQL.

---

## 1. Running a new prediction

To compute a new voyage prediction (or re-run an existing route/period
combination), call:

```python
from src.orchestration import run_prediction

prediction_id = run_prediction(
    route_id='rotterdam_ny',        # str, which route
    weather_period='2025-01',       # str, 'YYYY-MM'
    ballast_condition='laden',      # 'laden' or 'ballast'
    include_wind=False,             # keep False until Track B (wind) is added
    vessel_id=1,                    # int, which vessel config row (see seeding below)
)
```

This runs the full 4-layer pipeline (fuel law → SFOC → resistance →
DP optimizer), computes CO2 emissions and CII rating, saves the result
to the database, and returns a `prediction_id` (int). **Every call
creates a new row — nothing is overwritten.** Store this id if the
dashboard needs to link back to a specific run later.

**One-time setup, before the very first prediction can be saved:**
the vessel must exist in the database first (`vessel_id` is a foreign
key). Run once:

```python
from src.database.connection import get_connection, init_db
from src.database.queries import insert_vessel
from src.models.ship import SHIP

init_db()
conn = get_connection()
vessel_id = insert_vessel(conn, SHIP)   # returns 1 on first run
conn.commit()
conn.close()
```

`init_db()` is also safe to call every time the app starts — it's a
no-op if tables already exist. If you're updating an older database
that predates the CO2/CII columns, also run once:

```python
from src.database.connection import run_emissions_migration
run_emissions_migration()
```

This is also safe to call repeatedly — it silently skips columns that
already exist.

---

## 2. Reading data for display

These are the **only two functions** the dashboard should call to get
data for a screen. Both are read-only and do zero computation — all
the math (per-leg splits, cumulative fuel, CO2, CII, formatted labels)
was already done once at prediction time and stored flat.

### `get_dashboard_summary(conn, prediction_id)` → `dict` or `None`

One row of headline numbers for a single prediction. Use this for
cards/headers at the top of a results screen.

```python
from src.database.connection import get_connection
from src.database.queries import get_dashboard_summary

conn = get_connection()
summary = get_dashboard_summary(conn, prediction_id)
conn.close()
```

Returns `None` if the `prediction_id` doesn't exist. Otherwise:

| Field | Type | Example | Notes |
|---|---|---|---|
| `prediction_id` | int | `10` | |
| `route_id` | str | `'rotterdam_ny'` | |
| `route_name` | str | `'Rotterdam - New York'` | display name |
| `weather_period` | str | `'2025-01'` | |
| `weather_label` | str | `'January (harsh)'` | ready to display as-is |
| `ballast_condition` | str | `'laden'` | |
| `dp_fuel_t` | float or `None` | `405.23` | `None` if infeasible |
| `baseline_fuel_t` | float | `419.39` | |
| `savings_pct` | float or `None` | `3.38` | `None` if infeasible |
| `savings_label` | str | `'3.4% saved'` or `'Infeasible'` | ready to drop into a card |
| `is_feasible` | int (0/1) | `1` | check this before showing fuel/CII-based charts |
| `n_legs` | int | `10` | |
| `total_dist_nm` | float | `3149.46` | |
| `created_at` | str (ISO 8601, UTC) | `'2026-09-06T07:49:41...'` | when this run happened |
| `total_co2_t` | float or `None` | `1261.88` | total voyage CO2, `None` if infeasible or from a prediction made before this feature existed |
| `attained_cii` | float or `None` | `7.33` | gCO2 per DWT·nm, IMO definition |
| `reference_cii` | float or `None` | `7.61` | IMO 2019 baseline for this vessel's type/size bracket |
| `cii_rating` | str | `'C'` | letter A–E, or `'N/A'` if infeasible / pre-dates this feature |

**Displaying CII:** a natural card layout is `attained_cii` vs.
`reference_cii` side by side with `cii_rating` as a colored badge
(A=green through E=red is the conventional IMO scheme). Don't
recompute the rating client-side — always use `cii_rating` as stored.

### `get_dashboard_legs(conn, prediction_id)` → `pandas.DataFrame`

Per-leg rows, already sorted by `leg_id`, ready to feed straight into
any chart. Empty DataFrame if the prediction doesn't exist or was
infeasible (no legs saved in that case).

```python
from src.database.queries import get_dashboard_legs

legs_df = get_dashboard_legs(conn, prediction_id)
```

| Column | Type | Chart use |
|---|---|---|
| `leg_id` | int | x-axis (raw) |
| `leg_label` | str | `'Leg 1'`, `'Leg 2'`... — x-axis (display) |
| `dp_rpm` | float | RPM-per-leg line/bar chart |
| `dp_fuel_t` | float | fuel-per-leg bar chart |
| `dp_time_h` | float | | 
| `dp_v_kn` | float or `None` | speed-per-leg chart |
| `baseline_rpm` | float | constant across all rows — useful as a reference line |
| `baseline_fuel_t` | float | this leg's *share* of the baseline total (split proportionally by distance) |
| `cum_dp_fuel_t` | float | running total — plug directly into a "fuel burned so far" line chart |
| `co2_t` | float or `None` | this leg's CO2 emissions (`fuel_t × 3.114`) — bar chart or cumulative overlay |
| `hs_m` | float or `None` | wave height overlay |
| `wind_speed_ms` | float or `None` | wind overlay — will be `None` for many wave-only runs; always check for `None` before plotting |

### Listing past predictions

```python
from src.database.queries import list_predictions

all_runs = list_predictions(conn)                        # every prediction, newest first
route_runs = list_predictions(conn, route_id='rotterdam_ny')  # filtered to one route
```

Returns a `DataFrame` of raw `voyage_predictions` rows (not the
dashboard view) — use this for a "history" screen where the user picks
which past run to view, then calls `get_dashboard_summary`/`get_dashboard_legs`
with the chosen `prediction_id`. Note: predictions made before the
CO2/CII feature was added will show `None`/`NaN` in those columns —
handle that gracefully rather than assuming every row has them.

---

## 3. Suggested chart mapping

| Dashboard element | Data source | Notes |
|---|---|---|
| Headline savings card | `summary['savings_label']` | already formatted |
| CII rating badge | `summary['cii_rating']` | color by letter: A=green, B=lime, C=yellow, D=orange, E=red |
| Attained vs. reference CII | `summary['attained_cii']`, `summary['reference_cii']` | two-bar or gauge chart |
| DP vs. baseline fuel bar chart | `legs_df[['leg_label', 'dp_fuel_t', 'baseline_fuel_t']]` | two bars per leg |
| RPM policy across route | `legs_df[['leg_label', 'dp_rpm']]`, reference line at `baseline_rpm` | |
| Cumulative fuel burn | `legs_df[['leg_label', 'cum_dp_fuel_t']]` | line chart, already cumulative |
| Cumulative / per-leg CO2 | `legs_df[['leg_label', 'co2_t']]` | bar or cumulative line, same pattern as fuel |
| Weather overlay | `legs_df[['leg_label', 'hs_m', 'wind_speed_ms']]` | secondary y-axis against fuel or RPM |
| History / past runs list | `list_predictions()` | table, click-through to detail view |

---

## 4. What NOT to do in dashboard code

- Don't write raw SQL — everything needed goes through `queries.py`.
- Don't recompute fuel/CO2/CII numbers client-side — they're already
  final in `dashboard_summary_view` / `dashboard_leg_view`.
- Don't call `run_prediction()` on every page load — it re-runs the
  full optimizer and inserts a new row each time. Only call it when
  the user explicitly requests a new prediction.
- Don't assume `prediction_id=1` — always use the id returned by
  `run_prediction()` or selected from `list_predictions()`.
- Don't assume every prediction has CO2/CII data — older rows (created
  before this feature existed) will have `None` there.