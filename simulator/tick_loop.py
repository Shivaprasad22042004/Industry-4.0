import asyncio
from datetime import datetime, timezone

from machines.config import MACHINE_CONFIGS
from physics.engine import PhysicsEngine
from database import db


class SimulatorManager:
    """
    Manages the async tick loop and holds the global state of all machines.
    """
    def __init__(self):
        self.machines = {}
        self.latest_telemetry = {}
        self._running = False
        self._task = None
        self.time_speed = 1.0

        # Initialize all 4 machines from config
        for machine_id, config in MACHINE_CONFIGS.items():
            self.machines[machine_id] = PhysicsEngine(machine_id, config)
            self.latest_telemetry[machine_id] = None

    async def start(self):
        """Start the 10 Hz tick loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self):
        """Stop the tick loop."""
        self._running = False
        if self._task:
            await self._task
            
    def get_live_snapshot(self) -> dict:
        """Returns the most recent payload for all machines."""
        return {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'machines': self.latest_telemetry
        }

    async def _loop(self):
        """10 Hz internal physics clock (dt = 0.1s)."""
        dt_base = 0.1
        while self._running:
            dt_effective = dt_base * self.time_speed
            for machine_id, engine in self.machines.items():
                payload = engine.compute_tick(dt_effective)
                self.latest_telemetry[machine_id] = payload
            
            # Fire and forget DB insertion
            asyncio.create_task(db.insert_telemetry_batch(self.latest_telemetry))
            
            await asyncio.sleep(dt_base)


# Global singleton instance
_simulator = SimulatorManager()

def get_simulator() -> SimulatorManager:
    return _simulator
