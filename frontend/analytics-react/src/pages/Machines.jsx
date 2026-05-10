import React, { useState } from 'react';

const API_BASE = 'http://localhost:8000';

function HealthBar({ value, reverse = false, warn = 70, crit = 90 }) {
  const pct = parseFloat(value) || 0;
  const effectivePct = reverse ? 100 - pct : pct;
  const color = effectivePct < warn
    ? 'var(--status-running)'
    : effectivePct < crit
    ? 'var(--status-idle)'
    : 'var(--alert-critical)';
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
      <div style={{ flex: 1, height: '6px', background: 'rgba(255,255,255,0.08)', borderRadius: '999px', overflow: 'hidden' }}>
        <div style={{ width: `${Math.min(100, pct)}%`, height: '100%', background: color, borderRadius: '999px', transition: 'width 0.5s' }} />
      </div>
      <span style={{ fontSize: '0.7rem', fontWeight: 700, color, minWidth: '36px', textAlign: 'right' }}>{pct.toFixed(0)}%</span>
    </div>
  );
}

function StateChip({ state }) {
  const map = {
    RUNNING:  { color: 'var(--status-running)',  bg: 'rgba(16,185,129,0.12)' },
    IDLE:     { color: 'var(--status-idle)',     bg: 'rgba(245,158,11,0.12)' },
    WARM_UP:  { color: 'var(--status-idle)',     bg: 'rgba(245,158,11,0.12)' },
    COOLDOWN: { color: 'var(--status-idle)',     bg: 'rgba(245,158,11,0.12)' },
    STOPPED:  { color: 'var(--text-muted)',      bg: 'rgba(148,163,184,0.1)' },
  };
  const style = map[state] || map.STOPPED;
  return (
    <span style={{ fontSize: '0.65rem', fontWeight: 700, padding: '2px 8px', borderRadius: '999px',
      color: style.color, background: style.bg, letterSpacing: '0.05em' }}>
      {state}
    </span>
  );
}

