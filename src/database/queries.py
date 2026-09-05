"""
Every read/write to the database goes through a function here -- nothing
else in the codebase should contain raw SQL. That way, if you ever swap
SQLite for Postgres, this is the only file that needs to change.

All INSERT functions use `?` placeholders (e.g. `VALUES (?, ?, ?)`)
rather than f-string/`.format()` interpolation. This isn't just style --
building SQL by string-concatenating user or file input is how SQL
injection bugs happen. `?` placeholders let sqlite3 handle the escaping
safely, and it's the same pattern you'd use with any other database
library later.
"""

from datetime import datetime, timezone

import pandas as pd

from .connection import get_connection


# ---- vessels -----------------------------------------------------------

def insert_vessel(conn, ship: dict) -> int:
    """ship: the SHIP dict from src/models/ship.py. Returns the new vessel_id."""
    cur = conn.execute(
        """INSERT INTO vessels
           (name, lpp, beam, t_full, t_ballast, depth, dwt, cb, d_prop, pitch,
            v_service_kn, p_service_kw)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        ('EcoVoyage LPG Carrier', ship['Lpp'], ship['B'], ship['T_full'],
         ship['T_ballast'], ship['depth'], ship.get('DWT'), ship['Cb'],
         ship['D_prop'], ship['pitch'], ship['V_service_kn'], ship['P_service_kw'])
    )
    return cur.lastrowid


def get_vessel(conn, vessel_id: int) -> dict:
    row = conn.execute('SELECT * FROM vessels WHERE vessel_id = ?', (vessel_id,)).fetchone()
    return dict(row) if row else None


# ---- routes -------------------------------------------------------------

def insert_route(conn, route_id: str, name: str, origin_latlon, dest_latlon, n_waypoints: int):
    conn.execute(
        """INSERT OR REPLACE INTO routes
           (route_id, name, origin_lat, origin_lon, dest_lat, dest_lon, n_waypoints)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (route_id, name, origin_latlon[0], origin_latlon[1],
         dest_latlon[0], dest_latlon[1], n_waypoints)
    )


def insert_route_legs(conn, route_id: str, legs: pd.DataFrame):
    """legs: the DataFrame produced by build_route_from_waypoints()."""
    rows = [
        (route_id, int(r.leg_id), int(r.from_pt), int(r.to_pt), float(r.dist_nm), float(r.course_deg))
        for r in legs.itertuples()
    ]
    conn.executemany(
        """INSERT OR REPLACE INTO route_legs (route_id, leg_id, from_pt, to_pt, dist_nm, course_deg)
           VALUES (?, ?, ?, ?, ?, ?)""",
        rows
    )


def get_route_legs(conn, route_id: str) -> pd.DataFrame:
    """Returns legs in the same shape build_route_from_waypoints() produces,
    so downstream optimizer code doesn't need to know it came from a DB."""
    return pd.read_sql_query(
        """SELECT leg_id, from_pt, to_pt, dist_nm, course_deg
           FROM route_legs WHERE route_id = ? ORDER BY leg_id""",
        conn, params=(route_id,)
    )


# ---- weather --------------------------------------------------------------

