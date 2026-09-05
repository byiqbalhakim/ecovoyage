import numpy as np
import pandas as pd

from ..models.propulsion import fuel_rate_from_equilibrium_cond
from ..config import RPM_MIN, RPM_MAX, RPM_STEP, DEFAULT_BALLAST_CONDITION

RPM_CANDIDATES = np.arange(RPM_MIN, RPM_MAX, RPM_STEP)
BALLAST_CONDITION = DEFAULT_BALLAST_CONDITION


def _select_leg_row(legs, summary, leg_id, month_period, use_point='to_pt'):
    if 'leg_id' in summary.columns:
        row = summary[summary['leg_id'] == leg_id]
    else:
        pt = legs.loc[leg_id, use_point]
        if month_period is None:
            row = summary[summary['leg_point'] == pt]
        else:
            row = summary[(summary['leg_point'] == pt) & (summary['datetime'] == month_period)]
    return row.iloc[0]


def leg_weather(legs, summary, leg_id, month_period=None, use_point='to_pt'):
    row = _select_leg_row(legs, summary, leg_id, month_period, use_point)
    return row['hs_mean'], row['tp_mean'], row['wave_dir_mean']


def leg_wind(legs, summary, leg_id, month_period=None, use_point='to_pt'):
    row = _select_leg_row(legs, summary, leg_id, month_period, use_point)
    wind_speed = row['wind_speed_mean']
    wind_dir_from = np.degrees(np.arctan2(-row['u10_vec_mean'], -row['v10_vec_mean'])) % 360
    return wind_speed, wind_dir_from


def leg_cost(legs, summary, leg_id, rpm, month_period=None, ballast_condition=BALLAST_CONDITION,
             include_wind=False):
    dist_nm = legs.loc[leg_id, 'dist_nm']
    ship_heading = legs.loc[leg_id, 'course_deg']
    Hs, Tp, wave_dir = leg_weather(legs, summary, leg_id, month_period)

    if include_wind:
        wind_speed, wind_dir_from = leg_wind(legs, summary, leg_id, month_period)
        dir_to_rad = np.radians((wind_dir_from + 180.0) % 360.0)
        u10 = wind_speed * np.sin(dir_to_rad)
        v10 = wind_speed * np.cos(dir_to_rad)
    else:
        u10, v10 = 0.0, 0.0

    V_kn, fuel_kgh, load_pct = fuel_rate_from_equilibrium_cond(
        rpm, Hs, Tp, wave_dir, ship_heading, ballast_condition, u10=u10, v10=v10)

    if V_kn is None or V_kn <= 0.5:
        return None

    time_h = dist_nm / V_kn
    fuel_t = fuel_kgh * time_h / 1000.0
    return {'time_h': time_h, 'fuel_t': fuel_t, 'V_kn': V_kn, 'load_pct': load_pct}


def build_cost_table(legs, summary, month_period=None, include_wind=False,
                      ballast_condition=BALLAST_CONDITION):
    rows = []
    for leg_id in legs['leg_id']:
        for rpm in RPM_CANDIDATES:
            result = leg_cost(legs, summary, leg_id, rpm, month_period,
                               ballast_condition=ballast_condition, include_wind=include_wind)
            if result:
                rows.append({'leg_id': leg_id, 'rpm': rpm, **result})
    return pd.DataFrame(rows)