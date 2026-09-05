import pandas as pd

SESSION_GAP_MIN = 15
WINDOW_MIN = 30
RPM_CV_MAX = 0.03
MIN_SAMPLES = 4
SOG_MIN = 5.0
FUEL_STD_MIN = 0.5
FUEL_CLIP_CEILING = 1000.0

AGG_SPEC = {
    '1_Pickup11': ['mean', 'std', 'count'],
    '2_Fuel_eff': 'mean',
    '3_ME_tot_FL': 'mean',
    '4_Nav_02': 'mean',
    '11_Trim_in_meters': 'mean',
    '18_Significant_wave_height': 'mean',
    '19_Wave_direction': 'mean',
    '20_Wave_period': 'mean',
    '15_Uwind': 'mean',
    '16_Vwind': 'mean',
    '17_Gust': 'mean',
    '21_struja_smjer_deg': 'mean',
    '22_struja_brzina': 'mean',
    '13_ballast': 'first',
    '0_datetime': ['first', 'last'],
}

COLUMN_RENAME = {
    '1_Pickup11_mean': 'rpm_mean', '1_Pickup11_std': 'rpm_std', '1_Pickup11_count': 'n_samples',
    '2_Fuel_eff_mean': 'fuel_mean',
    '3_ME_tot_FL_mean': 'load_pct_mean',
    '4_Nav_02_mean': 'sog_mean',
    '11_Trim_in_meters_mean': 'trim_mean',
    '18_Significant_wave_height_mean': 'wave_ht',
    '19_Wave_direction_mean': 'wave_dir',
    '20_Wave_period_mean': 'wave_period',
    '15_Uwind_mean': 'uwind', '16_Vwind_mean': 'vwind', '17_Gust_mean': 'gust',
    '21_struja_smjer_deg_mean': 'current_dir', '22_struja_brzina_mean': 'current_speed',
    '13_ballast_first': 'ballast',
    '0_datetime_first': 't_start', '0_datetime_last': 't_end',
}


def load_and_clean(path: str = 'sup_data/SeagoingShip-Sensor-data.csv') -> pd.DataFrame:
    raw = pd.read_csv(path)
    raw['0_datetime'] = pd.to_datetime(raw['0_datetime'])
    raw = raw.sort_values('0_datetime').reset_index(drop=True)

    clean = raw[(raw['1_Pickup11'] != -1) & (raw['3_ME_tot_FL'] != -1)].reset_index(drop=True)

    gap = clean['0_datetime'].diff()
    session_break = gap > pd.Timedelta(minutes=SESSION_GAP_MIN)
    clean['session_id'] = session_break.cumsum()

    clean['fuel_clipped'] = clean['2_Fuel_eff'] >= FUEL_CLIP_CEILING
    return clean


def add_time_bins(clean: pd.DataFrame) -> pd.DataFrame:
    clean = clean.copy()
    clean['t_bin'] = clean.groupby('session_id')['0_datetime'].transform(
        lambda s: ((s - s.iloc[0]).dt.total_seconds() // (WINDOW_MIN * 60)).astype(int)
    )
    return clean


def build_steady_windows(clean_binned: pd.DataFrame) -> pd.DataFrame:
    """Expects clean_binned to already have a 't_bin' column (see add_time_bins)."""
    windows = clean_binned.groupby(['session_id', 't_bin']).agg(AGG_SPEC)
    windows.columns = ['_'.join(c).strip('_') for c in windows.columns]
    windows = windows.reset_index().rename(columns=COLUMN_RENAME)

    windows = windows[windows['n_samples'] >= MIN_SAMPLES].copy()

    windows['rpm_cv'] = windows['rpm_std'] / windows['rpm_mean']
    return windows[windows['rpm_cv'] < RPM_CV_MAX].copy().reset_index(drop=True)


def clean_sensor_data(clean: pd.DataFrame, candidates: pd.DataFrame) -> pd.DataFrame:
    """Fuel-validity, clipped-sensor, low-SOG, frozen-sensor exclusions -> locked set."""
    cal_valid = candidates[candidates['fuel_mean'] > 0].copy()

    clip_flag = clean.groupby(['session_id', 't_bin'])['fuel_clipped'].any().rename('has_clipped_sample')
    cal_valid = cal_valid.merge(clip_flag, left_on=['session_id', 't_bin'], right_index=True, how='left')
    cal_final = cal_valid[~cal_valid['has_clipped_sample']].copy()

    fuel_var = clean.groupby(['session_id', 't_bin'])['2_Fuel_eff'].std().rename('fuel_std_raw')
    cal_final = cal_final.merge(fuel_var, left_on=['session_id', 't_bin'], right_index=True, how='left')

    return cal_final[
        (cal_final['sog_mean'] >= SOG_MIN) &
        (cal_final['fuel_std_raw'] >= FUEL_STD_MIN)
    ].copy()