export default function Machines({ machines, setSelectedMachine, setIsDrawerOpen, historicalOee }) {
  const [sortBy, setSortBy] = useState('id');
  const [injecting, setInjecting] = useState({});

  const machineList = Object.entries(machines)
    .filter(([, m]) => m)
    .sort(([idA, mA], [idB, mB]) => {
      if (sortBy === 'oee') {
        const oeeA = historicalOee?.machines?.[idA]?.oee ?? 0;
        const oeeB = historicalOee?.machines?.[idB]?.oee ?? 0;
        return oeeB - oeeA;
      }
      if (sortBy === 'power') return (mB.sensors?.energy?.power_kw || 0) - (mA.sensors?.energy?.power_kw || 0);
      if (sortBy === 'wear') return (mB.health?.tool_wear_pct || 0) - (mA.health?.tool_wear_pct || 0);
      return idA.localeCompare(idB);
    });

  const injectFault = async (machineId, fault) => {
    setInjecting(prev => ({ ...prev, [machineId]: true }));
    try {
      await fetch(`${API_BASE}/machines/${machineId}/fault`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ fault }),
      });
    } catch (_) {}
    setTimeout(() => setInjecting(prev => ({ ...prev, [machineId]: false })), 1500);
  };

  const clearFaults = async (machineId) => {
    try {
      await fetch(`${API_BASE}/machines/${machineId}/fault`, { method: 'DELETE' });
    } catch (_) {}
  };

  return (
    <div className="page-content" style={{ paddingBottom: '2rem' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.5rem' }}>
        <div>
          <h1 style={{ fontSize: '1.5rem', fontWeight: 800, marginBottom: '4px' }}>Machine Inventory</h1>
          <p style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
            Real-time status, OEE, health and reliability for all {machineList.length} machines.
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Sort by:</span>
          {['id', 'oee', 'power', 'wear'].map(s => (
            <button key={s} onClick={() => setSortBy(s)} style={{
              padding: '4px 10px', borderRadius: '6px', border: '1px solid var(--border-light)',
              background: sortBy === s ? 'rgba(0,229,255,0.12)' : 'transparent',
              color: sortBy === s ? 'var(--accent-primary)' : 'var(--text-muted)',
              cursor: 'pointer', fontSize: '0.75rem', fontWeight: 600, textTransform: 'uppercase'
            }}>{s}</button>
          ))}
        </div>
      </div>

      {/* Machine Cards Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '1rem' }}>
        {machineList.map(([id, m]) => {
          const machineOee = historicalOee?.machines?.[id];
          const faults = (m.alarm_codes || []).filter(f => f !== 'NONE');
          const healthScore = Math.round(100 - (m.health?.bearing_age_pct || 0));

          return (
            <div key={id} className="card" style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              {/* Card Header */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <span style={{ fontSize: '1.1rem', fontWeight: 800 }}>{id.toUpperCase()}</span>
                  <StateChip state={m.state} />
                  {faults.length > 0 && (
                    <span style={{ fontSize: '0.65rem', padding: '2px 6px', borderRadius: '4px',
                      background: 'rgba(239,68,68,0.15)', color: 'var(--alert-critical)', fontWeight: 700 }}>
                      ⚠ {faults.length} FAULT{faults.length > 1 ? 'S' : ''}
                    </span>
                  )}
                </div>
                <button onClick={() => { setSelectedMachine(id); setIsDrawerOpen(true); }}
                  style={{ padding: '4px 12px', borderRadius: '6px', border: '1px solid var(--border-light)',
                    background: 'rgba(0,229,255,0.08)', color: 'var(--accent-primary)',
                    cursor: 'pointer', fontSize: '0.75rem', fontWeight: 600 }}>
                  Details →
                </button>
              </div>

              {/* Metrics Row */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '0.5rem' }}>
                <div className="metric-tile">
                  <div className="metric-tile__label">OEE</div>
                  <div className="metric-tile__value" style={{ color: machineOee ? (machineOee.oee >= 65 ? 'var(--status-running)' : machineOee.oee >= 45 ? 'var(--status-idle)' : 'var(--alert-critical)') : 'var(--text-muted)' }}>
                    {machineOee ? `${machineOee.oee}%` : '—'}
                  </div>
                </div>
                <div className="metric-tile">
                  <div className="metric-tile__label">Power</div>
                  <div className="metric-tile__value">{(m.sensors?.energy?.power_kw || 0).toFixed(1)} <span className="metric-tile__unit">kW</span></div>
                </div>
                <div className="metric-tile">
                  <div className="metric-tile__label">Parts/Shift</div>
                  <div className="metric-tile__value">{m.production?.part_count_shift ?? '—'}</div>
                </div>
                <div className="metric-tile">
                  <div className="metric-tile__label">Health</div>
                  <div className="metric-tile__value" style={{ color: healthScore > 70 ? 'var(--status-running)' : healthScore > 40 ? 'var(--status-idle)' : 'var(--alert-critical)' }}>
                    {healthScore}%
                  </div>
                </div>
              </div>

              {/* OEE Breakdown (from TimescaleDB) */}
              {machineOee && (
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '0.5rem' }}>
                  {[['Availability', machineOee.availability, '--blue'], ['Performance', machineOee.performance, '--purple'], ['Quality', machineOee.quality, '--green']].map(([label, val, cls]) => (
                    <div key={label}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.7rem', marginBottom: '3px' }}>
                        <span style={{ color: 'var(--text-muted)' }}>{label}</span>
                        <span style={{ fontWeight: 600 }}>{val}%</span>
                      </div>
                      <div className="progress-bar">
                        <div className={`progress-bar__fill progress-bar__fill${cls}`} style={{ width: `${val}%` }} />
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Health Bars */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2px' }}>
                  <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Component Health</span>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '90px 1fr', gap: '4px 8px', alignItems: 'center' }}>
                  <span style={{ fontSize: '0.7rem', color: 'var(--text-secondary)' }}>Bearing</span>
                  <HealthBar value={m.health?.bearing_age_pct} reverse />
                  <span style={{ fontSize: '0.7rem', color: 'var(--text-secondary)' }}>Tool Wear</span>
                  <HealthBar value={m.health?.tool_wear_pct} />
                  <span style={{ fontSize: '0.7rem', color: 'var(--text-secondary)' }}>Coolant</span>
                  <HealthBar value={m.health?.coolant_health_pct} warn={40} crit={20} />
                </div>
              </div>

              {/* Live Sensor Row */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '0.5rem', paddingTop: '0.5rem', borderTop: '1px solid var(--border-light)' }}>
                <div style={{ fontSize: '0.7rem' }}>
                  <span style={{ color: 'var(--text-muted)' }}>Spindle RPM</span>
                  <div style={{ fontWeight: 700 }}>{(m.sensors?.rpm?.actual || 0).toFixed(0)}</div>
                </div>
                <div style={{ fontSize: '0.7rem' }}>
                  <span style={{ color: 'var(--text-muted)' }}>Motor Temp</span>
                  <div style={{ fontWeight: 700, color: (m.sensors?.temperature?.motor || 0) > 80 ? 'var(--alert-critical)' : 'inherit' }}>
                    {(m.sensors?.temperature?.motor || 0).toFixed(1)} °C
                  </div>
                </div>
                <div style={{ fontSize: '0.7rem' }}>
                  <span style={{ color: 'var(--text-muted)' }}>Vibration</span>
                  <div style={{ fontWeight: 700, color: ['C','D'].includes(m.sensors?.vibration?.iso_zone) ? 'var(--alert-critical)' : 'inherit' }}>
                    {(m.sensors?.vibration?.rms_mm_s || 0).toFixed(2)} mm/s
                  </div>
                </div>
              </div>

              {/* Fault controls */}
              {faults.length > 0 && (
                <div style={{ paddingTop: '0.5rem', borderTop: '1px solid rgba(239,68,68,0.2)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ fontSize: '0.7rem', color: 'var(--alert-critical)' }}>{faults.join(' • ')}</div>
                  <button onClick={() => clearFaults(id)} style={{ padding: '3px 10px', borderRadius: '6px', border: '1px solid rgba(239,68,68,0.4)',
                    background: 'rgba(239,68,68,0.1)', color: 'var(--alert-critical)', cursor: 'pointer', fontSize: '0.7rem', fontWeight: 600 }}>
                    Clear Faults
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
