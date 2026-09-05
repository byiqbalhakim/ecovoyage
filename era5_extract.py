import pandas as pd
import xarray as xr

from src.data.routes import load_passage_plan, build_route_corridor


def extract_route_weather(wave_path, oper_path, route_csv_path, buffer_nm=3.0, out_csv=None):
    route = load_passage_plan(route_csv_path)
    corridor = build_route_corridor(route['waypoints'], buffer_nm=buffer_nm)

    dep_dt = pd.Timestamp(route['dep_date'])
    arrival_dt = dep_dt + pd.Timedelta(hours=route['eta_hours'])

    ds_wave = xr.open_dataset(wave_path).sel(valid_time=slice(dep_dt, arrival_dt))
    ds_wind = xr.open_dataset(oper_path).sel(valid_time=slice(dep_dt, arrival_dt))

    records = []
    for _, row in corridor.iterrows():
        lat, lon = row['lat'], row['lon']
        wave_pt = ds_wave[['swh', 'mwd', 'pp1d']].sel(latitude=lat, longitude=lon, method='nearest')
        wind_pt = ds_wind[['u10', 'v10']].sel(latitude=lat, longitude=lon, method='nearest')

        df_wave = wave_pt.to_dataframe().reset_index()
        df_wind = wind_pt.to_dataframe().reset_index()

        df_pt = pd.merge(df_wave, df_wind, on='valid_time', suffixes=('', '_wind'))
        df_pt['leg_point'] = row['leg_point']
        df_pt['buffer_side'] = row['buffer_side']
        df_pt['waypoint_lat'] = lat
        df_pt['waypoint_lon'] = lon
        records.append(df_pt)

    route_data = pd.concat(records, ignore_index=True)
    route_data = route_data[['valid_time', 'leg_point', 'buffer_side', 'waypoint_lat', 'waypoint_lon',
                              'swh', 'pp1d', 'mwd', 'u10', 'v10']]
    route_data.columns = ['datetime', 'leg_point', 'buffer_side', 'lat', 'lon',
                           'hs_m', 'tp_s', 'wave_dir_deg', 'u10_ms', 'v10_ms']

    if out_csv is None:
        pol = str(route['pol']).replace(' ', '_').replace('(', '').replace(')', '')
        pod = str(route['pod']).replace(' ', '_').replace('(', '').replace(')', '')
        out_csv = f'era5_route_{pol}_to_{pod}.csv'

    route_data.to_csv(out_csv, index=False)
    return route_data