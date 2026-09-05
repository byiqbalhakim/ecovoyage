import numpy as np
import pandas as pd
from scipy.interpolate import interp1d

from .ship import SHIP

# Empirical, single-screw approximations — no model-test data available
W_FRAC = 0.5 * SHIP['Cb'] - 0.05
T_FRAC = 0.325 * SHIP['Cb'] - 0.1885 * SHIP['D_prop'] / np.sqrt(SHIP['B'] * SHIP['T_full'])


def _load_ktkq(path: str = 'kt_kq_j.csv') -> pd.DataFrame:
    raw = pd.read_csv(path, skiprows=1)
    raw.columns = ['J', 'Kt', 'Kq', 'eta_O']
    return raw.apply(pd.to_numeric, errors='coerce').dropna().reset_index(drop=True)


KTKQ = _load_ktkq()
KT_OF_J = interp1d(KTKQ['J'], KTKQ['Kt'], kind='linear', fill_value='extrapolate')
KQ_OF_J = interp1d(KTKQ['J'], KTKQ['Kq'], kind='linear', fill_value='extrapolate')


def advance_coefficient(V_kn: float, rpm: float, w: float = W_FRAC, D: float = SHIP['D_prop']) -> float:
    """J = Va / (n*D), Va = (1-w)*V."""
    V_ms = V_kn * 0.514444
    Va = (1 - w) * V_ms
    n = rpm / 60.0
    return Va / (n * D)