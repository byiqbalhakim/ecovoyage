import numpy as np
import pandas as pd

from .baseline import best_baseline_rpm


def compute_deadline_h(total_dist_nm: float, service_speed_kn: float = 16.8,
                        buffer_frac: float = 1.08) -> float:
    return (total_dist_nm / service_speed_kn) * buffer_frac


def run_dp_optimizer(cost_table, legs, deadline_h, time_bin_h=0.1):
    n_legs = len(legs)
    max_time_bins = int(np.ceil(deadline_h / time_bin_h)) + 1
    time_grid = np.arange(max_time_bins) * time_bin_h

    cost_lookup = {
        leg_id: grp[['rpm', 'time_h', 'fuel_t', 'V_kn']].to_dict('records')
        for leg_id, grp in cost_table.groupby('leg_id')
    }
    

    INF = float('inf')
    dp = [dict() for _ in range(n_legs + 1)]
    dp[n_legs] = {t_idx: (0.0, None, 0.0) for t_idx in range(max_time_bins)}

    for leg_id in reversed(range(n_legs)):
        for t_idx in range(max_time_bins):
            t_remaining = time_grid[t_idx]
            best_fuel, best_rpm, best_time = INF, None, None
            for action in cost_lookup[leg_id]:
                if action['time_h'] > t_remaining + 1e-6:
                    continue
                t_left_after = t_remaining - action['time_h']
                t_idx_after = min(round(t_left_after / time_bin_h), max_time_bins - 1)
                t_idx_after = max(t_idx_after, 0)
                future_fuel, _, _ = dp[leg_id + 1][t_idx_after]
                total_fuel = action['fuel_t'] + future_fuel
                if total_fuel < best_fuel:
                    best_fuel, best_rpm, best_time = total_fuel, action['rpm'], action['time_h']
            dp[leg_id][t_idx] = (best_fuel, best_rpm, best_time)

    t_used = 0.0
    policy_rows = []
    feasible = True
    for leg_id in range(n_legs):
        t_remaining_idx = min(round((deadline_h - t_used) / time_bin_h), max_time_bins - 1)
        t_remaining_idx = max(t_remaining_idx, 0)
        fuel_here, rpm_here, time_here = dp[leg_id][t_remaining_idx]
        if rpm_here is None:
            feasible = False
            break
        policy_rows.append({'leg_id': leg_id, 'rpm': rpm_here})
        t_used += time_here

    # pd.DataFrame([]) has no columns — pin them explicitly even when empty
    policy_df = pd.DataFrame(policy_rows, columns=['leg_id', 'rpm']).merge(
        cost_table, on=['leg_id', 'rpm'], how='left')

    if not feasible:
        return policy_df, float('nan'), float('nan')

    return policy_df, policy_df['fuel_t'].sum(), policy_df['time_h'].sum()


def evaluate_month(cost_table, legs, deadline_h, time_bin_h=0.1):
    """Returns (dp_fuel_t, savings_pct) vs. the best feasible constant-rpm baseline."""
    policy_df, dp_fuel, dp_time = run_dp_optimizer(cost_table, legs, deadline_h, time_bin_h)

    baseline_rpm = best_baseline_rpm(cost_table, legs, deadline_h)
    if baseline_rpm is None or not np.isfinite(dp_fuel):
        return dp_fuel, float('nan')

    baseline_fuel = cost_table[cost_table['rpm'] == baseline_rpm]['fuel_t'].sum()
    savings_pct = 100 * (baseline_fuel - dp_fuel) / baseline_fuel

    return dp_fuel, savings_pct