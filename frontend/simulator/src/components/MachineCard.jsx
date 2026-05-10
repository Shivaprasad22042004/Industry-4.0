import React from 'react';
import { Power, RotateCcw, Thermometer, Activity, Settings, AlertTriangle, PenTool } from 'lucide-react';

const MachineCard = ({ machineId, data, onStateChange, onModeChange }) => {
  if (!data) return null;

  const { machine_type, state, control_mode, health, sensors, alarm_codes } = data;
  
  // Format helpers
  const formatVal = (val) => val !== undefined ? val : '---';
  
  // Handlers
  const handleStateSelect = (e) => onStateChange(machineId, e.target.value);
  
  return (
    <div className={`glass-panel machine-card ${alarm_codes.includes('NONE') ? '' : 'has-alarm'}`}>
      
      {/* Header */}
      <div className="machine-header">
        <div className="machine-info">
          <h2>
            {machine_type === 'cnc' && '🖥️'}
            {machine_type === 'lathe' && '🔧'}
            {machine_type === 'mill' && '⚙️'}
            {machine_type === 'drill' && '🕳️'}
            {' '} {machineId.toUpperCase()}
          </h2>
          <span className="machine-type">{machine_type} Center</span>
        </div>
        
        {/* State Selector */}
        <select 
          className={`glass-select status-${state}`} 
          value={state}
          onChange={handleStateSelect}
        >
          <option value="STOPPED">● STOPPED</option>
          <option value="IDLE">○ IDLE</option>
          <option value="WARM_UP">♨ WARM UP</option>
          <option value="RUNNING">▶ RUNNING</option>
          <option value="TOOL_CHANGE">🔧 TOOL CHANGE</option>
          <option value="MAINTENANCE">🛠 MAINTENANCE</option>
          <option value="BREAKDOWN">✖ BREAKDOWN</option>
        </select>
      </div>

      {/* Alarms (if any) */}
      {!alarm_codes.includes('NONE') && (
        <div className="alarms-container" style={{color: 'var(--danger)', fontSize: '0.8rem', display: 'flex', gap: '0.5rem', flexWrap: 'wrap'}}>
          <AlertTriangle size={14} />
          {alarm_codes.map(code => <span key={code} style={{background: 'rgba(255,23,68,0.2)', padding: '2px 6px', borderRadius: '4px'}}>{code}</span>)}
        </div>
      )}

      {/* Sensors */}
      <div className="sensors-grid">
        <div className="sensor-box">
          <div className="sensor-label">
            <span><Power size={14}/> Power</span>
            <span className={`val-${sensors.energy.status_code}`}>
              {sensors.energy.status_code}
            </span>
          </div>
          <div className={`sensor-value val-${sensors.energy.status_code}`}>
            {formatVal(sensors.energy.power_kw)} <span className="sensor-unit">kW</span>
          </div>
        </div>

        <div className="sensor-box">
          <div className="sensor-label">
            <span><RotateCcw size={14}/> Spindle</span>
            <span className={`val-${sensors.rpm.status_code}`}>
              {sensors.rpm.status_code}
            </span>
          </div>
          <div className={`sensor-value val-${sensors.rpm.status_code}`}>
            {formatVal(sensors.rpm.actual)} <span className="sensor-unit">RPM</span>
          </div>
        </div>

        <div className="sensor-box">
          <div className="sensor-label">
            <span><Thermometer size={14}/> Motor Temp</span>
            <span className={`val-${sensors.temperature.status_code}`}>
              {sensors.temperature.status_code}
            </span>
          </div>
          <div className={`sensor-value val-${sensors.temperature.status_code}`}>
            {formatVal(sensors.temperature.motor)} <span className="sensor-unit">°C</span>
          </div>
        </div>

        <div className="sensor-box">
          <div className="sensor-label">
            <span><Activity size={14}/> Vibration</span>
            <span className={`val-${sensors.vibration.status_code}`}>
              Zone {sensors.vibration.iso_zone}
            </span>
          </div>
          <div className={`sensor-value val-${sensors.vibration.status_code}`}>
            {formatVal(sensors.vibration.rms_mm_s)} <span className="sensor-unit">mm/s</span>
          </div>
        </div>
      </div>

      {/* Health Bars */}
      <div className="health-section">
        <div className="health-bar-container">
          <div className="health-bar-header">
            <span><Settings size={12}/> Bearing Wear</span>
            <span>{health.bearing_age_pct}%</span>
          </div>
          <div className="health-bar-bg">
            <div className="health-bar-fill fill-bearing" style={{width: `${health.bearing_age_pct}%`}}></div>
          </div>
        </div>

        <div className="health-bar-container">
          <div className="health-bar-header">
            <span><PenTool size={12}/> Tool Wear</span>
            <span>{health.tool_wear_pct}%</span>
          </div>
          <div className="health-bar-bg">
            <div className="health-bar-fill fill-tool" style={{width: `${health.tool_wear_pct}%`}}></div>
          </div>
        </div>

        <div className="health-bar-container">
          <div className="health-bar-header">
            <span>💧 Coolant Health</span>
            <span>{health.coolant_health_pct}%</span>
          </div>
          <div className="health-bar-bg">
            <div className="health-bar-fill fill-coolant" style={{width: `${health.coolant_health_pct}%`}}></div>
          </div>
        </div>
      </div>

      {/* Controls */}
      <div className="machine-controls">
        <button 
          className={`btn ${control_mode === 'NORMAL' ? 'btn-primary' : ''}`}
          onClick={() => onModeChange(machineId, 'NORMAL', 1.0)}
        >
          🟢 NORMAL
        </button>
        <button 
          className={`btn ${control_mode === 'DEGRADE' ? 'btn-primary' : ''}`}
          onClick={() => onModeChange(machineId, 'DEGRADE', 100.0)}
        >
          🟡 DEGRADE (100x)
        </button>
        <button 
          className={`btn ${control_mode === 'RECOVER' ? 'btn-primary' : ''}`}
          onClick={() => onModeChange(machineId, 'RECOVER', 100.0)}
        >
          🔧 RECOVER
        </button>
        <button 
          className="btn btn-danger"
          onClick={() => onModeChange(machineId, 'DEMO', 1.0, { bearing: 85, tool: 90, coolant: 10 })}
        >
          📊 DEMO (Instant Failure)
        </button>
      </div>

    </div>
  );
};

export default MachineCard;
