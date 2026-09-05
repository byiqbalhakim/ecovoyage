import numpy as np
import pandas as pd
from ..config import ROUTE_DEFINITIONS_PATH
from math import radians, degrees, sin, cos, asin, atan2


def destination_point(lat, lon, bearing_deg, distance_nm):
    R_nm = 3440.065
    lat1, lon1, brng = radians(lat), radians(lon), radians(bearing_deg)
    d_ang = distance_nm / R_nm
    lat2 = asin(sin(lat1) * cos(d_ang) + cos(lat1) * sin(d_ang) * cos(brng))
    lon2 = lon1 + atan2(sin(brng) * sin(d_ang) * cos(lat1), cos(d_ang) - sin(lat1) * sin(lat2))
    return degrees(lat2), degrees(lon2)


def build_route_corridor(waypoints: pd.DataFrame, buffer_nm: float = 3.0) -> pd.DataFrame:
    """
    One center point per waypoint plus a left/right point offset perpendicular
    to the adjacent leg's course. Not consumed by the current optimizer --
    captured for future routing/deviation work.
    """
    n = len(waypoints)
    points = []
    for i in range(n):
        lat, lon = waypoints.loc[i, ['lat', 'lon']]
        if i < n - 1:
            lat2, lon2 = waypoints.loc[i + 1, ['lat', 'lon']]
            course = initial_bearing_deg(lat, lon, lat2, lon2)
        else:
            lat0, lon0 = waypoints.loc[i - 1, ['lat', 'lon']]
            course = initial_bearing_deg(lat0, lon0, lat, lon)

        points.append({'leg_point': i, 'buffer_side': 'center', 'lat': lat, 'lon': lon})
        for side, offset in [('left', -90), ('right', 90)]:
            lat_b, lon_b = destination_point(lat, lon, (course + offset) % 360, buffer_nm)
            points.append({'leg_point': i, 'buffer_side': side, 'lat': lat_b, 'lon': lon_b})

    return pd.DataFrame(points)

def load_route_definition(route_id: str, path=ROUTE_DEFINITIONS_PATH) -> dict:
    routes = pd.read_csv(path)
    row = routes[routes['route_id'] == route_id]
    if row.empty:
        raise ValueError(f"No route definition found for route_id='{route_id}' in {path}")
    row = row.iloc[0]
    return {
        'route_id': row['route_id'],
        'name': row['name'],
        'origin_latlon': (row['origin_lat'], row['origin_lon']),
        'dest_latlon': (row['dest_lat'], row['dest_lon']),
        'n_waypoints': int(row['n_waypoints']),
    }

def haversine_nm(lat1, lon1, lat2, lon2):
    import numpy as np
    R_nm = 3440.065
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 2 * R_nm * np.arcsin(np.sqrt(a))


def initial_bearing_deg(lat1, lon1, lat2, lon2):
    import numpy as np
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlon = lon2 - lon1
    x = np.sin(dlon) * np.cos(lat2)
    y = np.cos(lat1) * np.sin(lat2) - np.sin(lat1) * np.cos(lat2) * np.cos(dlon)
    return (np.degrees(np.arctan2(x, y)) + 360) % 360


def load_passage_plan(path: str) -> dict:
    raw = pd.read_csv(path, header=None)

    meta_row = raw.iloc[2]
    eta_hours = float(meta_row[0])
    pol = meta_row[1]
    pod = meta_row[2]
    eta_tolerance_h = float(meta_row[3])
    dep_date = meta_row[4]
    laden_condition = str(meta_row[5]).strip().upper() == 'TRUE'

    header_row_idx = raw[raw[0] == 'Point'].index[0]
    waypoints = raw.iloc[header_row_idx + 1:, :3].copy()
    waypoints.columns = ['point', 'lat', 'lon']
    waypoints = waypoints.dropna(subset=['lat', 'lon']).reset_index(drop=True)
    waypoints['lat'] = waypoints['lat'].astype(float)
    waypoints['lon'] = waypoints['lon'].astype(float)

    return {
        'eta_hours': eta_hours,
        'eta_tolerance_h': eta_tolerance_h,
        'pol': pol,
        'pod': pod,
        'dep_date': dep_date,
        'laden_condition': laden_condition,
        'waypoints': waypoints,
    }


def build_route_from_waypoints(waypoints: pd.DataFrame) -> pd.DataFrame:
    legs = []
    for i in range(len(waypoints) - 1):
        lat1, lon1 = waypoints.loc[i, ['lat', 'lon']]
        lat2, lon2 = waypoints.loc[i + 1, ['lat', 'lon']]
        legs.append({
            'leg_id': i,
            'from_pt': i,
            'to_pt': i + 1,
            'dist_nm': haversine_nm(lat1, lon1, lat2, lon2),
            'course_deg': initial_bearing_deg(lat1, lon1, lat2, lon2),
        })
    return pd.DataFrame(legs)

def estimate_leg_arrival_times(legs: pd.DataFrame, dep_date, baseline_speed_kn: float) -> pd.DataFrame:
    """Single-pass ETA per leg using a constant speed -- not re-solved against
    the DP's actual chosen RPM. Approximation, not a routing solution."""
    dep_dt = pd.Timestamp(dep_date)
    cum_h = 0.0
    rows = []
    for _, leg in legs.iterrows():
        transit_h = leg['dist_nm'] / baseline_speed_kn
        rows.append({
            'leg_id': leg['leg_id'],
            'dep_time': dep_dt + pd.Timedelta(hours=cum_h),
            'arr_time': dep_dt + pd.Timedelta(hours=cum_h + transit_h),
        })
        cum_h += transit_h
    return pd.DataFrame(rows)