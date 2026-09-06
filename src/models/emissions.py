"""
CO2 and CII (Carbon Intensity Indicator) calculations, per IMO MEPC.354(78)
and MEPC.353(78)/MEPC.338(76). Pure functions -- a new addition on top of
the frozen Track A pipeline, not an extraction from the notebook.
"""

import numpy as np

CO2_FACTOR_HFO = 3.114  # tCO2 per tonne of fuel burned (HFO)
CO2_FACTOR_MGO = 3.206  # tCO2 per tonne of fuel burned (MGO), if fuel type changes

# IMO reference line: CII_ref = a * DWT^(-c).
# Source: IMO Resolution MEPC.353(78), Table 1.
# Each ship type maps to a list of (dwt_upper_bound, a, c) brackets --
# pick the first bracket whose upper bound the vessel's DWT falls under.
# None as upper_bound means "this bracket covers everything above the
# previous one" (i.e. the largest-size row).
CII_REFERENCE_PARAMS = {
    'gas_carrier': [
        (65000, 8104, 0.639),      # < 65,000 DWT
        (None, 14405e6, 2.071),    # >= 65,000 DWT
    ],
}

CII_RATING_BOUNDARIES = {'d1': 0.86, 'd2': 0.94, 'd3': 1.06, 'd4': 1.18}


def fuel_to_co2(fuel_t: float, factor: float = CO2_FACTOR_HFO) -> float:
    return fuel_t * factor


def attained_cii(total_co2_t: float, dwt: float, total_dist_nm: float) -> float:
    if dwt <= 0 or total_dist_nm <= 0:
        return float('nan')
    return (total_co2_t * 1e6) / (dwt * total_dist_nm)


def cii_reference_value(dwt: float, ship_type: str = 'gas_carrier') -> float:
    """CII_ref = a * DWT^(-c), picking the correct bracket for this vessel's size."""
    brackets = CII_REFERENCE_PARAMS[ship_type]
    for upper_bound, a, c in brackets:
        if upper_bound is None or dwt < upper_bound:
            return a * dwt ** (-c)
    raise ValueError(f"No CII reference bracket matched DWT={dwt}")


def cii_rating(attained: float, reference: float) -> str:
    if reference <= 0 or np.isnan(attained):
        return 'N/A'
    ratio = attained / reference
    b = CII_RATING_BOUNDARIES
    if ratio <= b['d1']:
        return 'A'
    elif ratio <= b['d2']:
        return 'B'
    elif ratio <= b['d3']:
        return 'C'
    elif ratio <= b['d4']:
        return 'D'
    else:
        return 'E'


def voyage_cii(total_fuel_t: float, dwt: float, total_dist_nm: float,
               ship_type: str = 'gas_carrier', fuel_co2_factor: float = CO2_FACTOR_HFO) -> dict:
    total_co2_t = fuel_to_co2(total_fuel_t, fuel_co2_factor)
    attained = attained_cii(total_co2_t, dwt, total_dist_nm)
    reference = cii_reference_value(dwt, ship_type)
    rating = cii_rating(attained, reference)
    return {
        'total_co2_t': total_co2_t,
        'attained_cii': attained,
        'reference_cii': reference,
        'cii_rating': rating,
    }