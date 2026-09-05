"""
Phase 10 -- the single entry point that ties Layers 1-4 together and
persists the result. This is the only function the dashboard (or anything
else) should call to produce a new prediction; nothing downstream should
import from optimizer/, models/, or data/ directly.
"""

import pandas as pd

from .config import DEFAULT_ROUTE_ID, DEFAULT_BALLAST_CONDITION, ROUTE_DEFINITIONS_PATH
from .models.ship import SHIP
from .data.routes import load_passage_plan, build_route_from_waypoints
from .data.era5 import load_era5, extract_route_weather
from .optimizer.leg_cost import build_cost_table
from .optimizer.dp import run_dp_optimizer, evaluate_month, compute_deadline_h
from .optimizer.baseline import best_baseline_rpm
from .database.connection import get_connection, init_db
from .database.queries import (
    get_route_legs, insert_route, insert_route_legs,
    insert_prediction, insert_prediction_legs, build_dashboard_views,
)

WEATHER_LABELS = {'01': 'January (harsh)', '07': 'July (calm)'}


def run_prediction(route_id: str = DEFAULT_ROUTE_ID, weather_period: str = '2025-01',
                    ballast_condition: str = DEFAULT_BALLAST_CONDITION,
                    include_wind: bool = False, vessel_id: int = 1, db_conn=None,
                    route_name: str = "Rotterdam - New York") -> int:
    """
    Runs the full pipeline (routes -> weather -> cost table -> DP optimizer)
    for one route/period/ballast combination, saves everything to the DB
    (including pre-built dashboard views), and returns the new prediction_id.

    db_conn: pass an existing connection to reuse it (e.g. from a script
    running several predictions in a row); otherwise one is opened and
    closed automatically.
    """
    owns_conn = db_conn is None
    conn = db_conn or get_connection()
    init_db()  # no-op if tables already exist -- cheap safety net

    try:
        legs = get_or_build_route_legs(conn, route_id, route_name)

        weather_df = load_era5()
        summary = extract_route_weather(weather_df)
        month_period = pd.Period(weather_period, freq='M')

        deadline_h = compute_deadline_h(legs['dist_nm'].sum(), SHIP['V_service_kn'])

        cost_table = build_cost_table(legs, summary, month_period,
                                       include_wind=include_wind,
                                       ballast_condition=ballast_condition)

        policy_df, dp_fuel, dp_time = run_dp_optimizer(cost_table, legs, deadline_h)
        baseline_rpm = best_baseline_rpm(cost_table, legs, deadline_h)
        _, savings_pct = evaluate_month(cost_table, legs, deadline_h)

        is_feasible = pd.notna(dp_fuel)
        baseline_fuel_t = (cost_table[cost_table['rpm'] == baseline_rpm]['fuel_t'].sum()
                            if baseline_rpm is not None else None)

        pred_id = insert_prediction(
            conn, route_id, vessel_id, weather_period, ballast_condition, deadline_h,
            include_wind, dp_fuel if is_feasible else None, baseline_rpm, baseline_fuel_t,
            savings_pct if is_feasible else None, is_feasible,
        )

        if is_feasible:
            insert_prediction_legs(conn, pred_id, policy_df)

        weather_label = WEATHER_LABELS.get(weather_period.split('-')[-1], weather_period)
        leg_weather = summary[summary['datetime'] == month_period] if 'datetime' in summary.columns else None
        build_dashboard_views(conn, pred_id, route_name, weather_label, weather_df=leg_weather)

        conn.commit()
        return pred_id

    finally:
        if owns_conn:
            conn.close()


def get_or_build_route_legs(conn, route_id: str, route_name: str) -> pd.DataFrame:
    """Reuses stored legs if this route's already been loaded once;
    otherwise builds them from the passage plan CSV and stores them."""
    existing = get_route_legs(conn, route_id)
    if not existing.empty:
        return existing

    plan = load_passage_plan(route_def_path(route_id))
    waypoints = plan['waypoints']
    legs = build_route_from_waypoints(waypoints)

    origin_lat, origin_lon = waypoints.iloc[0][['lat', 'lon']]
    dest_lat, dest_lon = waypoints.iloc[-1][['lat', 'lon']]

    insert_route(conn, route_id, route_name, (origin_lat, origin_lon),
                 (dest_lat, dest_lon), len(waypoints))
    insert_route_legs(conn, route_id, legs)
    return legs


def route_def_path(route_id: str) -> str:
    return str(ROUTE_DEFINITIONS_PATH)