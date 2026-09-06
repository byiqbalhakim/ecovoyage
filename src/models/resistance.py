import numpy as np
from scipy.optimize import brentq

from .ship import SHIP
from .propeller import W_FRAC, T_FRAC, KT_OF_J, KQ_OF_J, KTKQ
from .waves import RHO_SW, added_resistance_waves

ETA_D_ASSUMED = 0.68  # no towing-tank data available

V_SERVICE_MS = SHIP['V_service_kn'] * 0.514444
P_USEFUL_SERVICE = SHIP['P_service_kw'] * 1000 * ETA_D_ASSUMED
R_SERVICE = P_USEFUL_SERVICE / V_SERVICE_MS
K_R = R_SERVICE / V_SERVICE_MS ** 2

K_R_BALLAST = {
    'laden': K_R,
    'ballast': K_R * (SHIP['T_ballast'] / SHIP['T_full']),
}

RHO_AIR = 1.225

FREEBOARD = {
    'laden': SHIP['depth'] - SHIP['T_full'],
    'ballast': SHIP['depth'] - SHIP['T_ballast'],
}

SUPER_HEIGHT_M = 10.0
SUPER_WIDTH_FRAC_OF_B = 0.55
SUPER_LENGTH_FRAC_OF_LPP = 0.12

_A_hull_head = {c: SHIP['B'] * fb for c, fb in FREEBOARD.items()}
_A_hull_beam = {c: SHIP['Lpp'] * fb for c, fb in FREEBOARD.items()}
_A_super_head = SUPER_WIDTH_FRAC_OF_B * SHIP['B'] * SUPER_HEIGHT_M
_A_super_beam = SUPER_LENGTH_FRAC_OF_LPP * SHIP['Lpp'] * SUPER_HEIGHT_M

A_T_HEAD_BY_BALLAST = {c: _A_hull_head[c] + _A_super_head for c in FREEBOARD}
A_T_BEAM_BY_BALLAST = {c: _A_hull_beam[c] + _A_super_beam for c in FREEBOARD}

C_AA_HEAD = 0.85


def R_calm(V_ms: float, k_R: float = K_R) -> float:
    return k_R * V_ms ** 2


def R_calm_cond(V_ms: float, ballast_condition: str) -> float:
    return K_R_BALLAST[ballast_condition] * V_ms ** 2


def thrust_from_prop(V_ms, rpm, w=W_FRAC, D=SHIP['D_prop'], rho=RHO_SW):
    n = rpm / 60.0
    Va = (1 - w) * V_ms
    J = Va / (n * D) if n > 0 else 0.0
    J = np.clip(J, KTKQ['J'].min(), KTKQ['J'].max())
    return float(KT_OF_J(J)) * rho * n ** 2 * D ** 4


def torque_from_prop(V_ms, rpm, w=W_FRAC, D=SHIP['D_prop'], rho=RHO_SW):
    n = rpm / 60.0
    Va = (1 - w) * V_ms
    J = Va / (n * D) if n > 0 else 0.0
    J = np.clip(J, KTKQ['J'].min(), KTKQ['J'].max())
    return float(KQ_OF_J(J)) * rho * n ** 2 * D ** 5


def solve_equilibrium_speed(rpm, Hs, Tp, mean_wave_dir_deg, ship_heading_deg,
                             t=T_FRAC, V_guess_range=(0.5, 25.0)):
    """Single-condition (laden-implicit), no wind. Validation cross-check only."""
    def imbalance(V_ms):
        V_kn = V_ms / 0.514444
        R_total = R_calm(V_ms) + added_resistance_waves(
            Hs, Tp, V_kn, mean_wave_dir_deg, ship_heading_deg)
        T_available = thrust_from_prop(V_ms, rpm) * (1 - t)
        return T_available - R_total

    lo, hi = V_guess_range
    if imbalance(lo) * imbalance(hi) > 0:
        return None
    return brentq(imbalance, lo, hi, xtol=1e-4)


def relative_wind(u10, v10, V_ship_kn, ship_heading_deg):
    """Returns (V_rel_ms, angle_from_bow_deg)."""
    heading_rad = np.radians(ship_heading_deg)
    V_ship_ms = V_ship_kn * 0.514444
    ship_vx = V_ship_ms * np.sin(heading_rad)
    ship_vy = V_ship_ms * np.cos(heading_rad)

    rel_u = u10 - ship_vx
    rel_v = v10 - ship_vy
    V_rel_ms = np.hypot(rel_u, rel_v)

    wind_bearing = np.degrees(np.arctan2(-rel_u, -rel_v)) % 360
    angle = np.abs(((wind_bearing - ship_heading_deg + 180) % 360) - 180)
    return V_rel_ms, angle


def A_T(angle_from_bow_deg, ballast_condition):
    A_head = A_T_HEAD_BY_BALLAST[ballast_condition]
    A_beam = A_T_BEAM_BY_BALLAST[ballast_condition]
    frac = np.sin(np.radians(angle_from_bow_deg))
    return A_head + (A_beam - A_head) * frac


def C_AA(angle_from_bow_deg, C_head=C_AA_HEAD):
    angle_rad = np.radians(angle_from_bow_deg)
    shape = 0.5 * (1 + np.cos(angle_rad))
    return C_head * (0.10 + 0.90 * shape)


def R_wind(u10, v10, V_ship_kn, ship_heading_deg, ballast_condition):
    V_rel_ms, angle = relative_wind(u10, v10, V_ship_kn, ship_heading_deg)
    Cd = C_AA(angle)
    A = A_T(angle, ballast_condition)
    return 0.5 * RHO_AIR * Cd * A * V_rel_ms ** 2