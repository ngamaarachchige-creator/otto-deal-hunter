CREATE TABLE IF NOT EXISTS cars (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    external_id TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    make TEXT,
    model TEXT,
    year INTEGER,
    price REAL,
    initial_price REAL,
    price_drop_amount REAL DEFAULT 0,
    price_display TEXT,
    is_negotiable INTEGER DEFAULT 0,
    location TEXT,
    district TEXT,
    mileage_km INTEGER,
    mileage_display TEXT,
    transmission TEXT,
    fuel_type TEXT,
    body_type TEXT,
    description TEXT,
    image_url TEXT,
    url TEXT NOT NULL,
    date_posted TEXT,
    status TEXT DEFAULT 'active',
    first_seen_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_seen_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_verified_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS pipeline (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    car_id INTEGER UNIQUE NOT NULL,
    stage TEXT DEFAULT 'saved',
    seller_phone TEXT DEFAULT '',
    seller_name TEXT DEFAULT '',
    offer_price REAL DEFAULT 0,
    purchase_price REAL DEFAULT 0,
    estimated_repair_cost REAL DEFAULT 0,
    target_resale_price REAL DEFAULT 0,
    actual_sold_price REAL DEFAULT 0,
    notes TEXT DEFAULT '',
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (car_id) REFERENCES cars(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS search_presets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    filters TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_cars_make_model ON cars(make, model);
CREATE INDEX IF NOT EXISTS idx_cars_price ON cars(price);
CREATE INDEX IF NOT EXISTS idx_cars_year ON cars(year);
CREATE INDEX IF NOT EXISTS idx_cars_district ON cars(district);
CREATE INDEX IF NOT EXISTS idx_cars_source ON cars(source);
CREATE INDEX IF NOT EXISTS idx_cars_mileage ON cars(mileage_km);
CREATE INDEX IF NOT EXISTS idx_cars_is_negotiable ON cars(is_negotiable);
CREATE INDEX IF NOT EXISTS idx_cars_updated_at ON cars(updated_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_cars_status ON cars(status);
CREATE INDEX IF NOT EXISTS idx_pipeline_stage ON pipeline(stage);
CREATE INDEX IF NOT EXISTS idx_pipeline_car_id ON pipeline(car_id);

-- Durable history of rate-limit (429/403) hits across every scraper entry
-- point and every environment (local Mac, GitHub Actions), so patterns over
-- time (time of day, frequency, how long blocks actually last) are visible
-- instead of only the current cooldown. See backend/scrapers/rate_limit_state.py
-- and scripts/rate_limit_report.py.
CREATE TABLE IF NOT EXISTS rate_limit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    host TEXT NOT NULL,
    hit_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    cooldown_seconds INTEGER,
    source_env TEXT,
    status_code INTEGER
);
CREATE INDEX IF NOT EXISTS idx_rate_limit_events_host_hit ON rate_limit_events(host, hit_at);

-- Running tally of D1 rows_written per UTC day, incremented by
-- record_write_budget() after every scrape run. D1's free tier caps
-- rows_written at 100,000/day (account-wide, resets 00:00 UTC) -- this table
-- lets scheduled_scrape.py check remaining headroom before doing more work
-- and stop early rather than risk crossing into billing. See
-- backend/database.py get_write_budget_today() / record_write_budget().
CREATE TABLE IF NOT EXISTS write_budget (
    utc_date TEXT PRIMARY KEY,
    rows_written INTEGER NOT NULL DEFAULT 0
);
