from fastapi import APIRouter, Query
from database import db

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/oee")
async def get_oee_summary(window_minutes: int = Query(60, ge=5, le=1440)):
    """
    Returns per-machine OEE components (A, P, Q, OEE %) computed from
    TimescaleDB telemetry over the last `window_minutes` minutes.
    Also returns a plant-level aggregate.
    """
    per_machine = await db.query_oee_summary(window_minutes)
    
    # Plant-level weighted average
    if per_machine:
        plant_oee = round(sum(v['oee'] for v in per_machine.values()) / len(per_machine), 1)
        plant_avail = round(sum(v['availability'] for v in per_machine.values()) / len(per_machine), 1)
        plant_perf = round(sum(v['performance'] for v in per_machine.values()) / len(per_machine), 1)
        plant_qual = round(sum(v['quality'] for v in per_machine.values()) / len(per_machine), 1)
        total_parts = sum(v['parts_produced'] for v in per_machine.values())
        total_defects = sum(v['defects'] for v in per_machine.values())
        total_power = round(sum(v['avg_power_kw'] for v in per_machine.values()), 2)
    else:
        plant_oee = plant_avail = plant_perf = plant_qual = 0
        total_parts = total_defects = total_power = 0

    return {
        "window_minutes": window_minutes,
        "plant": {
            "oee": plant_oee,
            "availability": plant_avail,
            "performance": plant_perf,
            "quality": plant_qual,
            "total_parts": total_parts,
            "total_defects": total_defects,
            "total_power_kw": total_power,
        },
        "machines": per_machine,
    }


@router.get("/trend/{machine_id}")
async def get_oee_trend(
    machine_id: str,
    hours: int = Query(24, ge=1, le=168),
    bucket_minutes: int = Query(30, ge=5, le=120),
):
    """
    Returns time-bucketed OEE trend for one machine over the last `hours` hours.
    """
    trend = await db.query_oee_trend(machine_id, hours, bucket_minutes)
    return {"machine_id": machine_id, "hours": hours, "bucket_minutes": bucket_minutes, "trend": trend}


@router.get("/trend")
async def get_oee_trend_all(
    hours: int = Query(24, ge=1, le=168),
    bucket_minutes: int = Query(30, ge=5, le=120),
):
    """
    Returns time-bucketed OEE trend for ALL machines (fetched concurrently).
    """
    import asyncio
    from simulator.tick_loop import get_simulator
    sim = get_simulator()
    machine_ids = list(sim.machines.keys())
    
    results = await asyncio.gather(*[
        db.query_oee_trend(mid, hours, bucket_minutes) for mid in machine_ids
    ])
    return {mid: trend for mid, trend in zip(machine_ids, results)}


@router.get("/power")
async def get_power_trend(
    hours: int = Query(8, ge=1, le=48),
    bucket_minutes: int = Query(15, ge=5, le=60),
):
    """
    Returns total plant power kW trend, bucketed by time.
    """
    trend = await db.query_power_trend(hours, bucket_minutes)
    return {"hours": hours, "bucket_minutes": bucket_minutes, "trend": trend}
