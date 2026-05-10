"""
Machine Configurations — Physical Limits & Thresholds
=====================================================

Each machine has hard physical limits that the validator enforces.
These are NON-NEGOTIABLE — the physics engine cannot exceed them.

4 machines: CNC-001, LATHE-001, MILL-001, DRILL-001
"""

MACHINE_CONFIGS = {
    'cnc-001': {
        'machine_type': 'cnc',
        'display_name': 'CNC Machining Center',

        # Power ratings (kW)
        'power_rated_w': 15000,
        'power_max_w': 22000,
        'power_hard_clamp_w': 28600,

        # Spindle
        'rpm_max': 12000,
        'rpm_base': 2630,
        'rpm_min': 50,
        'torque_max_nm': 250,

        # Motor
        'efficiency': 0.92,
        'voltage_v': 400,

        # Thermal
        'thermal_mass': 500,
        'thermal_tau_seconds': 600,
        'coolant_inlet_temp': 22,

        # Vibration
        'vibration_idle': 0.5,

        # Operating parameters
        'typical_rpm': 2000,
        'idle_power_kw': (1.8, 2.5),

        # Cycle time (for OEE)
        'ideal_cycle_time_s': 180,
        'cycle_time_variance': 0.05,

        # Thresholds (normal_max, moderate_max, danger_max)
        'thresholds': {
            'energy': {
                'warning': 15.0,
                'alarm': 22.0,
                'emergency': 28.6,
            },
            'rpm': {
                'warning': 8000,
                'alarm': 11000,
                'emergency': 12000,
            },
            'temperature': {
                'warning': 75,
                'alarm': 90,
                'emergency': 105,
            },
            'vibration': {
                'zone_a': 2.3,
                'zone_b': 4.5,
                'zone_c': 7.1,
                'zone_d': 7.1,
            },
        },
    },

    'lathe-001': {
        'machine_type': 'lathe',
        'display_name': 'CNC Turning Center',

        'power_rated_w': 7500,
        'power_max_w': 11000,
        'power_hard_clamp_w': 14300,

        'rpm_max': 3000,
        'rpm_base': 1500,
        'rpm_min': 30,
        'torque_max_nm': 120,

        'efficiency': 0.90,
        'voltage_v': 400,

        'thermal_mass': 300,
        'thermal_tau_seconds': 400,
        'coolant_inlet_temp': 22,

        'vibration_idle': 0.3,

        'typical_rpm': 800,
        'idle_power_kw': (0.8, 1.5),

        'ideal_cycle_time_s': 120,
        'cycle_time_variance': 0.06,

        'thresholds': {
            'energy': {
                'warning': 7.5,
                'alarm': 11.0,
                'emergency': 14.3,
            },
            'rpm': {
                'warning': 2000,
                'alarm': 2700,
                'emergency': 3000,
            },
            'temperature': {
                'warning': 65,
                'alarm': 80,
                'emergency': 95,
            },
            'vibration': {
                'zone_a': 2.3,
                'zone_b': 4.5,
                'zone_c': 7.1,
                'zone_d': 7.1,
            },
        },
    },

    'mill-001': {
        'machine_type': 'mill',
        'display_name': 'Vertical Milling Machine',

        'power_rated_w': 11000,
        'power_max_w': 15000,
        'power_hard_clamp_w': 19500,

        'rpm_max': 6000,
        'rpm_base': 2000,
        'rpm_min': 40,
        'torque_max_nm': 180,

        'efficiency': 0.91,
        'voltage_v': 400,

        'thermal_mass': 400,
        'thermal_tau_seconds': 500,
        'coolant_inlet_temp': 22,

        'vibration_idle': 0.4,

        'typical_rpm': 3000,
        'idle_power_kw': (1.2, 2.0),

        'ideal_cycle_time_s': 240,
        'cycle_time_variance': 0.07,

        'thresholds': {
            'energy': {
                'warning': 11.0,
                'alarm': 15.0,
                'emergency': 19.5,
            },
            'rpm': {
                'warning': 4500,
                'alarm': 5500,
                'emergency': 6000,
            },
            'temperature': {
                'warning': 70,
                'alarm': 82,
                'emergency': 95,
            },
            'vibration': {
                'zone_a': 2.3,
                'zone_b': 4.5,
                'zone_c': 7.1,
                'zone_d': 7.1,
            },
        },
    },

    'drill-001': {
        'machine_type': 'drill',
        'display_name': 'CNC Drill Press',

        'power_rated_w': 2200,
        'power_max_w': 3500,
        'power_hard_clamp_w': 4550,

        'rpm_max': 3000,
        'rpm_base': 1200,
        'rpm_min': 30,
        'torque_max_nm': 35,

        'efficiency': 0.88,
        'voltage_v': 400,

        'thermal_mass': 150,
        'thermal_tau_seconds': 180,
        'coolant_inlet_temp': 22,

        'vibration_idle': 0.2,

        'typical_rpm': 1500,
        'idle_power_kw': (0.3, 0.6),

        'ideal_cycle_time_s': 60,
        'cycle_time_variance': 0.08,

        'thresholds': {
            'energy': {
                'warning': 2.2,
                'alarm': 3.5,
                'emergency': 4.55,
            },
            'rpm': {
                'warning': 2500,
                'alarm': 2700,
                'emergency': 3000,
            },
            'temperature': {
                'warning': 55,
                'alarm': 70,
                'emergency': 85,
            },
            'vibration': {
                'zone_a': 2.3,
                'zone_b': 4.5,
                'zone_c': 7.1,
                'zone_d': 7.1,
            },
        },
    },
}

def get_config(machine_id: str) -> dict:
    """Get machine config by ID, raises KeyError if not found."""
    if machine_id not in MACHINE_CONFIGS:
        raise KeyError(
            f"Unknown machine_id '{machine_id}'. "
            f"Valid IDs: {list(MACHINE_CONFIGS.keys())}"
        )
    return MACHINE_CONFIGS[machine_id]


def get_all_machine_ids() -> list:
    """Return list of all configured machine IDs."""
    return list(MACHINE_CONFIGS.keys())
