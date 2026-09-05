from .leg_cost import RPM_CANDIDATES


def best_baseline_rpm(cost_table, legs, deadline_h):
    n_legs = len(legs)
    rows = []
    for rpm in RPM_CANDIDATES:
        grp = cost_table[cost_table['rpm'] == rpm]
        if len(grp) != n_legs:
            continue
        total_t, total_f = grp['time_h'].sum(), grp['fuel_t'].sum()
        if total_t <= deadline_h:
            rows.append((rpm, total_f))
    rows.sort(key=lambda r: r[1])
    return rows[0][0] if rows else None
    