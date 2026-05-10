from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from simulator.tick_loop import get_simulator
from physics.state_machine import MachineState

router = APIRouter(prefix="/machines", tags=["Machines"])


# --- DATA MODELS ---

class ModeRequest(BaseModel):
    mode: str  # NORMAL, DEGRADE, RECOVER, MANUAL, DEMO
    speed_multiplier: float = 1.0  # 1x, 50x, 500x, 5000x
    # For DEMO mode only:
    target_bearing_age: Optional[float] = None
    target_tool_wear: Optional[float] = None
    target_coolant_health: Optional[float] = None

class StateRequest(BaseModel):
    state: str  # STOPPED, IDLE, WARM_UP, RUNNING, TOOL_CHANGE, MAINTENANCE, BREAKDOWN

class SpeedRequest(BaseModel):
    speed: float

class OverrideRequest(BaseModel):
    sensor: str  # power_kw, rpm, temperature, vibration
    value: float
    lock: bool = True

class FaultRequest(BaseModel):
    fault: str  # TOOL_BREAKAGE, BEARING_FAILURE, COOLANT_FAILURE, ELECTRICAL_FAULT


# --- ENDPOINTS ---

@router.get("")
async def get_all_machines():
    """Return current state payload of all 4 machines"""
    sim = get_simulator()
    return {mid: payload for mid, payload in sim.latest_telemetry.items() if payload}


@router.post("/reset-all")
async def reset_all_machines():
    """Reset all machines to factory defaults (0% wear, stopped)."""
    sim = get_simulator()
    for engine in sim.machines.values():
        engine.reset()
    return {"status": "success", "message": "All machines reset"}


@router.post("/speed")
async def set_global_speed(req: SpeedRequest):
    """Set global simulation time speed multiplier"""
    sim = get_simulator()
    sim.time_speed = req.speed
    return {"status": "success", "speed": req.speed}


@router.get("/{machine_id}")
async def get_machine(machine_id: str):
    """Return full state of single machine"""
    sim = get_simulator()
    if machine_id not in sim.machines:
        raise HTTPException(404, "Machine not found")
    return sim.latest_telemetry.get(machine_id)


@router.post("/{machine_id}/mode")
async def set_mode(machine_id: str, req: ModeRequest):
    """Set control mode and degradation speed"""
    sim = get_simulator()
    if machine_id not in sim.machines:
        raise HTTPException(404, "Machine not found")
        
    machine = sim.machines[machine_id]
    
    valid_modes = ['NORMAL', 'DEGRADE', 'RECOVER', 'MANUAL', 'DEMO']
    if req.mode not in valid_modes:
        raise HTTPException(400, f"Invalid mode. Must be one of {valid_modes}")
        
    machine.state.control_mode = req.mode
    machine.state.degrade_speed_multiplier = req.speed_multiplier
    
    if req.mode == 'DEMO':
        if req.target_bearing_age is not None:
            machine.state._demo_target_bearing = req.target_bearing_age
        if req.target_tool_wear is not None:
            machine.state._demo_target_tool = req.target_tool_wear
        if req.target_coolant_health is not None:
            machine.state._demo_target_coolant = req.target_coolant_health
            
    return {"status": "success", "mode": req.mode, "machine_id": machine_id}


@router.post("/{machine_id}/state")
async def set_state(machine_id: str, req: StateRequest):
    """Change machine operational state"""
    sim = get_simulator()
    if machine_id not in sim.machines:
        raise HTTPException(404, "Machine not found")
        
    try:
        new_state = MachineState(req.state)
    except ValueError:
        raise HTTPException(400, f"Invalid state '{req.state}'")
        
    machine = sim.machines[machine_id]
    machine.set_state(new_state)
    return {"status": "success", "state": req.state}


@router.post("/{machine_id}/override")
async def manual_override(machine_id: str, req: OverrideRequest):
    """Manually set sensor value (MANUAL mode only)"""
    sim = get_simulator()
    if machine_id not in sim.machines:
        raise HTTPException(404, "Machine not found")
        
    machine = sim.machines[machine_id]
    if machine.state.control_mode != 'MANUAL':
        raise HTTPException(400, "Manual override only allowed in MANUAL mode")
        
    # Translate frontend generic names to engine names if needed
    sensor_map = {
        'power_kw': 'power_kw',
        'rpm': 'rpm',
        'temperature': 'motor_temp',
        'vibration': 'vibration_rms'
    }
    internal_sensor = sensor_map.get(req.sensor, req.sensor)
        
    # Validate
    is_valid, clamped, reason, severity = machine.validator.validate(
        internal_sensor, req.value, machine.state_enum.value
    )
    
    if severity == 'CRITICAL':
        raise HTTPException(400, f"Rejected: {reason}")
        
    # Apply
    machine.state.manual_overrides[internal_sensor] = {
        'value': clamped,
        'locked': req.lock,
        'original_request': req.value,
        'clamp_reason': reason if not is_valid else None
    }
    
    return {
        "status": "applied" if is_valid else "clamped",
        "sensor": req.sensor,
        "internal_sensor": internal_sensor,
        "value": clamped,
        "reason": reason,
        "severity": severity
    }


@router.post("/{machine_id}/fault")
async def inject_fault(machine_id: str, req: FaultRequest):
    """Inject specific fault"""
    sim = get_simulator()
    if machine_id not in sim.machines:
        raise HTTPException(404, "Machine not found")
        
    machine = sim.machines[machine_id]
    machine.inject_fault(req.fault)
    return {"status": "fault_injected", "fault": req.fault}


@router.delete("/{machine_id}/fault")
async def clear_faults(machine_id: str):
    """Clear all active faults"""
    sim = get_simulator()
    if machine_id not in sim.machines:
        raise HTTPException(404, "Machine not found")
        
    machine = sim.machines[machine_id]
    machine.state.active_faults.clear()
    return {"status": "faults_cleared"}


@router.get("/{machine_id}/twin")
async def get_digital_twin(machine_id: str):
    """Return internal physics state (for debugging)"""
    sim = get_simulator()
    if machine_id not in sim.machines:
        raise HTTPException(404, "Machine not found")
        
    machine = sim.machines[machine_id]
    return {
        "machine_id": machine_id,
        "state_enum": machine.state_enum.value,
        "physics_state": {
            k: v for k, v in machine.state.__dict__.items()
            if not k.startswith('_')
        }
    }
