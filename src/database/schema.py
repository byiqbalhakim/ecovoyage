"""
Table definitions (Phases 5-9 of the master to-do).

Each string below is one CREATE TABLE statement ("DDL" = Data Definition
Language, as opposed to the SELECT/INSERT/UPDATE "DML" queries in
queries.py). Grouped in the same order as the to-do:

  5. Vessel config      -> vessels, engine_sfoc, propeller_curve
  6. Sensor data         -> sensor_observations, sensor_calibration_windows
  7. Weather             -> weather_era5
  8. Routes              -> routes, route_points, route_legs
  9. Predictions         -> voyage_predictions, prediction_legs

A few SQLite-specific notes that explain some of the syntax below:
  - INTEGER PRIMARY KEY is SQLite's auto-incrementing row ID. You never
    set this yourself; SQLite fills it in when you INSERT.
  - REAL is SQLite's floating-point type (equivalent to Python float).
  - TEXT covers strings, and also dates/timestamps (SQLite has no
    dedicated datetime type -- we store ISO-format strings, e.g.
    '2025-01-15T00:00:00', which sort correctly as plain text).
  - "FOREIGN KEY ... REFERENCES parent(col)" says "this column must
    match an existing row in the parent table." ON DELETE CASCADE means
    "if the parent row is deleted, delete these children too" -- e.g.
    deleting a route also deletes its legs, so you can't end up with
    orphaned route_legs pointing at a route_id that no longer exists.
"""

VESSELS = """
CREATE TABLE IF NOT EXISTS vessels (
    vessel_id       INTEGER PRIMARY KEY,
    name            TEXT NOT NULL,
    lpp             REAL NOT NULL,
    beam            REAL NOT NULL,
    t_full          REAL NOT NULL,
    t_ballast       REAL NOT NULL,
    depth           REAL NOT NULL,
    dwt             REAL,
    cb              REAL NOT NULL,
    d_prop          REAL NOT NULL,
    pitch           REAL NOT NULL,
    v_service_kn    REAL NOT NULL,
    p_service_kw    REAL NOT NULL
)
"""

ENGINE_SFOC = """
CREATE TABLE IF NOT EXISTS engine_sfoc (
    id              INTEGER PRIMARY KEY,
    vessel_id       INTEGER NOT NULL REFERENCES vessels(vessel_id) ON DELETE CASCADE,
    condition       TEXT NOT NULL,     -- 'ISO' / 'Tropical' / 'Specified'
    load_pct        REAL NOT NULL,
    power_kw        REAL NOT NULL,
    speed_rpm       REAL NOT NULL,
    sfoc_gkwh       REAL NOT NULL
)
"""

PROPELLER_CURVE = """
CREATE TABLE IF NOT EXISTS propeller_curve (
    id              INTEGER PRIMARY KEY,
    vessel_id       INTEGER NOT NULL REFERENCES vessels(vessel_id) ON DELETE CASCADE,
    j               REAL NOT NULL,     -- advance coefficient
    kt              REAL NOT NULL,
    kq              REAL NOT NULL,
    eta_o           REAL
)
"""

SENSOR_OBSERVATIONS = """
CREATE TABLE IF NOT EXISTS sensor_observations (
    id              INTEGER PRIMARY KEY,
    vessel_id       INTEGER NOT NULL REFERENCES vessels(vessel_id) ON DELETE CASCADE,
    datetime        TEXT NOT NULL,
    rpm             REAL,
    fuel_rate       REAL,
    load_pct        REAL,
    sog             REAL,
    trim_m          REAL,
    wave_ht         REAL,
    wave_dir        REAL,
    wave_period     REAL,
    uwind           REAL,
    vwind           REAL,
    gust            REAL,
    current_dir     REAL,
    current_speed   REAL,
    ballast         TEXT,
    is_fuel_clipped INTEGER DEFAULT 0   -- SQLite has no BOOLEAN type; 0/1 stands in for False/True
)
"""

