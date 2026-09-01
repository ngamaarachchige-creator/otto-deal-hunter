import os
import re
import json
from datetime import datetime
from typing import List, Dict, Any, Optional

# Load .env if present
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
if os.path.exists(env_path):
    with open(env_path, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip()

DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("SUPABASE_DB_URL") or os.environ.get("POSTGRES_URL")
IS_POSTGRES = bool(DATABASE_URL and DATABASE_URL.startswith("postgres"))

# D1 has no normal connection string — it's only reachable via the proxy Worker
# in cf-worker/. When configured, it takes priority: D1 uses the same SQLite
# dialect and :named-param style as the local-SQLite branch below, so every
# query in this file works unchanged against it through d1_connector.py's
# sqlite3-shaped shim.
from .d1_connector import is_d1_configured, get_d1_connection
IS_D1 = is_d1_configured()

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cars.db")

def get_db_connection():
    if IS_D1:
        return get_d1_connection()
    elif IS_POSTGRES:
        import psycopg2
        import psycopg2.extras
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    else:
        import sqlite3
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

def init_db():
    if IS_D1:
        # Schema is applied once via `wrangler d1 execute --file=schema.sql`
        # (see cf-worker/schema.sql) rather than on every app startup — the
        # SQLite migration-check path below relies on PRAGMA table_info, which
        # the D1 shim doesn't need to support since it's never exercised here.
        return

    conn = get_db_connection()
    cursor = conn.cursor()

    if IS_POSTGRES:
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS cars (
            id SERIAL PRIMARY KEY,
            source VARCHAR(50) NOT NULL,
            external_id VARCHAR(255) UNIQUE NOT NULL,
            title TEXT NOT NULL,
            make VARCHAR(100),
            model VARCHAR(100),
            year INT,
            price NUMERIC(15, 2),
            initial_price NUMERIC(15, 2),
            price_drop_amount NUMERIC(15, 2) DEFAULT 0,
            price_display VARCHAR(100),
            is_negotiable INT DEFAULT 0,
            location VARCHAR(150),
            district VARCHAR(100),
            mileage_km INT,
            mileage_display VARCHAR(100),
            transmission VARCHAR(50),
            fuel_type VARCHAR(50),
            body_type VARCHAR(50),
            description TEXT,
            image_url TEXT,
            url TEXT NOT NULL,
            date_posted VARCHAR(100),
            status VARCHAR(50) DEFAULT 'active',
            first_seen_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            last_seen_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            last_verified_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        );

        ALTER TABLE cars ADD COLUMN IF NOT EXISTS description TEXT;

        CREATE TABLE IF NOT EXISTS pipeline (
            id SERIAL PRIMARY KEY,
            car_id INT UNIQUE NOT NULL REFERENCES cars(id) ON DELETE CASCADE,
            stage VARCHAR(50) DEFAULT 'saved',
            seller_phone VARCHAR(50) DEFAULT '',
            seller_name VARCHAR(150) DEFAULT '',
            offer_price NUMERIC(15, 2) DEFAULT 0,
            purchase_price NUMERIC(15, 2) DEFAULT 0,
            estimated_repair_cost NUMERIC(15, 2) DEFAULT 0,
            target_resale_price NUMERIC(15, 2) DEFAULT 0,
            actual_sold_price NUMERIC(15, 2) DEFAULT 0,
            notes TEXT DEFAULT '',
            updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
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
        """)
        conn.commit()
        conn.close()
    else:
        cursor.execute("""
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
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # Check and add columns if upgrading existing SQLite schema
        cursor.execute("PRAGMA table_info(cars)")
        columns = [col[1] for col in cursor.fetchall()]
        if 'initial_price' not in columns:
            cursor.execute("ALTER TABLE cars ADD COLUMN initial_price REAL")
        if 'price_drop_amount' not in columns:
            cursor.execute("ALTER TABLE cars ADD COLUMN price_drop_amount REAL DEFAULT 0")
        if 'status' not in columns:
            cursor.execute("ALTER TABLE cars ADD COLUMN status TEXT DEFAULT 'active'")
        if 'first_seen_at' not in columns:
            cursor.execute("ALTER TABLE cars ADD COLUMN first_seen_at DATETIME")
        if 'last_seen_at' not in columns:
            cursor.execute("ALTER TABLE cars ADD COLUMN last_seen_at DATETIME")
        if 'last_verified_at' not in columns:
            cursor.execute("ALTER TABLE cars ADD COLUMN last_verified_at DATETIME")
        if 'description' not in columns:
            cursor.execute("ALTER TABLE cars ADD COLUMN description TEXT")

        cursor.execute("""
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
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS search_presets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            filters TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """)
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cars_make_model ON cars(make, model);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cars_price ON cars(price);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cars_year ON cars(year);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cars_district ON cars(district);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cars_source ON cars(source);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cars_mileage ON cars(mileage_km);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cars_is_negotiable ON cars(is_negotiable);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cars_updated_at ON cars(updated_at DESC, id DESC);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cars_status ON cars(status);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_pipeline_stage ON pipeline(stage);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_pipeline_car_id ON pipeline(car_id);")
        
        conn.commit()
        conn.close()

def mark_stale_listings(stale_after_days: int = 14) -> int:
    """Soft-hides ads not re-seen in a scrape for a while (likely sold/removed).

    Rows are never deleted: keeping stale rows lets us detect reposts (same
    seller relisting at a new price) and keeps market-average history intact.
    Only the 'active' flag flips, which is what dashboard/AI search filter on.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    if IS_POSTGRES:
        cursor.execute(
            "UPDATE cars SET status = 'stale' WHERE status = 'active' "
            "AND last_seen_at < NOW() - INTERVAL '%s days'" % int(stale_after_days)
        )
    else:
        cursor.execute(
            "UPDATE cars SET status = 'stale' WHERE status = 'active' "
            "AND last_seen_at < datetime('now', :cutoff)",
            {"cutoff": f"-{int(stale_after_days)} days"}
        )
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected

def upsert_cars_batch(cars_list: List[Dict[str, Any]]) -> int:
    if not cars_list:
        return 0

    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.utcnow().isoformat()

    if IS_POSTGRES:
        import psycopg2.extras
        sql = """
        INSERT INTO cars (
            source, external_id, title, make, model, year,
            price, initial_price, price_drop_amount, price_display, is_negotiable, location, district,
            mileage_km, mileage_display, transmission, fuel_type, body_type, description,
            image_url, url, date_posted, status, first_seen_at, last_seen_at, created_at, updated_at
        ) VALUES (
            %(source)s, %(external_id)s, %(title)s, %(make)s, %(model)s, %(year)s,
            %(price)s, %(price)s, 0, %(price_display)s, %(is_negotiable)s, %(location)s, %(district)s,
            %(mileage_km)s, %(mileage_display)s, %(transmission)s, %(fuel_type)s, %(body_type)s, %(description)s,
            %(image_url)s, %(url)s, %(date_posted)s, 'active', %(created_at)s, %(updated_at)s, %(created_at)s, %(updated_at)s
        )
        ON CONFLICT(external_id) DO UPDATE SET
            price_drop_amount = CASE
                WHEN cars.price > EXCLUDED.price AND EXCLUDED.price > 0 THEN (cars.price - EXCLUDED.price)
                ELSE cars.price_drop_amount
            END,
            price = EXCLUDED.price,
            price_display = EXCLUDED.price_display,
            is_negotiable = EXCLUDED.is_negotiable,
            location = EXCLUDED.location,
            district = EXCLUDED.district,
            mileage_km = EXCLUDED.mileage_km,
            mileage_display = EXCLUDED.mileage_display,
            transmission = CASE WHEN %(specs_verified)s THEN EXCLUDED.transmission ELSE cars.transmission END,
            fuel_type = CASE WHEN %(specs_verified)s THEN EXCLUDED.fuel_type ELSE cars.fuel_type END,
            body_type = CASE WHEN %(specs_verified)s THEN EXCLUDED.body_type ELSE cars.body_type END,
            description = CASE WHEN %(specs_verified)s THEN EXCLUDED.description ELSE cars.description END,
            image_url = EXCLUDED.image_url,
            date_posted = EXCLUDED.date_posted,
            status = 'active',
            last_seen_at = EXCLUDED.updated_at,
            updated_at = EXCLUDED.updated_at
        """
        params_list = []
        for car_data in cars_list:
            price_val = float(car_data.get('price', 0.0) or 0.0)
            is_neg = 1 if (car_data.get('is_negotiable') or price_val <= 0) else 0
            params_list.append({
                'source': car_data.get('source', ''),
                'external_id': car_data.get('external_id', ''),
                'title': car_data.get('title', ''),
                'make': car_data.get('make', ''),
                'model': car_data.get('model', ''),
                'year': car_data.get('year'),
                'price': price_val,
                'price_display': car_data.get('price_display', 'Price on request') if price_val > 0 else 'Price on request',
                'is_negotiable': is_neg,
                'location': car_data.get('location', ''),
                'district': car_data.get('district', ''),
                'mileage_km': car_data.get('mileage_km'),
                'mileage_display': car_data.get('mileage_display', ''),
                'transmission': car_data.get('transmission', ''),
                'fuel_type': car_data.get('fuel_type', ''),
                'body_type': car_data.get('body_type', ''),
                'description': car_data.get('description', ''),
                'specs_verified': bool(car_data.get('_specs_verified')),
                'image_url': car_data.get('image_url', ''),
                'url': car_data.get('url', ''),
                'date_posted': car_data.get('date_posted', ''),
                'created_at': now,
                'updated_at': now
            })
        psycopg2.extras.execute_batch(cursor, sql, params_list)
        count = len(params_list)
        conn.commit()
        conn.close()
        return count
    else:
        params_list = []
        for car_data in cars_list:
            price_val = float(car_data.get('price', 0.0) or 0.0)
            is_neg = 1 if (car_data.get('is_negotiable') or price_val <= 0) else 0

            params_list.append({
                'source': car_data.get('source', ''),
                'external_id': car_data.get('external_id', ''),
                'title': car_data.get('title', ''),
                'make': car_data.get('make', ''),
                'model': car_data.get('model', ''),
                'year': car_data.get('year'),
                'price': price_val,
                'price_display': car_data.get('price_display', 'Price on request') if price_val > 0 else 'Price on request',
                'is_negotiable': is_neg,
                'location': car_data.get('location', ''),
                'district': car_data.get('district', ''),
                'mileage_km': car_data.get('mileage_km'),
                'mileage_display': car_data.get('mileage_display', ''),
                'transmission': car_data.get('transmission', ''),
                'fuel_type': car_data.get('fuel_type', ''),
                'body_type': car_data.get('body_type', ''),
                'description': car_data.get('description', ''),
                'specs_verified': 1 if car_data.get('_specs_verified') else 0,
                'image_url': car_data.get('image_url', ''),
                'url': car_data.get('url', ''),
                'date_posted': car_data.get('date_posted', ''),
                'created_at': now,
                'updated_at': now
            })

        cursor.executemany("""
        INSERT INTO cars (
            source, external_id, title, make, model, year,
            price, initial_price, price_drop_amount, price_display, is_negotiable, location, district,
            mileage_km, mileage_display, transmission, fuel_type, body_type, description,
            image_url, url, date_posted, status, first_seen_at, last_seen_at, created_at, updated_at
        ) VALUES (
            :source, :external_id, :title, :make, :model, :year,
            :price, :price, 0, :price_display, :is_negotiable, :location, :district,
            :mileage_km, :mileage_display, :transmission, :fuel_type, :body_type, :description,
            :image_url, :url, :date_posted, 'active', :created_at, :updated_at, :created_at, :updated_at
        )
        ON CONFLICT(external_id) DO UPDATE SET
            price_drop_amount = CASE
                WHEN cars.price > excluded.price AND excluded.price > 0 THEN (cars.price - excluded.price)
                ELSE cars.price_drop_amount
            END,
            price = excluded.price,
            price_display = excluded.price_display,
            is_negotiable = excluded.is_negotiable,
            location = excluded.location,
            district = excluded.district,
            mileage_km = excluded.mileage_km,
            mileage_display = excluded.mileage_display,
            transmission = CASE WHEN :specs_verified THEN excluded.transmission ELSE cars.transmission END,
            fuel_type = CASE WHEN :specs_verified THEN excluded.fuel_type ELSE cars.fuel_type END,
            body_type = CASE WHEN :specs_verified THEN excluded.body_type ELSE cars.body_type END,
            description = CASE WHEN :specs_verified THEN excluded.description ELSE cars.description END,
            image_url = excluded.image_url,
            date_posted = excluded.date_posted,
            status = 'active',
            last_seen_at = excluded.updated_at,
            updated_at = excluded.updated_at
        """, params_list)

        count = len(params_list)
        conn.commit()
        conn.close()
        return count

def upsert_car(car_data: Dict[str, Any]) -> int:
    return upsert_cars_batch([car_data])

def get_cars(filters: Dict[str, Any] = None, sort_by: str = "date_desc", limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    if IS_POSTGRES:
        import psycopg2.extras
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    else:
        cursor = conn.cursor()

    query = """
    SELECT c.*, 
           p.stage as pipeline_stage, 
           p.seller_phone, 
           p.estimated_repair_cost, 
           p.target_resale_price, 
           p.notes as pipeline_notes
    FROM cars c
    LEFT JOIN pipeline p ON c.id = p.car_id
    WHERE 1=1
    """
    params = {}
    
    if filters:
        if filters.get("query"):
            query += f" AND (c.title ILIKE %(q)s OR c.make ILIKE %(q)s OR c.model ILIKE %(q)s OR c.location ILIKE %(q)s)" if IS_POSTGRES else " AND (c.title LIKE :q OR c.make LIKE :q OR c.model LIKE :q OR c.location LIKE :q)"
            params["q"] = f"%{filters['query']}%"
        if filters.get("source"):
            query += f" AND c.source = %(source)s" if IS_POSTGRES else " AND c.source = :source"
            params["source"] = filters["source"]
        if filters.get("make"):
            query += f" AND LOWER(c.make) = LOWER(%(make)s)" if IS_POSTGRES else " AND LOWER(c.make) = LOWER(:make)"
            params["make"] = filters["make"]
        if filters.get("model"):
            query += f" AND LOWER(c.model) LIKE LOWER(%(model)s)" if IS_POSTGRES else " AND LOWER(c.model) LIKE LOWER(:model)"
            params["model"] = f"%{filters['model']}%"
        if filters.get("district"):
            query += f" AND (LOWER(c.district) LIKE LOWER(%(district)s) OR LOWER(c.location) LIKE LOWER(%(district)s))" if IS_POSTGRES else " AND (LOWER(c.district) LIKE LOWER(:district) OR LOWER(c.location) LIKE LOWER(:district))"
            params["district"] = f"%{filters['district']}%"
        if filters.get("fuel_type"):
            query += f" AND LOWER(c.fuel_type) = LOWER(%(fuel_type)s)" if IS_POSTGRES else " AND LOWER(c.fuel_type) = LOWER(:fuel_type)"
            params["fuel_type"] = filters["fuel_type"]
        if filters.get("min_price"):
            query += f" AND (c.price >= %(min_price)s AND c.price > 0)" if IS_POSTGRES else " AND (c.price >= :min_price AND c.price > 0)"
            params["min_price"] = float(filters["min_price"])
        if filters.get("max_price"):
            query += f" AND (c.price <= %(max_price)s AND c.price > 0)" if IS_POSTGRES else " AND (c.price <= :max_price AND c.price > 0)"
            params["max_price"] = float(filters["max_price"])
        if filters.get("min_year"):
            query += f" AND c.year >= %(min_year)s" if IS_POSTGRES else " AND c.year >= :min_year"
            params["min_year"] = int(filters["min_year"])
        if filters.get("max_year"):
            query += f" AND c.year <= %(max_year)s" if IS_POSTGRES else " AND c.year <= :max_year"
            params["max_year"] = int(filters["max_year"])
        if filters.get("max_mileage"):
            query += f" AND (c.mileage_km <= %(max_mileage)s OR c.mileage_km IS NULL)" if IS_POSTGRES else " AND (c.mileage_km <= :max_mileage OR c.mileage_km IS NULL)"
            params["max_mileage"] = int(filters["max_mileage"])
        if filters.get("pipeline_stage"):
            if filters["pipeline_stage"] == "untracked":
                query += " AND p.stage IS NULL"
            else:
                query += f" AND p.stage = %(p_stage)s" if IS_POSTGRES else " AND p.stage = :p_stage"
                params["p_stage"] = filters["pipeline_stage"]
        if filters.get("deal_filter") == "negotiable":
            query += " AND (c.is_negotiable = 1 OR c.price <= 0 OR c.price IS NULL)"
        elif filters.get("deal_filter") in ["priced", "hot", "good"]:
            query += " AND (c.is_negotiable = 0 AND c.price > 0)"
        if filters.get("status"):
            if filters["status"] != "all":
                query += f" AND c.status = %(status)s" if IS_POSTGRES else " AND c.status = :status"
                params["status"] = filters["status"]
        else:
            query += " AND (c.status = 'active' OR c.status IS NULL)"
    else:
        query += " AND (c.status = 'active' OR c.status IS NULL)"

    # Sorting
    if sort_by == "price_asc":
        query += " ORDER BY CASE WHEN c.price > 0 THEN c.price ELSE 999999999 END ASC"
    elif sort_by == "price_desc":
        query += " ORDER BY c.price DESC"
    elif sort_by == "year_desc":
        query += " ORDER BY c.year DESC NULLS LAST"
    elif sort_by == "mileage_asc":
        query += " ORDER BY CASE WHEN c.mileage_km > 0 THEN c.mileage_km ELSE 9999999 END ASC"
    elif sort_by == "date_desc":
        query += " ORDER BY c.updated_at DESC, c.id DESC"
    else:
        query += " ORDER BY c.id DESC"

    if limit is not None:
        query += f" LIMIT %(limit)s OFFSET %(offset)s" if IS_POSTGRES else " LIMIT :limit OFFSET :offset"
        params["limit"] = limit
        params["offset"] = offset

    cursor.execute(query, params)
    rows = cursor.fetchall()
    results = [dict(row) for row in rows]
    conn.close()
    return results

def get_car_count(filters: Dict[str, Any] = None) -> int:
    conn = get_db_connection()
    cursor = conn.cursor()
    query = "SELECT COUNT(*) FROM cars c LEFT JOIN pipeline p ON c.id = p.car_id WHERE 1=1"
    params = {}
    
    if filters:
        if filters.get("query"):
            query += f" AND (c.title ILIKE %(q)s OR c.make ILIKE %(q)s OR c.model ILIKE %(q)s OR c.location ILIKE %(q)s)" if IS_POSTGRES else " AND (c.title LIKE :q OR c.make LIKE :q OR c.model LIKE :q OR c.location LIKE :q)"
            params["q"] = f"%{filters['query']}%"
        if filters.get("source"):
            query += f" AND c.source = %(source)s" if IS_POSTGRES else " AND c.source = :source"
            params["source"] = filters["source"]
        if filters.get("make"):
            query += f" AND LOWER(c.make) = LOWER(%(make)s)" if IS_POSTGRES else " AND LOWER(c.make) = LOWER(:make)"
            params["make"] = filters["make"]
        if filters.get("model"):
            query += f" AND LOWER(c.model) LIKE LOWER(%(model)s)" if IS_POSTGRES else " AND LOWER(c.model) LIKE LOWER(:model)"
            params["model"] = f"%{filters['model']}%"
        if filters.get("district"):
            query += f" AND (LOWER(c.district) LIKE LOWER(%(district)s) OR LOWER(c.location) LIKE LOWER(%(district)s))" if IS_POSTGRES else " AND (LOWER(c.district) LIKE LOWER(:district) OR LOWER(c.location) LIKE LOWER(:district))"
            params["district"] = f"%{filters['district']}%"
        if filters.get("fuel_type"):
            query += f" AND LOWER(c.fuel_type) = LOWER(%(fuel_type)s)" if IS_POSTGRES else " AND LOWER(c.fuel_type) = LOWER(:fuel_type)"
            params["fuel_type"] = filters["fuel_type"]
        if filters.get("min_price"):
            query += f" AND (c.price >= %(min_price)s AND c.price > 0)" if IS_POSTGRES else " AND (c.price >= :min_price AND c.price > 0)"
            params["min_price"] = float(filters["min_price"])
        if filters.get("max_price"):
            query += f" AND (c.price <= %(max_price)s AND c.price > 0)" if IS_POSTGRES else " AND (c.price <= :max_price AND c.price > 0)"
            params["max_price"] = float(filters["max_price"])
        if filters.get("min_year"):
            query += f" AND c.year >= %(min_year)s" if IS_POSTGRES else " AND c.year >= :min_year"
            params["min_year"] = int(filters["min_year"])
        if filters.get("max_year"):
            query += f" AND c.year <= %(max_year)s" if IS_POSTGRES else " AND c.year <= :max_year"
            params["max_year"] = int(filters["max_year"])
        if filters.get("max_mileage"):
            query += f" AND (c.mileage_km <= %(max_mileage)s OR c.mileage_km IS NULL)" if IS_POSTGRES else " AND (c.mileage_km <= :max_mileage OR c.mileage_km IS NULL)"
            params["max_mileage"] = int(filters["max_mileage"])
        if filters.get("pipeline_stage"):
            if filters["pipeline_stage"] == "untracked":
                query += " AND p.stage IS NULL"
            else:
                query += f" AND p.stage = %(p_stage)s" if IS_POSTGRES else " AND p.stage = :p_stage"
                params["p_stage"] = filters["pipeline_stage"]
        if filters.get("deal_filter") == "negotiable":
            query += " AND (c.is_negotiable = 1 OR c.price <= 0 OR c.price IS NULL)"
        elif filters.get("deal_filter") in ["priced", "hot", "good"]:
            query += " AND (c.is_negotiable = 0 AND c.price > 0)"
        if filters.get("status"):
            if filters["status"] != "all":
                query += f" AND c.status = %(status)s" if IS_POSTGRES else " AND c.status = :status"
                params["status"] = filters["status"]
        else:
            query += " AND (c.status = 'active' OR c.status IS NULL)"
    else:
        query += " AND (c.status = 'active' OR c.status IS NULL)"

    cursor.execute(query, params)
    row = cursor.fetchone()
    count = row[0] if row else 0
    conn.close()
    return count

def update_pipeline_item(car_id: int, stage: str, seller_phone: str = "", seller_name: str = "",
                         offer_price: float = 0, purchase_price: float = 0,
                         estimated_repair_cost: float = 0, target_resale_price: float = 0,
                         actual_sold_price: float = 0, notes: str = "") -> Dict[str, Any]:
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.utcnow().isoformat()
    
    if IS_POSTGRES:
        cursor.execute("""
        INSERT INTO pipeline (
            car_id, stage, seller_phone, seller_name, offer_price, purchase_price,
            estimated_repair_cost, target_resale_price, actual_sold_price, notes, updated_at
        ) VALUES (
            %(car_id)s, %(stage)s, %(seller_phone)s, %(seller_name)s, %(offer_price)s, %(purchase_price)s,
            %(estimated_repair_cost)s, %(target_resale_price)s, %(actual_sold_price)s, %(notes)s, %(updated_at)s
        )
        ON CONFLICT(car_id) DO UPDATE SET
            stage = EXCLUDED.stage,
            seller_phone = EXCLUDED.seller_phone,
            seller_name = EXCLUDED.seller_name,
            offer_price = EXCLUDED.offer_price,
            purchase_price = EXCLUDED.purchase_price,
            estimated_repair_cost = EXCLUDED.estimated_repair_cost,
            target_resale_price = EXCLUDED.target_resale_price,
            actual_sold_price = EXCLUDED.actual_sold_price,
            notes = EXCLUDED.notes,
            updated_at = EXCLUDED.updated_at
        """, {
            'car_id': car_id,
            'stage': stage,
            'seller_phone': seller_phone,
            'seller_name': seller_name,
            'offer_price': offer_price,
            'purchase_price': purchase_price,
            'estimated_repair_cost': estimated_repair_cost,
            'target_resale_price': target_resale_price,
            'actual_sold_price': actual_sold_price,
            'notes': notes,
            'updated_at': now
        })
    else:
        cursor.execute("""
        INSERT INTO pipeline (
            car_id, stage, seller_phone, seller_name, offer_price, purchase_price,
            estimated_repair_cost, target_resale_price, actual_sold_price, notes, updated_at
        ) VALUES (
            :car_id, :stage, :seller_phone, :seller_name, :offer_price, :purchase_price,
            :estimated_repair_cost, :target_resale_price, :actual_sold_price, :notes, :updated_at
        )
        ON CONFLICT(car_id) DO UPDATE SET
            stage = excluded.stage,
            seller_phone = excluded.seller_phone,
            seller_name = excluded.seller_name,
            offer_price = excluded.offer_price,
            purchase_price = excluded.purchase_price,
            estimated_repair_cost = excluded.estimated_repair_cost,
            target_resale_price = excluded.target_resale_price,
            actual_sold_price = excluded.actual_sold_price,
            notes = excluded.notes,
            updated_at = excluded.updated_at
        """, {
            'car_id': car_id,
            'stage': stage,
            'seller_phone': seller_phone,
            'seller_name': seller_name,
            'offer_price': offer_price,
            'purchase_price': purchase_price,
            'estimated_repair_cost': estimated_repair_cost,
            'target_resale_price': target_resale_price,
            'actual_sold_price': actual_sold_price,
            'notes': notes,
            'updated_at': now
        })

    conn.commit()
    conn.close()
    return {"status": "success", "car_id": car_id, "stage": stage}

def delete_pipeline_item(car_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    if IS_POSTGRES:
        cursor.execute("DELETE FROM pipeline WHERE car_id = %(car_id)s", {'car_id': car_id})
    else:
        cursor.execute("DELETE FROM pipeline WHERE car_id = ?", (car_id,))
    conn.commit()
    conn.close()
    return {"status": "deleted", "car_id": car_id}

def get_pipeline_stages_summary() -> Dict[str, Any]:
    conn = get_db_connection()
    if IS_POSTGRES:
        import psycopg2.extras
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    else:
        cursor = conn.cursor()

    cursor.execute("""
    SELECT stage, COUNT(*) as count, 
           SUM(purchase_price) as total_invested,
           SUM(estimated_repair_cost) as total_repairs,
           SUM(target_resale_price) as total_projected_sales,
           SUM(actual_sold_price) as total_actual_sales
    FROM pipeline
    GROUP BY stage
    """)
    rows = cursor.fetchall()
    conn.close()
    return {row['stage']: dict(row) for row in rows}

# Initialize on import
init_db()
