"""
Sensor Validator
================

Enforces physical limits on all sensor readings.
Every value from the physics engine passes through this validator
before being emitted. Invalid values are clamped with a reason log.

Rules:
    - STOPPED: power=0, rpm=0
    - IDLE: power within tight idle range (±0.1 kW noise), rpm=0
    - WARM_UP: rpm ≤ 1500, no cutting, power 2-5 kW
    - RUNNING: full physics, all sensors active
    - Values are hard-clamped to machine config limits
    - ISO 10816 vibration zone tagging (corrected: >15 kW machinery)
"""

import math
from typing import Tuple


class SensorValidator:
    """
    Validates and clamps sensor readings against machine physical limits.
    Returns (is_valid, clamped_value, reason, severity) tuples.
    """

    def __init__(self, config: dict):
        self.config = config
        self._log = []  # Recent validation events (last 50)

    @property
    def recent_events(self) -> list:
        """Return last 50 validation events."""
        return list(self._log)

    def _log_event(self, sensor: str, original: float, clamped: float,
                   reason: str, severity: str):
        """Log a validation event (capped at 50 entries)."""
        if severity != 'OK':
            self._log.append({
                'sensor': sensor,
                'original': round(original, 3),
                'clamped': round(clamped, 3),
                'reason': reason,
                'severity': severity,
            })
            if len(self._log) > 50:
                self._log.pop(0)

    def validate(self, sensor: str, value: float,
                 machine_state: str) -> Tuple[bool, float, str, str]:
        """
        Validate a sensor value against machine limits and current state.

        Args:
            sensor: Sensor name ('power_kw', 'rpm', 'motor_temp',
                    'bearing_temp', 'coolant_temp', 'vibration_rms',
                    'current_a', 'power_factor')
            value: Raw sensor value from physics engine
            machine_state: Current machine state string

        Returns:
            (is_valid, clamped_value, reason, severity)
            severity: 'OK', 'WARNING', 'ALARM', 'CRITICAL'
        """
        dispatch = {
            'power_kw': self._validate_power,
            'rpm': self._validate_rpm,
            'motor_temp': self._validate_temperature,
            'bearing_temp': self._validate_temperature,
            'coolant_temp': self._validate_coolant_temp,
            'vibration_rms': self._validate_vibration,
            'current_a': self._validate_current,
            'power_factor': self._validate_power_factor,
        }

        validator_fn = dispatch.get(sensor)
        if validator_fn is None:
            return True, value, f"No validator for '{sensor}'", 'OK'

        is_valid, clamped, reason, severity = validator_fn(value, machine_state)
        self._log_event(sensor, value, clamped, reason, severity)
        return is_valid, clamped, reason, severity

    def validate_all(self, sensors: dict, machine_state: str) -> dict:
        """
        Validate and clamp all sensors in a dict.
        Returns a new dict with clamped values.
        """
        clamped = {}
        for sensor_name, value in sensors.items():
            if isinstance(value, (int, float)):
                _, clamped_val, _, _ = self.validate(sensor_name, value, machine_state)
                clamped[sensor_name] = clamped_val
            else:
                clamped[sensor_name] = value
        return clamped

    # ── Individual sensor validators ──────────────────────────────────

    def _validate_power(self, value: float, state: str) -> Tuple[bool, float, str, str]:
        """Validate power consumption (kW)."""
        config = self.config

        # ── STOPPED ───────────────────────────────────────────────
        if state == 'STOPPED':
            if value > 0.05:  # Tighter: only leakage current
                return (False, 0.0,
                        "Power must be ~0 when STOPPED (leakage only)",
                        'ERROR')
            return True, max(0, value), "Valid", 'OK'

        # ── IDLE ──────────────────────────────────────────────────
        if state == 'IDLE':
            min_p, max_p = config['idle_power_kw']
            # Tight noise band: ±0.1 kW (realistic for constant control loads)
            noise_margin = 0.1
            
            if value < min_p - noise_margin:
                return (False, min_p,
                        f"Idle power below minimum {min_p} kW "
                        f"(controls + pumps are constant load)",
                        'WARNING')
            if value > max_p + noise_margin:
                return (False, max_p,
                        f"Idle power above maximum {max_p} kW "
                        f"(cannot exceed baseline draw)",
                        'WARNING')
            return True, value, "Valid", 'OK'

        # ── WARM_UP ─────────────────────────────────────────────
        if state == 'WARM_UP':
            # Spindle at partial RPM, no cutting
            rated_kw = config['power_rated_w'] / 1000.0
            min_warmup = max(0.5, rated_kw * 0.10)
            max_warmup = max(min_warmup + 0.5, rated_kw * 0.35)
            if value > max_warmup:
                return (False, max_warmup,
                        f"Warm-up power exceeds {max_warmup:.2f} kW "
                        f"(no cutting load yet, scaled to rated power)",
                        'WARNING')
            if value < min_warmup:
                return (False, min_warmup,
                        f"Warm-up power below {min_warmup:.2f} kW "
                        f"(spindle friction minimum, scaled to rated power)",
                        'WARNING')
            return True, value, "Valid", 'OK'

        # ── RUNNING / TOOL_CHANGE / MAINTENANCE ──────────────────
        # Hard clamp: absolute physical maximum (motor max + 30% overload)
        max_allowed_kw = config['power_hard_clamp_w'] / 1000.0
        
        if value > max_allowed_kw:
            return (False, max_allowed_kw,
                    f"Power HARD CLAMPED to {max_allowed_kw:.1f} kW "
                    f"(absolute motor limit + overload margin)",
                    'ERROR')

        if value < 0:
            return False, 0.0, "Power cannot be negative", 'CRITICAL'

        # Minimum running power: friction losses at current RPM
        # P_min = base friction + windage + magnetizing losses
        # Approx: 10% of rated power at minimum
        min_running_kw = (config['power_rated_w'] / 1000.0) * 0.10
        if value < min_running_kw and state == 'RUNNING':
            return (False, min_running_kw,
                    f"Running power below minimum {min_running_kw:.1f} kW "
                    f"(friction + windage losses)",
                    'WARNING')

        # ── Threshold checks: MUST check emergency FIRST ─────────
        thresholds = config['thresholds']['energy']
        
        if value > thresholds['emergency']:
            return (True, value,
                    f"EMERGENCY: {value:.1f} kW > {thresholds['emergency']} kW "
                    f"(exceeds continuous rating, thermal damage imminent)",
                    'CRITICAL')
        
        if value > thresholds['alarm']:
            return (True, value,
                    f"ALARM: {value:.1f} kW > {thresholds['alarm']} kW "
                    f"(overload condition, reduce load or stop)",
                    'ALARM')
        
        if value > thresholds['warning']:
            return (True, value,
                    f"WARNING: {value:.1f} kW > {thresholds['warning']} kW "
                    f"(approaching rated limit)",
                    'WARNING')

        return True, value, "Valid", 'OK'

    def _validate_rpm(self, value: float, state: str) -> Tuple[bool, float, str, str]:
        """Validate spindle RPM."""
        config = self.config

        # ── STOPPED / IDLE ────────────────────────────────────────
        if state in ('STOPPED', 'IDLE'):
            if abs(value) > 1:  # Allow tiny float noise
                return (False, 0.0,
                        "RPM must be 0 when stopped/idle (spindle brake engaged)",
                        'CRITICAL')
            return True, 0.0, "Valid", 'OK'

        # ── WARM_UP ───────────────────────────────────────────────
        if state == 'WARM_UP':
            if value > 1500:
                return (False, 1500.0,
                        "Warm-up RPM limited to 1500 (thermal safety)",
                        'WARNING')
            if value < 100:
                return (False, 100.0,
                        "Warm-up RPM below 100 (bearing lubrication minimum)",
                        'WARNING')

        # ── All states with rotation ────────────────────────────
        if value < 0:
            return False, 0.0, "RPM cannot be negative", 'CRITICAL'

        if value > config['rpm_max']:
            return (False, float(config['rpm_max']),
                    f"RPM HARD CLAMPED to {config['rpm_max']} "
                    f"(spindle mechanical limit)",
                    'CRITICAL')

        # Threshold checks: emergency BEFORE alarm BEFORE warning
        thresholds = config['thresholds']['rpm']
        
        if value > thresholds['emergency']:
            return (True, value,
                    f"EMERGENCY: {value:.0f} RPM > {thresholds['emergency']} RPM "
                    f"(mechanical overspeed, catastrophic failure risk)",
                    'CRITICAL')
        
        if value > thresholds['alarm']:
            return (True, value,
                    f"ALARM: {value:.0f} RPM > {thresholds['alarm']} RPM "
                    f"(approaching max rated speed)",
                    'ALARM')
        
        if value > thresholds['warning']:
            return (True, value,
                    f"WARNING: {value:.0f} RPM > {thresholds['warning']} RPM",
                    'WARNING')

        return True, value, "Valid", 'OK'

    def _validate_temperature(self, value: float, state: str) -> Tuple[bool, float, str, str]:
        """Validate motor/bearing temperature (°C)."""
        config = self.config

        # Absolute physical limits
        if value < 10:
            return (False, 10.0,
                    "Below realistic minimum 10°C (ambient + sensor error)",
                    'WARNING')

        # Class F insulation absolute maximum
        insulation_limit = 155.0
        if value > insulation_limit:
            return (False, insulation_limit,
                    f"HARD CLAMPED to {insulation_limit}°C "
                    f"(Class F insulation destruction point)",
                    'CRITICAL')

        # Thermal runaway threshold (emergency shutdown)
        thermal_runaway = 120.0
        if value > thermal_runaway:
            return (True, value,
                    f"CRITICAL: {value:.1f}°C > {thermal_runaway}°C "
                    f"(thermal runaway, emergency stop triggered)",
                    'CRITICAL')

        # Threshold checks: emergency (105) BEFORE alarm (90) BEFORE warning (80)
        thresholds = config['thresholds']['temperature']
        
        if value > thresholds['emergency']:
            return (True, value,
                    f"EMERGENCY: {value:.1f}°C > {thresholds['emergency']}°C "
                    f"(insulation degradation accelerating)",
                    'CRITICAL')
        
        if value > thresholds['alarm']:
            return (True, value,
                    f"ALARM: {value:.1f}°C > {thresholds['alarm']}°C "
                    f"(reduce load, check coolant)",
                    'ALARM')
        
        if value > thresholds['warning']:
            return (True, value,
                    f"WARNING: {value:.1f}°C > {thresholds['warning']}°C "
                    f"(monitor closely)",
                    'WARNING')

        return True, value, "Valid", 'OK'

    def _validate_coolant_temp(self, value: float, state: str) -> Tuple[bool, float, str, str]:
        """Validate coolant temperature (°C) — state-aware limits."""
        
        # Absolute limits (all states)
        if value < 10:
            return (False, 10.0,
                    "Coolant below 10°C (freezing risk, flow restriction)",
                    'WARNING')
        if value > 65:
            return (False, 65.0,
                    "Coolant HARD CLAMPED to 65°C (boiling/evaporation risk)",
                    'CRITICAL')

        # State-aware expected ranges
        ambient = self.config.get('coolant_inlet_temp', 22)
        
        if state in ('STOPPED', 'IDLE'):
            # Coolant should be near ambient when not circulating
            if value > ambient + 5:
                return (True, value,
                        f"Coolant {value:.1f}°C elevated for idle "
                        f"(expected near {ambient}°C)",
                        'WARNING')
        
        elif state == 'RUNNING':
            # Normal running: ambient + 10-20°C rise
            expected_max = ambient + 25
            if value > expected_max:
                return (True, value,
                        f"Coolant {value:.1f}°C > expected max {expected_max}°C "
                        f"(check flow rate, coolant health)",
                        'WARNING')
            if value > 45:
                return (True, value,
                        f"Coolant {value:.1f}°C elevated (heat exchanger efficiency down)",
                        'WARNING')

        return True, value, "Valid", 'OK'

    def _validate_vibration(self, value: float, state: str) -> Tuple[bool, float, str, str]:
        """Validate vibration RMS (mm/s) with CORRECTED ISO 10816 zones."""
        
        if value < 0:
            return False, 0.0, "Vibration cannot be negative", 'CRITICAL'

        # Absolute physical limit for this machine class
        if value > 20:
            return (False, 20.0,
                    "Vibration HARD CLAMPED to 20 mm/s "
                    f"(structural damage to machine frame)",
                    'CRITICAL')

        # ISO 10816-3 for machinery >15 kW (CNC, Lathe, Mill)
        # Zone A: ≤ 2.3 mm/s (Good)
        # Zone B: 2.3 – 4.5 mm/s (Acceptable)
        # Zone C: 4.5 – 7.1 mm/s (Unsatisfactory)
        # Zone D: > 7.1 mm/s (Dangerous)
        zones = self.config['thresholds']['vibration']
        zone_a = zones['zone_a']   # 2.3
        zone_b = zones['zone_b']   # 4.5
        zone_c = zones['zone_c']   # 7.1

        # CRITICAL: Check Zone D FIRST (>7.1), then Zone C, then Zone B
        if value > zone_c:  # > 7.1 = Zone D
            return (True, value,
                    f"Zone D — DANGEROUS: {value:.2f} mm/s > {zone_c} mm/s "
                    f"(immediate shutdown required, structural risk)",
                    'CRITICAL')
        
        if value > zone_b:  # > 4.5 = Zone C
            return (True, value,
                    f"Zone C — UNSATISFACTORY: {value:.2f} mm/s > {zone_b} mm/s "
                    f"(schedule maintenance within 24 hours)",
                    'ALARM')
        
        if value > zone_a:  # > 2.3 = Zone B
            return (True, value,
                    f"Zone B — ACCEPTABLE: {value:.2f} mm/s > {zone_a} mm/s "
                    f"(continue monitoring, trend analysis recommended)",
                    'OK')

        return (True, value,
                f"Zone A — GOOD: {value:.2f} mm/s ≤ {zone_a} mm/s",
                'OK')

    def _validate_current(self, value: float, state: str) -> Tuple[bool, float, str, str]:
        """Validate motor current (Amps) — realistic limits."""
        
        if value < 0:
            return False, 0.0, "Current cannot be negative", 'CRITICAL'

        config = self.config
        
        # Realistic max current: use rated power / (voltage × realistic full-load PF)
        # NOT worst-case PF of 0.25 (that gives absurd 286A for CNC)
        realistic_pf = 0.88  # Full-load power factor
        max_current = (config['power_hard_clamp_w']) / (config['voltage_v'] * realistic_pf)
        
        if value > max_current:
            return (False, max_current,
                    f"Current HARD CLAMPED to {max_current:.1f} A "
                    f"(breaker trip limit, cable rating)",
                    'CRITICAL')

        # Minimum current: magnetizing current at no load
        min_current = (config['power_rated_w'] * 0.05) / (config['voltage_v'] * 0.3)
        if value < min_current and state == 'RUNNING':
            return (False, min_current,
                    f"Current below {min_current:.1f} A "
                    f"(magnetizing current minimum, open circuit suspected)",
                    'WARNING')

        return True, value, "Valid", 'OK'

    def _validate_power_factor(self, value: float, state: str) -> Tuple[bool, float, str, str]:
        """Validate power factor (dimensionless, 0-1)."""
        
        if value < 0.2:
            return (False, 0.2,
                    f"PF {value:.3f} below 0.2 (open phase or severe imbalance)",
                    'CRITICAL')
        
        if value > 0.98:
            return (False, 0.98,
                    f"PF {value:.3f} above 0.98 (synchronous motor? not induction)",
                    'WARNING')
        
        # State-aware expected ranges
        if state == 'IDLE' and value > 0.5:
            return (True, value,
                    f"PF {value:.3f} high for idle (expected 0.3-0.4)",
                    'WARNING')
        
        if state == 'RUNNING' and value < 0.75:
            return (True, value,
                    f"PF {value:.3f} low for running load (expected 0.85-0.92)",
                    'WARNING')

        return True, value, "Valid", 'OK'

    # ── ISO Zone Tagging ──────────────────────────────────────────────

    def tag_iso_zone(self, vibration_rms: float) -> str:
        """
        Tag vibration reading with ISO 10816-3 zone.
        CORRECTED: >15 kW machinery boundaries.

        Zone A: ≤ 2.3 mm/s (Good / New)
        Zone B: 2.3 – 4.5 mm/s (Acceptable / Normal)
        Zone C: 4.5 – 7.1 mm/s (Unsatisfactory / Degraded)
        Zone D: > 7.1 mm/s (Dangerous / Failure Imminent)
        """
        zones = self.config['thresholds']['vibration']
        
        if vibration_rms <= zones['zone_a']:
            return 'A'
        if vibration_rms <= zones['zone_b']:
            return 'B'
        if vibration_rms <= zones['zone_c']:
            return 'C'
        return 'D'

    def determine_alarms(self, sensors: dict) -> list:
        """
        Determine active alarm codes from sensor readings.
        CORRECTED: Returns CRITICAL for emergency conditions.
        """
        alarms = []
        thresholds = self.config['thresholds']

        # ── Power alarms ──────────────────────────────────────────
        power = sensors.get('power_kw', 0)
        if power > thresholds['energy']['emergency']:
            alarms.append('POWER_EMERGENCY')  # CRITICAL
        elif power > thresholds['energy']['alarm']:
            alarms.append('POWER_ALARM')      # ALARM
        elif power > thresholds['energy']['warning']:
            alarms.append('POWER_WARNING')    # WARNING

        # ── Temperature alarms (motor) ────────────────────────────
        motor_temp = sensors.get('motor_temp', 0)
        if motor_temp > thresholds['temperature']['emergency']:
            alarms.append('TEMP_EMERGENCY')   # CRITICAL
        elif motor_temp > thresholds['temperature']['alarm']:
            alarms.append('TEMP_ALARM')       # ALARM
        elif motor_temp > thresholds['temperature']['warning']:
            alarms.append('TEMP_WARNING')    # WARNING

        # ── RPM alarms ────────────────────────────────────────────
        rpm = sensors.get('rpm', 0)
        if rpm > thresholds['rpm']['emergency']:
            alarms.append('RPM_EMERGENCY')    # CRITICAL
        elif rpm > thresholds['rpm']['alarm']:
            alarms.append('RPM_ALARM')        # ALARM
        elif rpm > thresholds['rpm']['warning']:
            alarms.append('RPM_WARNING')      # WARNING

        # ── Vibration alarms ──────────────────────────────────────
        vib = sensors.get('vibration_rms', 0)
        zone = self.tag_iso_zone(vib)
        if zone == 'D':
            alarms.append('VIB_ZONE_D')      # CRITICAL
        elif zone == 'C':
            alarms.append('VIB_ZONE_C')      # ALARM

        return alarms if alarms else ['NONE']
