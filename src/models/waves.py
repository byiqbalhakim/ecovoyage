import numpy as np

from .ship import SHIP

G = 9.80665
RHO_SW = 1025.0

_trapz = getattr(np, 'trapezoid', None) or np.trapz

TARGET_RATIO_AT_HS3 = 0.20
C_AW_OLD = 0.64
# Solved once (cell 36) so R_added/R_calm = 0.20 at Hs=3m/Tp=9s/head/service speed.
# Recompute if ship config, k_R, or eta_D_assumed ever change.
C_AW_CALIBRATED = 3.889


def jonswap_spectrum(omega, Hs: float, Tp: float, gamma: float = 3.3):
    """JONSWAP spectral density S(omega) [m^2 s]."""
    omega = np.asarray(omega, dtype=float)
    omega_p = 2 * np.pi / Tp

    sigma = np.where(omega <= omega_p, 0.07, 0.09)
    r = np.exp(-((omega - omega_p) ** 2) / (2 * sigma ** 2 * omega_p ** 2))

    with np.errstate(divide='ignore', invalid='ignore'):
        pm_shape = omega ** -5 * np.exp(-1.25 * (omega_p / omega) ** 4)
    pm_shape = np.nan_to_num(pm_shape, nan=0.0, posinf=0.0)

    S_unscaled = pm_shape * gamma ** r
    S_unscaled = np.nan_to_num(S_unscaled, nan=0.0)

    domega = np.gradient(omega)
    m0_unscaled = np.sum(S_unscaled * domega)
    target_m0 = Hs ** 2 / 16
    scale = target_m0 / m0_unscaled if m0_unscaled > 0 else 0.0

    return S_unscaled * scale


def raw_bar_transfer(omega, V_kn: float, Lpp: float, B: float, Cb: float,
                      heading_rel_deg, C_AW: float) -> float:
    """
    Jinkine-Ferdinande-type added-resistance transfer function [N/m^2].
    heading_rel_deg: 0 = head sea, 180 = following sea.
    C_AW is a required explicit parameter — never a module-level global.
    """
    V_ms = V_kn * 0.514444
    Fn = V_ms / np.sqrt(G * Lpp)
    omega_bar = omega * np.sqrt(Lpp / G)

    omega_peak = 2.6
    shape = (omega_bar / omega_peak) ** 2 * np.exp(1 - (omega_bar / omega_peak) ** 2)
    shape = np.clip(shape, 0, None)

    magnitude = C_AW * RHO_SW * G * (B ** 2 / Lpp) * Cb * (1 + 2.0 * Fn)

    heading_rad = np.radians(heading_rel_deg)
    heading_factor = np.clip(0.5 * (1 + np.cos(heading_rad)), 0.0, 1.0)
    heading_factor = 0.15 + 0.85 * heading_factor

    return magnitude * shape * heading_factor


def added_resistance_waves(Hs: float, Tp: float, V_kn: float,
                            mean_wave_dir_deg: float, ship_heading_deg: float,
                            Lpp: float = SHIP['Lpp'], B: float = SHIP['B'], Cb: float = SHIP['Cb'],
                            C_AW: float = C_AW_CALIBRATED,
                            n_omega: int = 120, n_dir: int = 60, gamma: float = 3.3) -> float:
    """R_added = 2 * integral(S(omega,mu) * R_AW_bar(omega,mu)) domega dmu, [N]."""
    omega = np.linspace(0.15, 2.5, n_omega)
    S_om = jonswap_spectrum(omega, Hs, Tp, gamma=gamma)

    mu = np.linspace(-np.pi, np.pi, n_dir)
    mu_mean = np.radians(mean_wave_dir_deg)
    dmu = np.mod(mu - mu_mean + np.pi, 2 * np.pi) - np.pi
    D_raw = np.where(np.abs(dmu) <= np.pi / 2, np.cos(dmu) ** 4, 0.0)
    D_norm = D_raw / _trapz(D_raw, mu)

    heading_rel = np.degrees(mu) - ship_heading_deg
    heading_rel = np.mod(heading_rel, 360)
    heading_rel = np.minimum(heading_rel, 360 - heading_rel)

    R_grid = np.zeros((n_omega, n_dir))
    for j in range(n_dir):
        R_grid[:, j] = raw_bar_transfer(omega, V_kn, Lpp, B, Cb, heading_rel[j], C_AW)

    integrand = S_om[:, None] * D_norm[None, :] * R_grid
    return 2 * _trapz(_trapz(integrand, mu, axis=1), omega)