SENSOR_CALIBRATION_WINDOWS = """
CREATE TABLE IF NOT EXISTS sensor_calibration_windows (
    id                  INTEGER PRIMARY KEY,
    vessel_id           INTEGER NOT NULL REFERENCES vessels(vessel_id) ON DELETE CASCADE,
    session_id          INTEGER NOT NULL,
    t_bin               INTEGER NOT NULL,
    t_start             TEXT,
    t_end               TEXT,
    rpm_mean            REAL,
    rpm_std             REAL,
    rpm_cv              REAL,
    n_samples           INTEGER,
    fuel_mean           REAL,
    load_pct_mean       REAL,
    sog_mean            REAL,
    ballast             TEXT,
    passed_all_filters  INTEGER DEFAULT 0  -- 1 = survived load_and_clean + clean_sensor_data (cell 31's cal_locked)
)
"""

WEATHER_ERA5 = """
CREATE TABLE IF NOT EXISTS weather_era5 (
    id              INTEGER PRIMARY KEY,
    datetime        TEXT NOT NULL,
    route_id        TEXT NOT NULL,
    leg_point       INTEGER NOT NULL,
    lat             REAL NOT NULL,
    lon             REAL NOT NULL,
    hs_m            REAL,
    tp_s            REAL,
    wave_dir_deg    REAL,
    u10_ms          REAL,
    v10_ms          REAL,
    UNIQUE(datetime, route_id, leg_point)  -- prevents accidentally loading the same ERA5 row twice
)
"""

ROUTES = """
CREATE TABLE IF NOT EXISTS routes (
    route_id        TEXT PRIMARY KEY,    -- e.g. 'rotterdam_ny', a slug, not an auto-int
    name            TEXT NOT NULL,
    origin_lat      REAL NOT NULL,
    origin_lon      REAL NOT NULL,
    dest_lat        REAL NOT NULL,
    dest_lon        REAL NOT NULL,
    n_waypoints     INTEGER NOT NULL
)
"""

ROUTE_POINTS = """
CREATE TABLE IF NOT EXISTS route_points (
    id              INTEGER PRIMARY KEY,
    route_id        TEXT NOT NULL REFERENCES routes(route_id) ON DELETE CASCADE,
    point_index     INTEGER NOT NULL,
    lat             REAL NOT NULL,
    lon             REAL NOT NULL,
    UNIQUE(route_id, point_index)
)
"""

ROUTE_LEGS = """
CREATE TABLE IF NOT EXISTS route_legs (
    id              INTEGER PRIMARY KEY,
    route_id        TEXT NOT NULL REFERENCES routes(route_id) ON DELETE CASCADE,
    leg_id          INTEGER NOT NULL,
    from_pt         INTEGER NOT NULL,
    to_pt           INTEGER NOT NULL,
    dist_nm         REAL NOT NULL,
    course_deg      REAL NOT NULL,
    UNIQUE(route_id, leg_id)
)
"""

VOYAGE_PREDICTIONS = """
CREATE TABLE IF NOT EXISTS voyage_predictions (
    prediction_id       INTEGER PRIMARY KEY,
    route_id             TEXT NOT NULL REFERENCES routes(route_id),
    vessel_id            INTEGER NOT NULL REFERENCES vessels(vessel_id),
    weather_period        TEXT NOT NULL,     -- e.g. '2025-01'
    ballast_condition     TEXT NOT NULL,
    deadline_h            REAL NOT NULL,
    include_wind          INTEGER DEFAULT 0,
    dp_fuel_t             REAL,
    baseline_rpm          REAL,
    baseline_fuel_t       REAL,
    savings_pct           REAL,
    is_feasible           INTEGER DEFAULT 1,
    created_at            TEXT NOT NULL      -- when this prediction was run, for audit/history
)
"""

PREDICTION_LEGS = """
CREATE TABLE IF NOT EXISTS prediction_legs (
    id              INTEGER PRIMARY KEY,
    prediction_id   INTEGER NOT NULL REFERENCES voyage_predictions(prediction_id) ON DELETE CASCADE,
    leg_id          INTEGER NOT NULL,
    rpm             REAL NOT NULL,
    time_h          REAL NOT NULL,
    fuel_t          REAL NOT NULL,
    v_kn            REAL,
    load_pct        REAL
)
"""

