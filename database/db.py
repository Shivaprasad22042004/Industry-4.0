import asyncpg
import asyncio
from datetime import datetime
import json
import logging

logger = logging.getLogger(__name__)

# DB connection config
DB_URL = "postgres://postgres:password@localhost:5432/oee_db"

_pool = None

async def init_db():
    """Initialize connection pool and TimescaleDB tables."""
    global _pool
    try:
        _pool = await asyncpg.create_pool(DB_URL, min_size=1, max_size=10)
        async with _pool.acquire() as conn:
            # Enable TimescaleDB extension
            await conn.execute('CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;')

            # Create the hypertable for OEE events and sensor readings
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS telemetry (
                    time TIMESTAMPTZ NOT NULL,
                    machine_id TEXT NOT NULL,
                    state TEXT NOT NULL,
                    control_mode TEXT NOT NULL,
                    power_kw DOUBLE PRECISION,
                    current_a DOUBLE PRECISION,
                    spindle_rpm DOUBLE PRECISION,
                    vibration_mm_s DOUBLE PRECISION,
                    motor_temp_c DOUBLE PRECISION,
                    coolant_temp_c DOUBLE PRECISION,
                    part_count_shift INTEGER,
                    defect_count_shift INTEGER,
                    power_factor DOUBLE PRECISION,
                    power_status TEXT,
                    vibration_status TEXT,
                    temp_status TEXT
                );
            """)

            # Convert it to a hypertable if it isn't already
            await conn.execute("""
                SELECT create_hypertable('telemetry', 'time', if_not_exists => TRUE);
            """)
            print("✅ Database and TimescaleDB hypertables initialized successfully.")
    except Exception as e:
        print(f"❌ Failed to initialize database: {e}")

async def get_pool():
    if not _pool:
        await init_db()
    return _pool

async def insert_telemetry_batch(batch_data):
    """Bulk insert telemetry data."""
    if not batch_data:
        return
    
    pool = await get_pool()
    if not pool:
        return

    records = []
    for machine_id, payload in batch_data.items():
        if not payload:
            continue
        sensors = payload.get('sensors', {})
        prod = payload.get('production', {})
        records.append((
            datetime.fromisoformat(payload['timestamp']),
            machine_id,
            payload['state'],
            payload['control_mode'],
            # FIXED: correct key paths matching engine.py output
            sensors.get('energy', {}).get('power_kw', 0.0),
            sensors.get('energy', {}).get('current_a', 0.0),
            sensors.get('energy', {}).get('power_factor', 0.0),
            sensors.get('rpm', {}).get('actual', 0.0),          # was spindle_rpm.value
            sensors.get('vibration', {}).get('rms_mm_s', 0.0),  # was vibration.value
            sensors.get('temperature', {}).get('motor', 0.0),   # was temperature.motor_c
            sensors.get('temperature', {}).get('coolant', 0.0), # was temperature.coolant_c
            prod.get('part_count_shift', 0),
            prod.get('defect_count_shift', 0),
            sensors.get('energy', {}).get('status_code', 'NORMAL'),
            sensors.get('vibration', {}).get('status_code', 'NORMAL'),
            sensors.get('temperature', {}).get('status_code', 'NORMAL'),
        ))
        
    query = """
        INSERT INTO telemetry (
            time, machine_id, state, control_mode, power_kw, current_a, power_factor,
            spindle_rpm, vibration_mm_s, motor_temp_c, coolant_temp_c,
            part_count_shift, defect_count_shift, power_status, vibration_status, temp_status
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
    """
    
    try:
        async with pool.acquire() as conn:
            await conn.executemany(query, records)
    except Exception as e:
        print(f"❌ Failed to insert telemetry batch: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# ANALYTICS QUERIES
# ─────────────────────────────────────────────────────────────────────────────

async def query_oee_summary(window_minutes: int = 60):
    """
    Compute per-machine OEE components over the last N minutes from TimescaleDB.
    
    Availability = time_running / time_total
    Performance  = avg_spindle_rpm / rated_rpm (proxy — ideal cycle time is in physics engine)
    Quality      = (parts_good) / (parts_total)   where parts_good = total - defects
    OEE          = A × P × Q
    """
    pool = await get_pool()
    if not pool:
        return {}

    query = """
        SELECT
            machine_id,
            COUNT(*) FILTER (WHERE state = 'RUNNING') * 0.1 AS running_seconds,
            COUNT(*) * 0.1 AS total_seconds,
            MAX(part_count_shift)  - MIN(part_count_shift)  AS parts_produced,
            MAX(defect_count_shift) - MIN(defect_count_shift) AS defects,
            AVG(spindle_rpm) FILTER (WHERE state = 'RUNNING') AS avg_rpm,
            AVG(power_kw) AS avg_power_kw
        FROM telemetry
        WHERE time > NOW() - INTERVAL '1 minute' * $1
        GROUP BY machine_id
        ORDER BY machine_id;
    """
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(query, window_minutes)
            result = {}
            for row in rows:
                # Rated RPM proxy: we assume 3000 is max rated
                # In a real system this would come from machine config
                rated_rpm = 3000.0
                availability = (row['running_seconds'] / row['total_seconds']) if row['total_seconds'] > 0 else 0
                
                avg_rpm = row['avg_rpm'] or 0
                performance = min(1.0, avg_rpm / rated_rpm) if avg_rpm > 0 else 0

                parts = row['parts_produced'] or 0
                defects = row['defects'] or 0
                quality = ((parts - defects) / parts) if parts > 0 else 1.0
                quality = max(0.0, min(1.0, quality))

                oee = availability * performance * quality

                result[row['machine_id']] = {
                    'availability': round(availability * 100, 1),
                    'performance': round(performance * 100, 1),
                    'quality': round(quality * 100, 1),
                    'oee': round(oee * 100, 1),
                    'parts_produced': int(parts),
                    'defects': int(defects),
                    'avg_power_kw': round(row['avg_power_kw'] or 0, 2),
                }
            return result
    except Exception as e:
        print(f"❌ OEE query failed: {e}")
        return {}


async def query_oee_trend(machine_id: str, hours: int = 24, bucket_minutes: int = 30):
    """
    Return time-bucketed OEE % trend for a single machine over the last N hours.
    Uses TimescaleDB time_bucket for efficient aggregation.
    """
    pool = await get_pool()
    if not pool:
        return []

    query = """
        SELECT
            time_bucket($1::INTERVAL, time) AS bucket,
            COUNT(*) FILTER (WHERE state = 'RUNNING') * 0.1 AS running_sec,
            COUNT(*) * 0.1 AS total_sec,
            AVG(spindle_rpm) FILTER (WHERE state = 'RUNNING') AS avg_rpm,
            MAX(part_count_shift) - MIN(part_count_shift) AS parts,
            MAX(defect_count_shift) - MIN(defect_count_shift) AS defects,
            AVG(power_kw) AS avg_power_kw
        FROM telemetry
        WHERE machine_id = $2
          AND time > NOW() - INTERVAL '1 hour' * $3
        GROUP BY bucket
        ORDER BY bucket;
    """
    bucket_interval = f"{bucket_minutes} minutes"
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(query, bucket_interval, machine_id, hours)
            trend = []
            for row in rows:
                rated_rpm = 3000.0
                avail = (row['running_sec'] / row['total_sec']) if row['total_sec'] > 0 else 0
                avg_rpm = row['avg_rpm'] or 0
                perf = min(1.0, avg_rpm / rated_rpm)
                parts = row['parts'] or 0
                defects = row['defects'] or 0
                qual = ((parts - defects) / parts) if parts > 0 else 1.0
                qual = max(0.0, min(1.0, qual))
                oee = avail * perf * qual
                trend.append({
                    'bucket': row['bucket'].isoformat(),
                    'oee': round(oee * 100, 1),
                    'availability': round(avail * 100, 1),
                    'performance': round(perf * 100, 1),
                    'quality': round(qual * 100, 1),
                    'avg_power_kw': round(row['avg_power_kw'] or 0, 2),
                    'parts': int(parts),
                })
            return trend
    except Exception as e:
        print(f"❌ OEE trend query failed: {e}")
        return []


async def query_power_trend(hours: int = 8, bucket_minutes: int = 15):
    """
    Return total plant power bucketed over the last N hours.
    """
    pool = await get_pool()
    if not pool:
        return []

    query = """
        SELECT
            time_bucket($1::INTERVAL, time) AS bucket,
            machine_id,
            AVG(power_kw) AS avg_power_kw
        FROM telemetry
        WHERE time > NOW() - INTERVAL '1 hour' * $2
        GROUP BY bucket, machine_id
        ORDER BY bucket;
    """
    bucket_interval = f"{bucket_minutes} minutes"
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(query, bucket_interval, hours)
            # Aggregate into { bucket: str, total_kw: float, by_machine: dict }
            from collections import defaultdict
            buckets = defaultdict(lambda: {'total_kw': 0.0, 'by_machine': {}})
            for row in rows:
                b = row['bucket'].isoformat()
                buckets[b]['total_kw'] += row['avg_power_kw'] or 0
                buckets[b]['by_machine'][row['machine_id']] = round(row['avg_power_kw'] or 0, 2)
            return [
                {'bucket': b, 'total_kw': round(v['total_kw'], 2), 'by_machine': v['by_machine']}
                for b, v in sorted(buckets.items())
            ]
    except Exception as e:
        print(f"❌ Power trend query failed: {e}")
        return []


async def close_db():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
