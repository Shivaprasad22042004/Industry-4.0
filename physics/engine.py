import math
import random
from datetime import datetime, timezone
from dataclasses import dataclass, field

from .state_machine import MachineState, PRODUCTIVE_STATES
from .validator import SensorValidator


@dataclass
class MachinePhysicsState:
    # The ONLY variables that change over time (the "truth")
    bearing_age_pct: float = 0.0        # 0-100, triggers fault at ~95
    tool_wear_pct: float = 0.0          # 0-100, triggers change alert at 80
    coolant_health_pct: float = 100.0   # 100-0, triggers alarm below 20
    
    # Derived thermal state (updated via differential equation)
    motor_temp_internal: float = 25.0   # °C
    bearing_temp_internal: float = 25.0 # °C
    coolant_temp_internal: float = 22.0 # °C
    
    # RPM state
    spindle_rpm_commanded: float = 0.0
    spindle_rpm_actual: float = 0.0
    
    # Production state
    part_count_shift: int = 0
    defect_count_shift: int = 0
    defect_reason: str | None = None
    cycle_count: int = 0
    last_cycle_time: float = 0.0        # seconds
    current_cycle_time: float = 0.0     # seconds tracking the current part
    
    # Fault state
    active_faults: list = field(default_factory=list)
    
    # Control mode
    control_mode: str = 'NORMAL'        # NORMAL, DEGRADE, RECOVER, MANUAL, DEMO
    degrade_speed_multiplier: float = 1.0 # 1x = real rate, 50x = fast, 5000x = demo
    
    # Manual overrides (only active in MANUAL mode)
    manual_overrides: dict = field(default_factory=dict)