DASHBOARD_LEG_VIEW = """
CREATE TABLE IF NOT EXISTS dashboard_leg_view (
    id              INTEGER PRIMARY KEY,
    prediction_id   INTEGER NOT NULL REFERENCES voyage_predictions(prediction_id) ON DELETE CASCADE,
    route_id        TEXT NOT NULL,
    weather_period  TEXT NOT NULL,
    leg_id          INTEGER NOT NULL,
    leg_label       TEXT NOT NULL,      -- e.g. "Leg 3" -- pre-formatted for an axis label
    dp_rpm          REAL NOT NULL,
    dp_fuel_t       REAL NOT NULL,
    dp_time_h       REAL NOT NULL,
    dp_v_kn         REAL,
    baseline_rpm    REAL NOT NULL,
    baseline_fuel_t REAL NOT NULL,      -- this leg's share of the baseline total, split proportionally by time
    cum_dp_fuel_t   REAL NOT NULL,      -- running total -- lets a "fuel used so far" chart skip a client-side cumsum
    hs_m            REAL,               -- sea state at this leg, pulled in so a weather overlay chart needs no join
    wind_speed_ms   REAL
)
"""

DASHBOARD_SUMMARY_VIEW = """
CREATE TABLE IF NOT EXISTS dashboard_summary_view (
    prediction_id     INTEGER PRIMARY KEY REFERENCES voyage_predictions(prediction_id) ON DELETE CASCADE,
    route_id          TEXT NOT NULL,
    route_name        TEXT NOT NULL,
    weather_period    TEXT NOT NULL,
    weather_label     TEXT NOT NULL,     -- e.g. "January 2025 (harsh)" -- pre-written for display
    ballast_condition TEXT NOT NULL,
    dp_fuel_t         REAL,
    baseline_fuel_t   REAL,
    savings_pct       REAL,
    savings_label     TEXT,              -- e.g. "3.4% saved" -- ready to drop straight into a card
    is_feasible       INTEGER NOT NULL,
    n_legs            INTEGER NOT NULL,
    total_dist_nm     REAL NOT NULL,
    created_at        TEXT NOT NULL
)
"""
# ---- Emissions/CII migration -- adds columns to the existing table ----

MIGRATION_ADD_CO2 = "ALTER TABLE voyage_predictions ADD COLUMN total_co2_t REAL"
MIGRATION_ADD_CII = "ALTER TABLE voyage_predictions ADD COLUMN attained_cii REAL"
MIGRATION_ADD_CII_REF = "ALTER TABLE voyage_predictions ADD COLUMN reference_cii REAL"
MIGRATION_ADD_CII_RATING = "ALTER TABLE voyage_predictions ADD COLUMN cii_rating TEXT"
MIGRATION_ADD_LEG_CO2 = "ALTER TABLE dashboard_leg_view ADD COLUMN co2_t REAL"

# -- new additions below --
MIGRATION_ADD_SUMMARY_CO2 = "ALTER TABLE dashboard_summary_view ADD COLUMN total_co2_t REAL"
MIGRATION_ADD_SUMMARY_CII = "ALTER TABLE dashboard_summary_view ADD COLUMN attained_cii REAL"
MIGRATION_ADD_SUMMARY_CII_REF = "ALTER TABLE dashboard_summary_view ADD COLUMN reference_cii REAL"
MIGRATION_ADD_SUMMARY_CII_RATING = "ALTER TABLE dashboard_summary_view ADD COLUMN cii_rating TEXT"

EMISSIONS_MIGRATIONS = [
    MIGRATION_ADD_CO2, MIGRATION_ADD_CII, MIGRATION_ADD_CII_REF,
    MIGRATION_ADD_CII_RATING, MIGRATION_ADD_LEG_CO2,
    MIGRATION_ADD_SUMMARY_CO2, MIGRATION_ADD_SUMMARY_CII,
    MIGRATION_ADD_SUMMARY_CII_REF, MIGRATION_ADD_SUMMARY_CII_RATING,
]

ALL_SCHEMAS = [
    VESSELS, ENGINE_SFOC, PROPELLER_CURVE,
    SENSOR_OBSERVATIONS, SENSOR_CALIBRATION_WINDOWS,
    WEATHER_ERA5,
    ROUTES, ROUTE_POINTS, ROUTE_LEGS,
    VOYAGE_PREDICTIONS, PREDICTION_LEGS,
    DASHBOARD_LEG_VIEW, DASHBOARD_SUMMARY_VIEW,
]