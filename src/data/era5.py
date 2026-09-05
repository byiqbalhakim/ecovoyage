import numpy as np
import pandas as pd

from ..config import ERA5_CSV_PATH


def load_era5(csv_path=ERA5_CSV_PATH) -> pd.DataFrame:
    route_data = pd.read_csv(csv_path, parse_dates=['datetime'])
    return _fix_point10_nan(route_data)


def _fix_point10_nan(route_data: pd.DataFrame) -> pd.DataFrame:
    for _, grp in route_data.groupby(route_data['datetime'].dt.to_period('M')):
        pt10_idx = grp[grp['leg_point'] == 10].index
        pt9_vals = grp[grp['leg_point'] == 9].set_index('datetime')[['hs_m', 'tp_s', 'wave_dir_deg']]
        for idx in pt10_idx:
            dt = route_data.loc[idx, 'datetime']
            if pd.isna(route_data.loc[idx, 'hs_m']) and dt in pt9_vals.index:
                route_data.loc[idx, ['hs_m', 'tp_s', 'wave_dir_deg']] = pt9_vals.loc[dt].values
    return route_data


def _filter_corridor_center(route_data: pd.DataFrame) -> pd.DataFrame:
    if 'buffer_side' in route_data.columns:
        return route_data[route_data['buffer_side'] == 'center'].drop(columns='buffer_side')
    return route_data


def _summarize(route_data: pd.DataFrame, group_cols: list) -> pd.DataFrame:
    summary = route_data.groupby(group_cols).agg(
        hs_mean=('hs_m', 'mean'), hs_max=('hs_m', 'max'),
        tp_mean=('tp_s', 'mean'), wave_dir_mean=('wave_dir_deg', 'mean'),
        lat=('lat', 'first'), lon=('lon', 'first'),
    ).reset_index()

    route_data = route_data.copy()
    route_data['wind_speed_inst'] = np.sqrt(route_data['u10_ms'] ** 2 + route_data['v10_ms'] ** 2)

    wind_summary = route_data.groupby(group_cols).agg(
        wind_speed_mean=('wind_speed_inst', 'mean'),
        wind_speed_std=('wind_speed_inst', 'std'),
        u10_vec_mean=('u10_ms', 'mean'),
        v10_vec_mean=('v10_ms', 'mean'),
    ).reset_index()

    wind_summary['wind_vec_mean_speed'] = np.sqrt(
        wind_summary['u10_vec_mean'] ** 2 + wind_summary['v10_vec_mean'] ** 2)
    wind_summary['wind_dir_variance_flag'] = (
        wind_summary['wind_speed_mean'] - wind_summary['wind_vec_mean_speed']
    ) / wind_summary['wind_speed_mean'].clip(lower=1e-6)

    return summary.merge(wind_summary, on=group_cols, how='left')


def extract_route_weather(route_data: pd.DataFrame) -> pd.DataFrame:
    """Climatology mode: one row per leg_point per calendar month."""
    route_data = _filter_corridor_center(route_data)
    period = route_data['datetime'].dt.to_period('M')
    return _summarize(route_data.assign(datetime=period), ['leg_point', 'datetime'])


def build_leg_weather_summary(route_data: pd.DataFrame, legs: pd.DataFrame,
                               leg_etas: pd.DataFrame) -> pd.DataFrame:
    """Voyage mode: one row per leg_id, sampled at that leg's own estimated arrival window."""
    route_data = _filter_corridor_center(route_data)
    rows = []
    for _, leg in legs.iterrows():
        leg_id = leg['leg_id']
        to_pt = leg['to_pt']
        eta = leg_etas[leg_etas['leg_id'] == leg_id].iloc[0]

        at_point = route_data[route_data['leg_point'] == to_pt]
        window = at_point[(at_point['datetime'] >= eta['dep_time']) & (at_point['datetime'] <= eta['arr_time'])]
        if window.empty:
            nearest_idx = (at_point['datetime'] - eta['arr_time']).abs().idxmin()
            window = at_point.loc[[nearest_idx]]

        summarized = _summarize(window, ['leg_point'])
        summarized['leg_id'] = leg_id
        rows.append(summarized)
    return pd.concat(rows, ignore_index=True)