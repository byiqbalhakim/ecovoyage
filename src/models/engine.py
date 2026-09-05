import numpy as np
from scipy.interpolate import interp1d

SMCR_KW = 12400.0

# Columns: Load[%SMCR], Power[kW], Speed[rpm], SFOC[g/kWh]
SFOC_TABLE_ISO = np.array([
    [100, 12400, 92.0, 166.0],
    [95,  11780, 90.4, 164.5],
    [90,  11160, 88.8, 163.2],
    [85,  10540, 87.1, 162.0],
    [80,   9920, 85.4, 160.7],
    [75,   9300, 83.6, 159.5],
    [70,   8680, 81.7, 158.1],
    [65,   8060, 79.7, 157.6],
    [60,   7440, 77.6, 157.7],
    [55,   6820, 75.4, 158.1],
    [50,   6200, 73.0, 158.6],
    [45,   5580, 70.5, 159.8],
    [40,   4960, 67.8, 161.1],
    [35,   4340, 64.8, 162.6],
    [30,   3720, 61.6, 164.2],
    [25,   3100, 58.0, 165.9],
    [20,   2480, 53.8, 167.9],
    [15,   1860, 48.9, 171.9],
    [10,   1240, 42.7, 181.9],
])

SFOC_TABLE_TROP = np.array([
    [100, 12400, 92.0, 167.8],
    [95,  11780, 90.4, 166.3],
    [90,  11160, 88.8, 165.0],
    [85,  10540, 87.1, 163.7],
    [80,   9920, 85.4, 162.4],
    [75,   9300, 83.6, 161.2],
    [70,   8680, 81.7, 159.8],
    [65,   8060, 79.7, 159.3],
    [60,   7440, 77.6, 159.4],
    [55,   6820, 75.4, 159.8],
    [50,   6200, 73.0, 160.3],
    [45,   5580, 70.5, 161.5],
    [40,   4960, 67.8, 162.8],
    [35,   4340, 64.8, 164.3],
    [30,   3720, 61.6, 165.9],
    [25,   3100, 58.0, 167.7],
    [20,   2480, 53.8, 169.7],
    [15,   1860, 48.9, 173.7],
    [10,   1240, 42.7, 183.7],
])

SFOC_TABLE_SPEC = np.array([
    [100, 12400, 92.0, 164.0],
    [95,  11780, 90.4, 162.6],
    [90,  11160, 88.8, 161.3],
    [85,  10540, 87.1, 160.1],
    [80,   9920, 85.4, 158.8],
    [75,   9300, 83.6, 157.6],
    [70,   8680, 81.7, 156.2],
    [65,   8060, 79.7, 155.7],
    [60,   7440, 77.6, 155.8],
    [55,   6820, 75.4, 156.2],
    [50,   6200, 73.0, 156.7],
    [45,   5580, 70.5, 157.9],
    [40,   4960, 67.8, 159.2],
    [35,   4340, 64.8, 160.6],
    [30,   3720, 61.6, 162.2],
    [25,   3100, 58.0, 163.9],
    [20,   2480, 53.8, 165.9],
    [15,   1860, 48.9, 169.9],
    [10,   1240, 42.7, 179.9],
])

SFOC_TABLES = {
    'ISO': SFOC_TABLE_ISO,
    'Tropical': SFOC_TABLE_TROP,
    'Specified': SFOC_TABLE_SPEC,
}


class Engine:
    def __init__(self, condition: str = 'ISO'):
        table = SFOC_TABLES[condition]
        load_pct, power_kw, speed_rpm, sfoc_gkwh = table.T

        self.condition = condition
        self.load_pct = load_pct
        self.power_kw = power_kw
        self.speed_rpm = speed_rpm
        self.sfoc_gkwh = sfoc_gkwh

        self.sfoc_of_load = interp1d(load_pct, sfoc_gkwh, kind='linear', fill_value='extrapolate')
        self.power_of_rpm = interp1d(speed_rpm, power_kw, kind='linear', fill_value='extrapolate')
        self.rpm_of_power = interp1d(power_kw, speed_rpm, kind='linear', fill_value='extrapolate')

    def fuel_rate_tph(self, power_kw_val: float, load_pct_val: float) -> float:
        """Fuel rate [t/h] given Power [kW] and Load [%SMCR]."""
        sfoc = self.sfoc_of_load(load_pct_val)
        return sfoc * power_kw_val / 1e6