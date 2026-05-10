import pytest
from physics.validator import SensorValidator
from machines.config import MACHINE_CONFIGS

@pytest.fixture
def validator():
    config = MACHINE_CONFIGS['cnc-001']
    return SensorValidator(config)

def test_power_clamping(validator):
    # STOPPED state should clamp power > 0.1 to 0.0
    is_valid, clamped, _, severity = validator.validate('power_kw', 5.0, 'STOPPED')
    assert not is_valid
    assert clamped == 0.0
    assert severity == 'ERROR'

    # RUNNING state over max + 30% overload (22kW * 1.3 = 28.6kW)
    # Validator checks power_kw using: config['power_max_w'] / 1000 * 1.3
    # 22 * 1.3 = 28.6
    is_valid, clamped, _, severity = validator.validate('power_kw', 30.0, 'RUNNING')
    assert not is_valid
    assert clamped == 28.6
    assert severity == 'ERROR'

    # Valid RUNNING state
    is_valid, clamped, _, severity = validator.validate('power_kw', 15.0, 'RUNNING')
    assert is_valid
    assert clamped == 15.0
    assert severity == 'OK'

def test_rpm_clamping(validator):
    # IDLE state should clamp RPM to 0
    is_valid, clamped, _, _ = validator.validate('rpm', 1000.0, 'IDLE')
    assert not is_valid
    assert clamped == 0.0

    # WARM_UP state limited to 1500
    is_valid, clamped, _, _ = validator.validate('rpm', 2000.0, 'WARM_UP')
    assert not is_valid
    assert clamped == 1500.0

    # Over max RPM
    is_valid, clamped, _, _ = validator.validate('rpm', 15000.0, 'RUNNING')
    assert not is_valid
    assert clamped == 12000.0  # cnc-001 max rpm

def test_vibration_iso_zones(validator):
    assert validator.tag_iso_zone(1.0) == 'A'
    assert validator.tag_iso_zone(3.0) == 'B'
    assert validator.tag_iso_zone(6.0) == 'C'
    assert validator.tag_iso_zone(8.0) == 'D'

def test_alarm_determination(validator):
    sensors = {
        'power_kw': 10.0,
        'rpm': 2000,
        'motor_temp': 95, # config alarm is 90, emergency 105
        'vibration_rms': 1.0
    }
    alarms = validator.determine_alarms(sensors)
    assert 'TEMP_ALARM' in alarms
    assert 'POWER_EMERGENCY' not in alarms

    # Multiple alarms
    sensors['vibration_rms'] = 8.0 # Zone D
    alarms = validator.determine_alarms(sensors)
    assert 'TEMP_ALARM' in alarms
    assert 'VIB_ZONE_D' in alarms
