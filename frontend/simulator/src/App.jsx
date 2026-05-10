import React, { useState, useEffect } from 'react';
import MachineCard from './components/MachineCard';
import { Zap, Play, Square, FastForward, RotateCcw } from 'lucide-react';

const API_BASE = 'http://localhost:8000';
const WS_URL = 'ws://localhost:8000/ws/live';

function App() {
  const [machines, setMachines] = useState({});
  const [connected, setConnected] = useState(false);
  const [speed, setSpeed] = useState(1);

  // WebSocket Connection
  useEffect(() => {
    let ws;
    let reconnectTimer;

    const connect = () => {
      ws = new WebSocket(WS_URL);
      
      ws.onopen = () => {
        setConnected(true);
        console.log("Connected to live telemetry");
      };
      
      ws.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          if (payload.machines) {
            setMachines(payload.machines);
          }
        } catch (err) {
          console.error("Payload parsing error:", err);
        }
      };
      
      ws.onclose = () => {
        setConnected(false);
        // Auto-reconnect after 2 seconds
        reconnectTimer = setTimeout(connect, 2000);
      };
    };

    connect();

    return () => {
      clearTimeout(reconnectTimer);
      if (ws) ws.close();
    };
  }, []);

  // API Actions
  const handleStateChange = async (machineId, newState) => {
    try {
      await fetch(`${API_BASE}/machines/${machineId}/state`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ state: newState })
      });
    } catch (err) {
      console.error("Error setting state:", err);
    }
  };

  const handleModeChange = async (machineId, mode, multiplier, demoTargets = null) => {
    const payload = { mode, speed_multiplier: multiplier };
    
    if (mode === 'DEMO' && demoTargets) {
      payload.target_bearing_age = demoTargets.bearing;
      payload.target_tool_wear = demoTargets.tool;
      payload.target_coolant_health = demoTargets.coolant;
    }

    try {
      await fetch(`${API_BASE}/machines/${machineId}/mode`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
    } catch (err) {
      console.error("Error setting mode:", err);
    }
  };

  // Global Actions
  const handleGlobalAction = async (action) => {
    const machineIds = Object.keys(machines);
    for (const id of machineIds) {
      if (action === 'START') {
        // Slow start sequence
        handleStateChange(id, 'WARM_UP');
        setTimeout(() => handleStateChange(id, 'IDLE'), 3000);
        setTimeout(() => handleStateChange(id, 'RUNNING'), 6000);
      } else if (action === 'STOP') {
        handleStateChange(id, 'IDLE');
        setTimeout(() => handleStateChange(id, 'STOPPED'), 2000);
      }
    }
  };

  const handleResetAll = async () => {
    try {
      await fetch(`${API_BASE}/machines/reset-all`, { method: 'POST' });
    } catch (err) {
      console.error("Error resetting machines:", err);
    }
  };

  return (
    <>
      <header className="dashboard-header">
        <div className="header-title">
          <Zap color="var(--primary)" size={28} />
          <h1>INDUSTRY 4.0 SIMULATOR</h1>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '20px' }}>
          <a href="http://localhost:5174" target="_blank" className="btn btn-primary" style={{ textDecoration: 'none', background: 'linear-gradient(90deg, #8b5cf6, #3b82f6)' }}>
            Launch Analytics Dashboard 🚀
          </a>
          <div className="status-badge" style={{ borderColor: connected ? 'rgba(0, 230, 118, 0.2)' : 'rgba(255, 23, 68, 0.2)', color: connected ? 'var(--success)' : 'var(--danger)' }}>
            <div className="status-dot" style={{ backgroundColor: connected ? 'var(--success)' : 'var(--danger)' }}></div>
            {connected ? 'LIVE (10 Hz)' : 'DISCONNECTED'}
          </div>
        </div>
      </header>

      <main className="dashboard-content">
        <div className="machine-grid">
          {Object.entries(machines).map(([id, data]) => (
            <MachineCard 
              key={id} 
              machineId={id} 
              data={data} 
              onStateChange={handleStateChange}
              onModeChange={handleModeChange}
            />
          ))}
          {Object.keys(machines).length === 0 && connected && (
            <div style={{gridColumn: '1/-1', textAlign: 'center', padding: '3rem', color: 'var(--text-muted)'}}>
              Waiting for telemetry data...
            </div>
          )}
        </div>

        <div className="glass-panel global-actions">
          <div className="action-group">
            <h3>Global Controls</h3>
            <button className="btn btn-primary" onClick={() => handleGlobalAction('START')}>
              <Play size={16} /> START ALL
            </button>
            <button className="btn" onClick={() => handleGlobalAction('STOP')}>
              <Square size={16} /> STOP ALL
            </button>
            <button className="btn btn-danger" onClick={handleResetAll}>
              <RotateCcw size={16} /> RESET ALL
            </button>
          </div>
          <div className="action-group">
            <span>Global Simulation Time Speed:</span>
            <select className="glass-select" value={speed} onChange={(e) => setSpeed(Number(e.target.value))}>
              <option value={1}>1x (Real Time)</option>
              <option value={2}>2x</option>
              <option value={10}>10x</option>
              <option value={100}>100x</option>
              <option value={1000}>1000x</option>
            </select>
            <button className="btn" onClick={async () => {
              try {
                await fetch(`${API_BASE}/machines/speed`, {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ speed: speed })
                });
              } catch (err) { console.error(err); }
            }}>Apply Speed to All</button>
          </div>
        </div>
      </main>
    </>
  );
}

export default App;
