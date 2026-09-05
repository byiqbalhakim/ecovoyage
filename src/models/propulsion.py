import numpy as np

from .engine import Engine, SMCR_KW
from .propeller import T_FRAC
from .resistance import (
    R_calm_cond, thrust_from_prop, torque_from_prop,
    solve_equilibrium_speed, R_wind,
)
from .waves import added_resistance_waves

ETA_SHAFT = 0.98  # shaft/gearbox mechanical efficiency, no measured value available

_ENGINE = Engine('ISO')


def fuel_rate_from_equilibrium(rpm, Hs, Tp, mean_wave_dir_deg, ship_heading_deg,
                                SMCR_kw=SMCR_KW):
    """
    Single-condition (laden-implicit), no wind. Validation cross-check only —
    superseded for optimizer use by fuel_rate_from_equilibrium_cond.
    Returns (V_eq_kn, fuel_kg_h, load_pct), or (None, None, None) if infeasible.
    """
    V_eq = solve_equilibrium_speed(rpm, Hs, Tp, mean_wave_dir_deg, ship_heading_deg)
    if V_eq is None:
        return None, None, None

    Q = torque_from_prop(V_eq, rpm)
    omega_shaft = rpm * 2 * np.pi / 60.0
    P_shaft = Q * omega_shaft
    P_brake_kw = P_shaft / ETA_SHAFT / 1000.0

    load_pct = 100 * P_brake_kw / SMCR_kw
    load_pct_clamped = np.clip(load_pct, _ENGINE.load_pct.min(), _ENGINE.load_pct.max())
    sfoc = float(_ENGINE.sfoc_of_load(load_pct_clamped))
    fuel_kg_h = sfoc * P_brake_kw / 1000.0

    return V_eq / 0.514444, fuel_kg_h, load_pct


def solve_equilibrium_speed_cond(rpm, Hs, Tp, mean_wave_dir_deg, ship_heading_deg,
                                  ballast_condition, u10=0.0, v10=0.0,
                                  t=T_FRAC, V_guess_range=(0.5, 25.0)):
    """
    Ballast-conditional, wind-aware equilibrium solve. u10/v10 default to 0
    so this reduces to the no-wind case — production entry point.
    """
    from scipy.optimize import brentq

    def imbalance(V_ms):
        V_kn = V_ms / 0.514444
        R_total = (R_calm_cond(V_ms, ballast_condition)
                   + added_resistance_waves(Hs, Tp, V_kn, mean_wave_dir_deg, ship_heading_deg)
                   + R_wind(u10, v10, V_kn, ship_heading_deg, ballast_condition))
        T_available = thrust_from_prop(V_ms, rpm) * (1 - t)
        return T_available - R_total

    lo, hi = V_guess_range
    if imbalance(lo) * imbalance(hi) > 0:
        return None
    return brentq(imbalance, lo, hi, xtol=1e-4)


def fit_cubic_fuel_law(cal_locked):
    """Fuel[kg/h] = c(ballast) * rpm^3, fit per ballast condition on the locked set."""
    c_by_ballast = {}
    for cond, grp in cal_locked.groupby('ballast'):
        c_by_ballast[cond] = (grp['fuel_mean'] * grp['rpm_mean'] ** 3).sum() / (grp['rpm_mean'] ** 6).sum()
    return c_by_ballast


def fuel_rate_from_equilibrium_cond(rpm, Hs, Tp, mean_wave_dir_deg, ship_heading_deg,
                                     ballast_condition, u10=0.0, v10=0.0,
                                     SMCR_kw=SMCR_KW):
    """Ballast- and wind-aware version of fuel_rate_from_equilibrium. Production entry point."""
    V_eq = solve_equilibrium_speed_cond(rpm, Hs, Tp, mean_wave_dir_deg, ship_heading_deg,
                                         ballast_condition, u10=u10, v10=v10)
    if V_eq is None:
        return None, None, None

    Q = torque_from_prop(V_eq, rpm)
    omega_shaft = rpm * 2 * np.pi / 60.0
    P_shaft = Q * omega_shaft
    P_brake_kw = P_shaft / ETA_SHAFT / 1000.0

    load_pct = 100 * P_brake_kw / SMCR_kw
    load_pct_clamped = np.clip(load_pct, _ENGINE.load_pct.min(), _ENGINE.load_pct.max())
    sfoc = float(_ENGINE.sfoc_of_load(load_pct_clamped))
    fuel_kg_h = sfoc * P_brake_kw / 1000.0

    return V_eq / 0.514444, fuel_kg_h, load_pct