def insert_weather_era5(conn, route_id: str, weather_df: pd.DataFrame):
    """weather_df: output of era5.py's load_era5() / extract_route_weather(),
    with columns datetime, leg_point, lat, lon, hs_m, tp_s, wave_dir_deg, u10_ms, v10_ms."""
    rows = [
        (str(r.datetime), route_id, int(r.leg_point), float(r.lat), float(r.lon),
         float(r.hs_m) if pd.notna(r.hs_m) else None,
         float(r.tp_s) if pd.notna(r.tp_s) else None,
         float(r.wave_dir_deg) if pd.notna(r.wave_dir_deg) else None,
         float(r.u10_ms) if pd.notna(r.u10_ms) else None,
         float(r.v10_ms) if pd.notna(r.v10_ms) else None)
        for r in weather_df.itertuples()
    ]
    conn.executemany(
        """INSERT OR IGNORE INTO weather_era5
           (datetime, route_id, leg_point, lat, lon, hs_m, tp_s, wave_dir_deg, u10_ms, v10_ms)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        rows
    )
    # INSERT OR IGNORE (rather than OR REPLACE) here because weather_era5 has
    # a UNIQUE constraint on (datetime, route_id, leg_point) -- re-running
    # extraction on the same period just silently skips rows already loaded.


# ---- predictions ------------------------------------------------------------

def insert_prediction(conn, route_id: str, vessel_id: int, weather_period: str,
                       ballast_condition: str, deadline_h: float, include_wind: bool,
                       dp_fuel_t: float, baseline_rpm: float, baseline_fuel_t: float,
                       savings_pct: float, is_feasible: bool) -> int:
    """Returns the new prediction_id. This is what run_prediction() calls
    at the end of the pipeline (Phase 10)."""
    cur = conn.execute(
        """INSERT INTO voyage_predictions
           (route_id, vessel_id, weather_period, ballast_condition, deadline_h,
            include_wind, dp_fuel_t, baseline_rpm, baseline_fuel_t, savings_pct,
            is_feasible, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (route_id, vessel_id, weather_period, ballast_condition, deadline_h,
         int(include_wind), dp_fuel_t, baseline_rpm, baseline_fuel_t, savings_pct,
         int(is_feasible), datetime.now(timezone.utc).isoformat())
    )
    return cur.lastrowid


def insert_prediction_legs(conn, prediction_id: int, policy_df: pd.DataFrame):
    """policy_df: the DataFrame returned by run_dp_optimizer() (leg_id, rpm,
    time_h, fuel_t, V_kn, load_pct)."""
    rows = [
        (prediction_id, int(r.leg_id), float(r.rpm), float(r.time_h), float(r.fuel_t),
         float(r.V_kn) if pd.notna(r.V_kn) else None,
         float(r.load_pct) if pd.notna(r.load_pct) else None)
        for r in policy_df.itertuples()
    ]
    conn.executemany(
        """INSERT INTO prediction_legs (prediction_id, leg_id, rpm, time_h, fuel_t, v_kn, load_pct)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        rows
    )


def get_prediction(conn, prediction_id: int) -> dict:
    """This is the single query the dashboard (Phase 11) needs to display
    a result -- header info plus the per-leg policy in one call."""
    header = conn.execute(
        'SELECT * FROM voyage_predictions WHERE prediction_id = ?', (prediction_id,)
    ).fetchone()
    if header is None:
        return None

    legs = pd.read_sql_query(
        'SELECT * FROM prediction_legs WHERE prediction_id = ? ORDER BY leg_id',
        conn, params=(prediction_id,)
    )
    return {'header': dict(header), 'legs': legs}


def list_predictions(conn, route_id: str = None) -> pd.DataFrame:
    """Dashboard 'history' view -- every prediction ever run, optionally
    filtered to one route."""
    if route_id:
        return pd.read_sql_query(
            'SELECT * FROM voyage_predictions WHERE route_id = ? ORDER BY created_at DESC',
            conn, params=(route_id,)
        )
    return pd.read_sql_query('SELECT * FROM voyage_predictions ORDER BY created_at DESC', conn)

def build_dashboard_views(conn, prediction_id: int, route_name: str, weather_label: str,
                           weather_df: pd.DataFrame = None):
    """
    Pre-computes everything the dashboard will ever need to display this
    prediction, and stores it as flat rows. Call this once, right after
    insert_prediction() + insert_prediction_legs(). The dashboard should
    never need to query anything except these two tables.

    weather_df: optional, the SUMMARIZED weather (output of era5.py's
    extract_route_weather() / build_leg_weather_summary()), with columns
    hs_mean, wind_speed_mean, indexed by leg_point -- NOT raw hs_m/u10_ms/v10_ms.
    """
    header = conn.execute(
        'SELECT * FROM voyage_predictions WHERE prediction_id = ?', (prediction_id,)
    ).fetchone()
    header = dict(header)

    legs = pd.read_sql_query(
        'SELECT * FROM prediction_legs WHERE prediction_id = ? ORDER BY leg_id',
        conn, params=(prediction_id,)
    )
    route_legs = get_route_legs(conn, header['route_id'])

    legs = legs.merge(route_legs[['leg_id', 'dist_nm']], on='leg_id', how='left')

    total_dist = legs['dist_nm'].sum()
    legs['baseline_fuel_t'] = header['baseline_fuel_t'] * (legs['dist_nm'] / total_dist)
    legs['cum_dp_fuel_t'] = legs['fuel_t'].cumsum()
    legs['leg_label'] = 'Leg ' + (legs['leg_id'] + 1).astype(str)

    if weather_df is not None and not weather_df.empty and 'leg_point' in weather_df.columns:
        weather_by_leg = weather_df.set_index('leg_point')
        legs['hs_m'] = legs['leg_id'].map(weather_by_leg.get('hs_mean', pd.Series(dtype=float)))
        legs['wind_speed_ms'] = legs['leg_id'].map(weather_by_leg.get('wind_speed_mean', pd.Series(dtype=float)))
    else:
        legs['hs_m'] = None
        legs['wind_speed_ms'] = None

    conn.execute('DELETE FROM dashboard_leg_view WHERE prediction_id = ?', (prediction_id,))
    conn.executemany(
        """INSERT INTO dashboard_leg_view
           (prediction_id, route_id, weather_period, leg_id, leg_label, dp_rpm, dp_fuel_t,
            dp_time_h, dp_v_kn, baseline_rpm, baseline_fuel_t, cum_dp_fuel_t, hs_m, wind_speed_ms)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            (prediction_id, header['route_id'], header['weather_period'], int(r.leg_id), r.leg_label,
             float(r.rpm), float(r.fuel_t), float(r.time_h),
             float(r.v_kn) if pd.notna(r.v_kn) else None,
             float(header['baseline_rpm']), float(r.baseline_fuel_t), float(r.cum_dp_fuel_t),
             float(r.hs_m) if pd.notna(r.hs_m) else None,
             float(r.wind_speed_ms) if pd.notna(r.wind_speed_ms) else None)
            for r in legs.itertuples()
        ]
    )

    conn.execute('DELETE FROM dashboard_summary_view WHERE prediction_id = ?', (prediction_id,))
    conn.execute(
        """INSERT INTO dashboard_summary_view
           (prediction_id, route_id, route_name, weather_period, weather_label, ballast_condition,
            dp_fuel_t, baseline_fuel_t, savings_pct, savings_label, is_feasible, n_legs,
            total_dist_nm, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (prediction_id, header['route_id'], route_name, header['weather_period'], weather_label,
         header['ballast_condition'], header['dp_fuel_t'], header['baseline_fuel_t'],
         header['savings_pct'],
         f"{header['savings_pct']:.1f}% saved" if header['savings_pct'] is not None else 'Infeasible',
         header['is_feasible'], len(legs), float(total_dist), header['created_at'])
    )


# ---- what the dashboard actually calls -- read-only, zero computation ----

def get_dashboard_summary(conn, prediction_id: int) -> dict:
    row = conn.execute(
        'SELECT * FROM dashboard_summary_view WHERE prediction_id = ?', (prediction_id,)
    ).fetchone()
    return dict(row) if row else None


def get_dashboard_legs(conn, prediction_id: int) -> pd.DataFrame:
    return pd.read_sql_query(
        'SELECT * FROM dashboard_leg_view WHERE prediction_id = ? ORDER BY leg_id',
        conn, params=(prediction_id,)
    )