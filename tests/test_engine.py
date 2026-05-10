import pytest
from physics.engine import PhysicsEngine
from physics.state_machine import MachineState
from machines.config import MACHINE_CONFIGS

@pytest.fixture
def engine():
    config = MACHINE_CONFIGS['cnc-001']
    return PhysicsEngine('cnc-001', config)

def test_stopped_state_baseline(engine):
    engine.set_state(MachineState.STOPPED)
    payload = engine.compute_tick(0.1)
    
    # Power and RPM should be zero when stopped
    assert payload['sensors']['energy']['power_kw'] == 0.0
    assert payload['sensors']['rpm']['actual'] == 0.0
    
    # Tool wear shouldn't cause vibration when stopped
    engine.state.tool_wear_pct = 90
    payload = engine.compute_tick(0.1)
    assert payload['sensors']['vibration']['rms_mm_s'] < 2.0  # Idle baseline

def test_idle_state_power(engine):
    engine.set_state(MachineState.IDLE)
    payload = engine.compute_tick(0.1)
    
    # Power should be within idle range (1.8 - 2.5 kW for CNC)
    power_kw = payload['sensors']['energy']['power_kw']
    assert 1.8 <= power_kw <= 2.5
    assert payload['sensors']['rpm']['actual'] == 0.0

def test_bearing_degradation_increases_vibration(engine):
    engine.set_state(MachineState.RUNNING)
    
    # Base vibration with fresh bearings
    engine.state.bearing_age_pct = 0.0
    fresh_payload = engine.compute_tick(0.1)
    fresh_vib = fresh_payload['sensors']['vibration']['rms_mm_s']
    
    # Vibration with heavily worn bearings
    engine.state.bearing_age_pct = 85.0
    worn_payload = engine.compute_tick(0.1)
    worn_vib = worn_payload['sensors']['vibration']['rms_mm_s']
    
    assert worn_vib > fresh_vib
    # Should likely push it into Zone C
    assert worn_payload['sensors']['vibration']['iso_zone'] in ['C', 'D']

def test_thermal_lag(engine):
    engine.set_state(MachineState.RUNNING)
    # Start at ambient 25
    engine.state.motor_temp_internal = 25.0
    
    # Tick for 1 second (10 * 0.1s ticks)
    for _ in range(10):
        engine.compute_tick(0.1)
        
    temp_after_1s = engine.state.motor_temp_internal
    
    # Tick for 100 seconds (1000 * 0.1s ticks)
    for _ in range(1000):
        engine.compute_tick(0.1)
        
    temp_after_100s = engine.state.motor_temp_internal
    
    # Temperature should rise smoothly over time, not jump instantly
    assert 25.0 < temp_after_1s < 30.0  # Slight rise
    assert temp_after_1s < temp_after_100s  # Continued rise
    assert temp_after_100s < 100.0  # Should not instantly max out

def test_tool_wear_chatter_bursts(engine):
    engine.set_state(MachineState.RUNNING)
    engine.state.tool_wear_pct = 95.0
    
    # With 95% tool wear, there's a high probability of chatter bursts
    # Run multiple ticks and collect vibration
    vibrations = []
    for _ in range(50):
        payload = engine.compute_tick(0.1)
        vibrations.append(payload['sensors']['vibration']['rms_mm_s'])
        
    # Chatter bursts should create significant variation between min and max
    max_vib = max(vibrations)
    min_vib = min(vibrations)
    
    assert max_vib > min_vib + 1.0  # At least 1.0 mm/s difference due to bursts
