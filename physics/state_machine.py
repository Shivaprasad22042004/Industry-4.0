"""
Machine State Machine
=====================

Defines the operational states a machine can be in,
and valid transitions between them.

States:
    STOPPED     → Machine is off, no power draw
    IDLE        → Machine is on, baseline power, spindle NOT spinning
    WARM_UP     → Spindle running at partial RPM, no cutting (pre-production)
    RUNNING     → Full production — cutting, all sensors active
    TOOL_CHANGE → Planned micro-stop for tool swap (~30-120s)
    MAINTENANCE → Planned downtime (operator-initiated)
    BREAKDOWN   → Unplanned downtime (fault-triggered or operator-injected)
    COOLDOWN    → Post-production spindle deceleration
"""

from enum import Enum


class MachineState(Enum):
    STOPPED = 'STOPPED'
    IDLE = 'IDLE'
    WARM_UP = 'WARM_UP'
    RUNNING = 'RUNNING'
    TOOL_CHANGE = 'TOOL_CHANGE'
    MAINTENANCE = 'MAINTENANCE'
    BREAKDOWN = 'BREAKDOWN'
    COOLDOWN = 'COOLDOWN'


# Valid state transitions: from_state → [allowed_to_states]
STATE_TRANSITIONS = {
    MachineState.STOPPED: [
        MachineState.IDLE,
    ],
    MachineState.IDLE: [
        MachineState.WARM_UP,
        MachineState.MAINTENANCE,
        MachineState.STOPPED,
    ],
    MachineState.WARM_UP: [
        MachineState.RUNNING,
        MachineState.IDLE,          # Abort warm-up
        MachineState.BREAKDOWN,     # Fault during warm-up
    ],
    MachineState.RUNNING: [
        MachineState.TOOL_CHANGE,
        MachineState.COOLDOWN,
        MachineState.BREAKDOWN,     # Fault during production
        MachineState.MAINTENANCE,   # Emergency maintenance
    ],
    MachineState.TOOL_CHANGE: [
        MachineState.RUNNING,       # Resume after tool swap
        MachineState.BREAKDOWN,     # Fault during tool change
        MachineState.IDLE,          # Operator pulls machine offline
    ],
    MachineState.MAINTENANCE: [
        MachineState.IDLE,          # Maintenance complete → back online
        MachineState.STOPPED,       # Shutdown for major maintenance
    ],
    MachineState.BREAKDOWN: [
        MachineState.MAINTENANCE,   # Repair initiated
        MachineState.STOPPED,       # Full shutdown
    ],
    MachineState.COOLDOWN: [
        MachineState.IDLE,          # Spindle stopped, ready for next job
        MachineState.STOPPED,       # Full shutdown
        MachineState.BREAKDOWN,     # Fault during cooldown
    ],
}


def can_transition(from_state: MachineState, to_state: MachineState) -> bool:
    """Check if a state transition is valid."""
    if from_state == to_state:
        return True  # No-op is always valid
    return to_state in STATE_TRANSITIONS.get(from_state, [])


def get_valid_transitions(from_state: MachineState) -> list:
    """Get list of states reachable from the given state."""
    return STATE_TRANSITIONS.get(from_state, [])


# States where the machine is "producing" (for OEE availability)
PRODUCTIVE_STATES = {MachineState.RUNNING}

# States where the machine is "available" (powered on, could produce)
AVAILABLE_STATES = {
    MachineState.IDLE,
    MachineState.WARM_UP,
    MachineState.RUNNING,
    MachineState.TOOL_CHANGE,
    MachineState.COOLDOWN,
}

# States that count as downtime
DOWNTIME_STATES = {
    MachineState.STOPPED,
    MachineState.MAINTENANCE,
    MachineState.BREAKDOWN,
}

# Planned vs unplanned downtime
PLANNED_DOWNTIME_STATES = {MachineState.MAINTENANCE, MachineState.TOOL_CHANGE}
UNPLANNED_DOWNTIME_STATES = {MachineState.BREAKDOWN}
