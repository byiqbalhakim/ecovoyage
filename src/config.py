from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SENSOR_DATA_PATH = BASE_DIR / 'data' / 'raw' / 'SeagoingShip-Sensor-data.csv'
ERA5_CSV_PATH = BASE_DIR / 'data' / 'processed' / 'era5_route_rotterdam_ny_2025.csv' # Change this
KTKQ_CSV_PATH = BASE_DIR / 'kt_kq_j.csv'
ROUTE_DEFINITIONS_PATH = BASE_DIR / 'data' / 'routes' / 'rotterdam_ny.csv'

DEFAULT_ROUTE_ID = 'rotterdam_ny'

SERVICE_SPEED_KN = 16.8
DEADLINE_BUFFER_FRAC = 1.08

RPM_MIN = 55
RPM_MAX = 93
RPM_STEP = 2.0

DEFAULT_BALLAST_CONDITION = 'laden'
DEFAULT_ENGINE_CONDITION = 'ISO'