class PhysicsEngine:
    """
    Pure function physics engine for an industrial machine.
    No side effects, no network calls. Computes the next tick state.
    """
    def __init__(self, machine_id: str, config: dict):
        self.machine_id = machine_id
        self.config = config
        self.state_enum = MachineState.STOPPED
        self.state = MachinePhysicsState()
        self.validator = SensorValidator(config)
        
        # Initialize some defaults based on config
        self.state.coolant_temp_internal = config.get('coolant_inlet_temp', 22.0)
        
        # Internal state for OEE part tracking
        self._is_cutting = False
        self._previous_power_kw = 0.0
        self._previous_state = MachineState.STOPPED.value
        self.cycle_start_time = None

    def reset(self):
        """Reset the machine to factory defaults."""
        self.state_enum = MachineState.STOPPED
        self.state = MachinePhysicsState()
        self.state.coolant_temp_internal = self.config.get('coolant_inlet_temp', 22.0)
        self._is_cutting = False

    def set_state(self, new_state: MachineState):
        """Change the operational state."""
        self.state_enum = new_state

    def inject_fault(self, fault: str):
        """Inject a specific fault."""
        if fault not in self.state.active_faults:
            self.state.active_faults.append(fault)

    def _trigger_alarm(self, alarm_type: str):
        """Internal helper to add alarms to active faults if not present."""
        pass # The validator handles tagging alarms for the frontend payload

    def _get_status_code(self, value: float, threshold_dict: dict) -> str:
        if value <= threshold_dict['warning']:
            return 'NORMAL'
        elif value <= threshold_dict['alarm']:
            return 'WARNING'
        elif value <= threshold_dict['emergency']:
            return 'ALARM'
        return 'EMERGENCY'

    def compute_tick(self, dt: float = 0.1) -> dict:
        """
        Computes the complete sensor reading for the next time step.
        dt = delta time in seconds (default 0.1 for 10 Hz)
        """
        # 1. Update health variables based on control mode
        self._update_health_variables(dt)
        
        # 2. Compute commanded RPM from state + machine config
        rpm_target = self._compute_rpm_target()
        self.state.spindle_rpm_commanded = rpm_target
        
        # 3. Apply inertia so RPM ramps up smoothly (takes ~3s to reach max)
        max_accel = self.config['rpm_max'] / 3.0
        rpm_diff = rpm_target - self.state.spindle_rpm_actual
        if abs(rpm_diff) > max_accel * dt:
            self.state.spindle_rpm_actual += math.copysign(max_accel * dt, rpm_diff)
        else:
            self.state.spindle_rpm_actual = rpm_target
            
        # 3b. Apply bearing drag to the actual RPM
        self.state.spindle_rpm_actual = self._apply_bearing_drag(self.state.spindle_rpm_actual)
        
        # 4. Compute cutting force from material + feed + tool wear
        cutting_force = self._compute_cutting_force()
        
        # 5. Compute power from state base + tool wear + cutting force
        power_w = self._compute_power(cutting_force)
        
        # 6. Compute power factor (varies with load)
        power_factor = self._compute_power_factor(power_w)
        
        # 7. Derive current from power, voltage, PF
        voltage = self.config.get('voltage_v', 400)
        # 3-phase power formula: P = sqrt(3) * V * I * PF
        current_a = power_w / (voltage * power_factor * math.sqrt(3)) if power_factor > 0 else 0.0
        
        # 8. Compute vibration from RPM² + bearing_age² + cutting chatter
        vibration = self._compute_vibration(cutting_force)
        
        # 9. Compute temperatures via exponential lag filter
        self._update_temperatures(power_w, dt)
        
        # 10. Run range validator (hard clamp to physical limits)
        sensors_raw = {
            'power_kw': power_w / 1000,
            'current_a': current_a,
            'voltage_v': voltage,
            'power_factor': power_factor,
            'rpm': self.state.spindle_rpm_actual,
            'motor_temp': self.state.motor_temp_internal,
            'bearing_temp': self.state.bearing_temp_internal,
            'coolant_temp': self.state.coolant_temp_internal,
            'vibration_rms': vibration
        }
        
        # Apply manual overrides if in MANUAL mode
        if self.state.control_mode == 'MANUAL':
            for sensor, override in self.state.manual_overrides.items():
                if override.get('locked', False):
                    sensors_raw[sensor] = override['value']

        sensors = self.validator.validate_all(sensors_raw, self.state_enum.value)
        
        # Re-sync actuals if validator clamped them
        self.state.spindle_rpm_actual = sensors.get('rpm', 0.0)
        self.state.motor_temp_internal = sensors.get('motor_temp', 25.0)
        self.state.bearing_temp_internal = sensors.get('bearing_temp', 25.0)
        self.state.coolant_temp_internal = sensors.get('coolant_temp', 22.0)
        
        # 11. Tag ISO vibration zone and alarm flags
        sensors['iso_zone'] = self.validator.tag_iso_zone(sensors['vibration_rms'])
        alarm_codes = self.validator.determine_alarms(sensors)
        
        # Add active faults to alarms payload
        all_alarms = list(set(alarm_codes + self.state.active_faults))
        if 'NONE' in all_alarms and len(all_alarms) > 1:
            all_alarms.remove('NONE')
            
        sensors['status_code'] = 'ALARM' if (len(all_alarms) > 0 and all_alarms != ['NONE']) else 'NORMAL'

        # 12. Detect part completion (power drop pattern) → OEE event
        current_power = sensors['power_kw']
        current_state = self.state_enum.value
        
        oee_event = self._detect_part_completion(
            self._previous_power_kw, current_power,
            self._previous_state, current_state, dt
        )
        
        # Store for next tick
        self._previous_power_kw = current_power
        self._previous_state = current_state
        
        return {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'machine_id': self.machine_id,
            'machine_type': self.config['machine_type'],
            'state': self.state_enum.value,
            'control_mode': self.state.control_mode,
            'production': {
                'part_count_shift': self.state.part_count_shift,
                'defect_count_shift': self.state.defect_count_shift,
                'last_cycle_time_s': round(self.state.last_cycle_time, 1)
            },
            'health': {
                'bearing_age_pct': round(self.state.bearing_age_pct, 1),
                'tool_wear_pct': round(self.state.tool_wear_pct, 1),
                'coolant_health_pct': round(self.state.coolant_health_pct, 1)
            },
            'sensors': {
                'energy': {
                    'power_kw': round(sensors['power_kw'], 2),
                    'current_a': round(sensors['current_a'], 2),
                    'voltage_v': sensors['voltage_v'],
                    'power_factor': round(sensors['power_factor'], 2),
                    'status_code': self._get_status_code(sensors['power_kw'], self.config['thresholds']['energy'])
                },
                'rpm': {
                    'actual': round(sensors['rpm'], 0),
                    'commanded': round(self.state.spindle_rpm_commanded, 0),
                    'deviation_percent': round(((sensors['rpm'] - self.state.spindle_rpm_commanded) / self.state.spindle_rpm_commanded * 100) if self.state.spindle_rpm_commanded > 0 else 0, 1),
                    'status_code': self._get_status_code(sensors['rpm'], self.config['thresholds']['rpm'])
                },
                'temperature': {
                    'motor': round(sensors['motor_temp'], 1),
                    'bearing': round(sensors['bearing_temp'], 1),
                    'coolant': round(sensors['coolant_temp'], 1),
                    'ambient': 24.0,
                    'status_code': self._get_status_code(sensors['motor_temp'], self.config['thresholds']['temperature'])
                },
                'vibration': {
                    'rms_mm_s': round(sensors['vibration_rms'], 2),
                    'peak_mm_s': round(sensors['vibration_rms'] * 1.414, 2),
                    'iso_zone': sensors['iso_zone'],
                    'status_code': 'NORMAL' if sensors['iso_zone'] in ['A', 'B'] else ('ALARM' if sensors['iso_zone'] == 'C' else 'EMERGENCY')
                }
            },
            'oee_event': oee_event,
            'is_manual_override': self.state.control_mode == 'MANUAL',
            'alarm_codes': all_alarms
        }

    def _update_health_variables(self, dt: float):
        if self.state.control_mode == 'NORMAL':
            # Realistic micro-aging
            rate = 0.00000278 * self.state.degrade_speed_multiplier  # % per second
            self.state.bearing_age_pct = min(100, self.state.bearing_age_pct + rate)
            self.state.tool_wear_pct = min(100, self.state.tool_wear_pct + rate * 1.5)
            self.state.coolant_health_pct = max(0, self.state.coolant_health_pct - rate * 0.5)
        
        elif self.state.control_mode == 'DEGRADE':
            # Accelerated degradation
            base_rate = 0.00000278
            rate = base_rate * self.state.degrade_speed_multiplier
            self.state.bearing_age_pct = min(100, self.state.bearing_age_pct + rate)
            self.state.tool_wear_pct = min(100, self.state.tool_wear_pct + rate * 2.0)
            self.state.coolant_health_pct = max(0, self.state.coolant_health_pct - rate * 0.8)
        
        elif self.state.control_mode == 'RECOVER':
            # Maintenance: gradual improvement
            rate = 0.001 * self.state.degrade_speed_multiplier  # 0.1% per second at 1x
            self.state.bearing_age_pct = max(0, self.state.bearing_age_pct - rate)
            self.state.tool_wear_pct = max(0, self.state.tool_wear_pct - rate * 3.0)
            self.state.coolant_health_pct = min(100, self.state.coolant_health_pct + rate * 2.0)
        
        elif self.state.control_mode == 'DEMO':
            # Fast interpolation to target values
            if hasattr(self.state, '_demo_target_bearing'):
                self.state.bearing_age_pct += (self.state._demo_target_bearing - self.state.bearing_age_pct) * (dt / 10)
                self.state.tool_wear_pct += (self.state._demo_target_tool - self.state.tool_wear_pct) * (dt / 10)
                self.state.coolant_health_pct += (self.state._demo_target_coolant - self.state.coolant_health_pct) * (dt / 10)
        
        # Auto-trigger faults
        if self.state.bearing_age_pct > 95 and 'BEARING_FAILURE' not in self.state.active_faults:
            self.state.active_faults.append('BEARING_FAILURE')
            self._trigger_alarm('BEARING_CRITICAL')
        
        if self.state.tool_wear_pct > 85 and 'TOOL_CHANGE_NEEDED' not in self.state.active_faults:
            self.state.active_faults.append('TOOL_CHANGE_NEEDED')
        
        if self.state.coolant_health_pct < 20 and 'COOLANT_FAILURE' not in self.state.active_faults:
            self.state.active_faults.append('COOLANT_FAILURE')
            self._trigger_alarm('COOLANT_LOW')

    def _compute_rpm_target(self) -> float:
        if self.state_enum == MachineState.STOPPED or self.state_enum == MachineState.IDLE:
            return 0.0
        elif self.state_enum == MachineState.WARM_UP:
            return min(1500.0, self.config['typical_rpm'])
        elif self.state_enum == MachineState.RUNNING:
            return float(self.config['typical_rpm'])
        return 0.0

    def _apply_bearing_drag(self, rpm_target: float) -> float:
        if self.state_enum in [MachineState.STOPPED, MachineState.IDLE]:
            return 0.0
        
        # Base drag: bearing_age × 0.02% per percent
        drag = (self.state.bearing_age_pct / 100) * 0.02
        drag = min(drag, 0.15)
        
        rpm_actual = rpm_target * (1.0 - drag)
        noise = random.gauss(0, rpm_actual * 0.003) if rpm_actual > 0 else 0
        
        if self.state.bearing_age_pct > 80:
            wobble = random.gauss(0, rpm_actual * 0.05 * (self.state.bearing_age_pct - 80) / 20)
            rpm_actual += wobble
        
        return max(0, rpm_actual + noise)

    def _compute_cutting_force(self) -> float:
        if self.state_enum != MachineState.RUNNING:
            return 0.0
        # Simulated cutting force base 500-2000N based on machine type
        base_force = 1000.0
        if self.config['machine_type'] == 'cnc': base_force = 2000.0
        if self.config['machine_type'] == 'mill': base_force = 1500.0
        
        # Varies slightly over time
        noise = random.uniform(-0.1, 0.1) * base_force
        return base_force + noise

    def _compute_torque(self, cutting_force: float) -> float:
        # Simple proxy: force * arbitrary radius
        return cutting_force * 0.05

    def _compute_power(self, cutting_force: float) -> float:
        if self.state_enum == MachineState.STOPPED:
            return 0.0
        
        if self.state_enum == MachineState.IDLE:
            base_min, base_max = self.config['idle_power_kw']
            return random.uniform(base_min, base_max) * 1000.0
        
        if self.state_enum == MachineState.WARM_UP:
            rpm_ratio = self.state.spindle_rpm_actual / self.config['rpm_max']
            return (2000 + rpm_ratio * 3000)
        
        # RUNNING state
        ideal = max(1.0, self.config.get('ideal_cycle_time_s', 60))
        if self.state.tool_wear_pct > 70:
            ideal *= 1.1
            
        cycle_progress = self.state.current_cycle_time / ideal
        
        # Last 15% of cycle is tool retract / part change (idle power)
        if cycle_progress > 0.85:
            base_load_ratio = 0.05
        else:
            # Map 0 to 0.85 into a 0 to 1 range for the cutting phase
            cut_progress = cycle_progress / 0.85
            
            # Smooth trapezoidal load curve (ramp up, hold steady, ramp down)
            if cut_progress < 0.1:
                base_load_ratio = 0.05 + (cut_progress / 0.1) * 0.45
            elif cut_progress > 0.9:
                base_load_ratio = 0.50 - ((cut_progress - 0.9) / 0.1) * 0.45
            else:
                # Sustained cutting load with very slow, gentle waving
                base_load_ratio = 0.50 + 0.02 * math.sin(cut_progress * 4 * math.pi)
        
        # Micro-noise (only 0.2% so the dial doesn't jitter crazily)
        base_load_ratio += random.uniform(-0.002, 0.002)
        
        mechanical_power = self.config['power_rated_w'] * base_load_ratio
        
        wear_penalty = 1.0 + (self.state.tool_wear_pct / 100) * 0.12
        health_penalty = 1.0 + (self.state.bearing_age_pct / 100) * 0.25
        coolant_penalty = 1.0 + ((100 - self.state.coolant_health_pct) / 100) * 0.15
        
        electrical_power = (mechanical_power * wear_penalty * health_penalty * coolant_penalty) / self.config['efficiency']
        
        if self.state.motor_temp_internal > 80:
            thermal_penalty = 1.0 + ((self.state.motor_temp_internal - 80) * 0.005)
            electrical_power *= thermal_penalty
            
        # Add baseline friction/idle power
        base_min, _ = self.config['idle_power_kw']
        electrical_power += (base_min * 1000.0)
        
        max_allowed = self.config['power_hard_clamp_w']
        return min(electrical_power, max_allowed)

    def _compute_power_factor(self, power_w: float) -> float:
        load_ratio = power_w / self.config['power_rated_w']
        pf = 0.3 + (load_ratio * 0.62)
        pf = max(0.3, min(0.95, pf))
        pf -= (self.state.bearing_age_pct / 100) * 0.04
        return round(max(0.25, pf), 3)

    def _compute_vibration(self, cutting_force: float) -> float:
        if self.state_enum == MachineState.STOPPED:
            return 0.0
        if self.state_enum == MachineState.IDLE:
            return random.uniform(0.1, self.config['vibration_idle'])
        
        rpm_ratio = self.state.spindle_rpm_actual / self.config['rpm_max']
        imbalance = self.config['vibration_idle'] * (rpm_ratio ** 2)
        
        bearing_vib = (self.state.bearing_age_pct / 100) ** 2 * 4.0
        
        chatter = 0.0
        if self.state_enum == MachineState.RUNNING and self.state.tool_wear_pct > 60:
            burst_probability = (self.state.tool_wear_pct - 60) / 40
            if random.random() < burst_probability * 0.3:
                burst_amplitude = ((self.state.tool_wear_pct - 60) / 40) * 3.0
                chatter = burst_amplitude * random.uniform(0.5, 1.5)
                
        cutting_vib = (cutting_force / 1000) * 0.1
        thermal_imbalance = max(0, (self.state.motor_temp_internal - 60) * 0.02)
        
        total = imbalance + bearing_vib + chatter + cutting_vib + thermal_imbalance
        noise = random.gauss(0, 0.05)
        
        return max(0, total + noise)

    def _update_temperatures(self, power_w: float, dt: float):
        # Calculate a stable target temperature based on current power load
        ambient = 24.0
        load_ratio = power_w / self.config['power_rated_w']
        
        if self.state_enum == MachineState.STOPPED:
            target_motor = ambient
        else:
            # Base rise is up to 45C above ambient at 100% load (Normal max is ~70C)
            base_rise = load_ratio * 45.0
            
            # Penalties that increase the steady-state temperature
            wear_factor = 1.0 + (self.state.bearing_age_pct / 100) * 0.5
            coolant_factor = 1.0 + ((100 - self.state.coolant_health_pct) / 100) * 0.5
            
            target_motor = ambient + (base_rise * wear_factor * coolant_factor)
            
        # Exponential interpolation (Newton's Law of Cooling) prevents runaway
        tau = self.config['thermal_tau_seconds']
        if self.state_enum == MachineState.STOPPED:
            tau *= 0.25 # Cool down much faster when stopped
            
        # Prevents division by zero
        alpha = 1.0 - math.exp(-dt / max(1.0, tau))
        self.state.motor_temp_internal += (target_motor - self.state.motor_temp_internal) * alpha
        self.state.motor_temp_internal = max(ambient, self.state.motor_temp_internal)

        target_bearing_temp = self.state.motor_temp_internal * 0.85 + (self.state.bearing_age_pct / 100) * 15
        self.state.bearing_temp_internal += (target_bearing_temp - self.state.bearing_temp_internal) * alpha
        
        # Coolant temperature 
        if self.state_enum == MachineState.STOPPED:
            target_coolant = ambient
        else:
            target_coolant = ambient + (load_ratio * 15.0) * (1.0 + ((100 - self.state.coolant_health_pct) / 100))
            
        self.state.coolant_temp_internal += (target_coolant - self.state.coolant_temp_internal) * alpha
        self.state.coolant_temp_internal = max(ambient, self.state.coolant_temp_internal)

    def _detect_part_completion(self, previous_power: float, current_power: float, 
                               previous_state: str, current_state: str, dt: float) -> dict | None:
        """
        Detect when a part finishes based on power drop pattern or state transition.
        """
        oee_event = None
        
        if current_state == 'RUNNING':
            self.state.current_cycle_time += dt
            if self.cycle_start_time is None:
                self.cycle_start_time = True
                
        # Method 1: State transition RUNNING → IDLE/TOOL_CHANGE
        if previous_state == 'RUNNING' and current_state in ('IDLE', 'TOOL_CHANGE'):
            if self.state.current_cycle_time > 10:  # Minimum valid cycle
                self.state.part_count_shift += 1
                self.state.cycle_count += 1
                cycle_time = self.state.current_cycle_time
                self.state.last_cycle_time = cycle_time
                oee_event = {
                    'event_type': 'PART_COMPLETE',
                    'cycle_time_actual_s': round(cycle_time, 1),
                    'cycle_time_ideal_s': self.config.get('ideal_cycle_time_s', 60),
                    'part_good': self._determine_part_quality()
                }
                self.state.current_cycle_time = 0.0
                self.cycle_start_time = None
                
        # Method 2: Ideal cycle met (simulating power drop / part retract)
        elif current_state == 'RUNNING':
            ideal = max(1.0, self.config.get('ideal_cycle_time_s', 60))
            if self.state.tool_wear_pct > 70:
                ideal *= 1.1
                
            if self.state.current_cycle_time >= ideal:
                # Part complete!
                self.state.part_count_shift += 1
                self.state.cycle_count += 1
                cycle_time = self.state.current_cycle_time
                self.state.last_cycle_time = cycle_time
                oee_event = {
                    'event_type': 'PART_COMPLETE',
                    'cycle_time_actual_s': round(cycle_time, 1),
                    'cycle_time_ideal_s': self.config.get('ideal_cycle_time_s', 60),
                    'part_good': self._determine_part_quality()
                }
                self.state.current_cycle_time = 0.0 # Reset for next part
        
        return oee_event

    def _determine_part_quality(self) -> bool:
        """
        Determine if the part just produced is good or defective based on physical conditions.
        """
        # Base defect probability: 0.5% for perfect machine
        defect_prob = 0.005
        
        # Bearing wear contribution: up to +15% at 100%
        defect_prob += (self.state.bearing_age_pct / 100) * 0.15
        
        # Tool wear contribution: up to +20% at 100%
        defect_prob += (self.state.tool_wear_pct / 100) * 0.20
        
        # Temperature contribution: above 80°C adds risk
        if self.state.motor_temp_internal > 80:
            defect_prob += (self.state.motor_temp_internal - 80) * 0.002
        
        # Coolant contribution: poor coolant = poor chip evacuation = surface defects
        if self.state.coolant_health_pct < 30:
            defect_prob += 0.08
            
        # Vibration check (approximate inline)
        rpm_ratio = self.state.spindle_rpm_actual / self.config['rpm_max']
        vib = self.config['vibration_idle'] * (rpm_ratio ** 2) + (self.state.bearing_age_pct / 100) ** 2 * 4.0
        if vib > 4.5:  # Zone C or D
            defect_prob += 0.10
        
        # Clamp to realistic maximum (max 35% defect rate)
        defect_prob = min(defect_prob, 0.35)
        
        # Roll the dice
        is_good = random.random() > defect_prob
        
        # Log for analytics
        if not is_good:
            self.state.defect_count_shift += 1
            self.state.defect_reason = self._pick_defect_reason(vib)
        else:
            self.state.defect_reason = None
            
        return is_good

    def _pick_defect_reason(self, vib: float) -> str:
        """Determine why this part was defective."""
        reasons = []
        if self.state.bearing_age_pct > 70:
            reasons.append('SURFACE_FINISH')
        if self.state.tool_wear_pct > 75:
            reasons.append('DIMENSIONAL_ERROR')
        if self.state.motor_temp_internal > 85:
            reasons.append('THERMAL_DEFORMATION')
        if vib > 4.5:
            reasons.append('CHATTER_MARKS')
        if self.state.coolant_health_pct < 30:
            reasons.append('CHIP_SCORE')
        
        return random.choice(reasons) if reasons else 'UNKNOWN_DEFECT'
