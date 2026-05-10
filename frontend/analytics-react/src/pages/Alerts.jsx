import React, { useState, useEffect, useRef } from 'react';

const SEVERITY_MAP = {
  BEARING_FAILURE:    { level: 'CRITICAL', color: 'var(--alert-critical)',  bg: 'rgba(239,68,68,0.12)',   icon: '🔴' },
  TOOL_CHANGE_NEEDED: { level: 'WARNING',  color: 'var(--status-idle)',     bg: 'rgba(245,158,11,0.12)',  icon: '🟡' },
  COOLANT_FAILURE:    { level: 'CRITICAL', color: 'var(--alert-critical)',  bg: 'rgba(239,68,68,0.12)',   icon: '🔴' },
  ELECTRICAL_FAULT:   { level: 'CRITICAL', color: 'var(--alert-critical)',  bg: 'rgba(239,68,68,0.12)',   icon: '🔴' },
  OVERTEMP_MOTOR:     { level: 'WARNING',  color: 'var(--status-idle)',     bg: 'rgba(245,158,11,0.12)',  icon: '🟡' },
  VIBRATION_HIGH:     { level: 'WARNING',  color: 'var(--status-idle)',     bg: 'rgba(245,158,11,0.12)',  icon: '🟡' },
};

function getSeverity(code) {
  return SEVERITY_MAP[code] || { level: 'INFO', color: 'var(--accent-primary)', bg: 'rgba(0,229,255,0.08)', icon: '🔵' };
}

function timeAgo(ts) {
  const diff = Math.floor((Date.now() - new Date(ts).getTime()) / 1000);
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff/60)}m ago`;
  return `${Math.floor(diff/3600)}h ago`;
}

export default function Alerts({ machines }) {
  const [alertLog, setAlertLog] = useState([]);
  const [filter, setFilter] = useState('ALL');
  const logRef = useRef(null);

  // Build live active faults from WS payload
  const activeFaults = [];
  Object.entries(machines).forEach(([id, m]) => {
    if (m?.alarm_codes) {
      m.alarm_codes.forEach(f => {
        if (f !== 'NONE') activeFaults.push({ id, fault: f, ...getSeverity(f), ts: new Date().toISOString() });
      });
    }
  });

  // Accumulate historical log (new faults get appended with timestamp)
  const prevFaults = useRef({});
  useEffect(() => {
    const now = new Date().toISOString();
    activeFaults.forEach(({ id, fault }) => {
      const key = `${id}:${fault}`;
      if (!prevFaults.current[key]) {
        prevFaults.current[key] = true;
        setAlertLog(prev => [{ id, fault, ts: now, ...getSeverity(fault) }, ...prev].slice(0, 100));
      }
    });
    // Remove cleared faults from tracking
    Object.keys(prevFaults.current).forEach(key => {
      const [id, fault] = key.split(':');
      if (!activeFaults.find(f => f.id === id && f.fault === fault)) {
        delete prevFaults.current[key];
      }
    });
  });

  const counts = { CRITICAL: 0, WARNING: 0, INFO: 0 };
  activeFaults.forEach(f => { counts[f.level] = (counts[f.level] || 0) + 1; });

  const filteredLog = filter === 'ALL' ? alertLog : alertLog.filter(a => a.level === filter);

  return (
    <div className="page-content" style={{ paddingBottom: '2rem' }}>
      {/* Header */}
      <div style={{ marginBottom: '1.5rem' }}>
        <h1 style={{ fontSize: '1.5rem', fontWeight: 800, marginBottom: '4px' }}>System Alerts</h1>
        <p style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
          Real-time monitoring of machine criticalities and threshold violations.
        </p>
      </div>

      {/* Summary KPI Row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1rem', marginBottom: '1.5rem' }}>
        {[
          { label: 'Active Faults',  value: activeFaults.length, color: activeFaults.length > 0 ? 'var(--alert-critical)' : 'var(--status-running)', pulse: activeFaults.length > 0 },
          { label: 'Critical',       value: counts.CRITICAL,     color: 'var(--alert-critical)' },
          { label: 'Warnings',       value: counts.WARNING,      color: 'var(--status-idle)' },
          { label: 'Total in Log',   value: alertLog.length,     color: 'var(--text-secondary)' },
        ].map(({ label, value, color, pulse }) => (
          <div key={label} className="card" style={{ padding: '1rem 1.25rem' }}>
            <div style={{ fontSize: '0.7rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--text-muted)', marginBottom: '6px' }}>
              {label}
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontSize: '2rem', fontWeight: 900, color }}>{value}</span>
              {pulse && value > 0 && (
                <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: color, boxShadow: `0 0 8px ${color}`, animation: 'pulse-green 1.5s infinite' }} />
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Active Faults Banner */}
      {activeFaults.length === 0 ? (
        <div className="card" style={{ textAlign: 'center', padding: '2rem', color: 'var(--status-running)', marginBottom: '1.5rem', border: '1px solid rgba(16,185,129,0.2)' }}>
          <div style={{ fontSize: '1.5rem', marginBottom: '8px' }}>✓</div>
          <div style={{ fontWeight: 700 }}>All Systems Nominal</div>
          <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginTop: '4px' }}>No active alarms across all zones.</div>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', marginBottom: '1.5rem' }}>
          <div style={{ fontSize: '0.75rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--text-muted)' }}>
            🔴 Active Now
          </div>
          {activeFaults.map((a, idx) => (
            <div key={idx} className="card" style={{ borderLeft: `4px solid ${a.color}`, background: a.bg, padding: '1rem 1.25rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  <span style={{ fontSize: '1.25rem' }}>{a.icon}</span>
                  <div>
                    <div style={{ fontWeight: 800, fontSize: '0.9rem' }}>{a.id.toUpperCase()}</div>
                    <div style={{ color: a.color, fontWeight: 600, fontSize: '0.8rem', marginTop: '2px' }}>{a.fault.replace(/_/g, ' ')}</div>
                  </div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontSize: '0.65rem', padding: '2px 8px', borderRadius: '999px', background: a.bg, color: a.color, fontWeight: 700, border: `1px solid ${a.color}`, marginBottom: '4px' }}>
                    {a.level}
                  </div>
                  <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>LIVE</div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Alert Log */}
      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <span style={{ fontWeight: 700, fontSize: '0.875rem', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Alert Log</span>
          <div style={{ display: 'flex', gap: '6px' }}>
            {['ALL', 'CRITICAL', 'WARNING', 'INFO'].map(f => (
              <button key={f} onClick={() => setFilter(f)} style={{
                padding: '3px 10px', borderRadius: '6px', border: '1px solid var(--border-light)',
                background: filter === f ? 'rgba(0,229,255,0.1)' : 'transparent',
                color: filter === f ? 'var(--accent-primary)' : 'var(--text-muted)',
                cursor: 'pointer', fontSize: '0.7rem', fontWeight: 600,
              }}>{f}</button>
            ))}
          </div>
        </div>

        <div ref={logRef} style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', maxHeight: '360px', overflowY: 'auto' }}>
          {filteredLog.length === 0 ? (
            <div style={{ textAlign: 'center', color: 'var(--text-muted)', padding: '2rem', fontSize: '0.875rem' }}>
              No alerts recorded yet. Log fills as faults occur.
            </div>
          ) : (
            filteredLog.map((a, idx) => (
              <div key={idx} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                padding: '0.6rem 0.875rem', borderRadius: '8px', background: 'rgba(255,255,255,0.02)',
                border: '1px solid var(--border-light)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <span>{a.icon}</span>
                  <div>
                    <span style={{ fontWeight: 700, fontSize: '0.8rem' }}>{a.id.toUpperCase()}</span>
                    <span style={{ margin: '0 6px', color: 'var(--text-muted)', fontSize: '0.7rem' }}>›</span>
                    <span style={{ fontSize: '0.8rem', color: a.color }}>{a.fault.replace(/_/g, ' ')}</span>
                  </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span style={{ fontSize: '0.65rem', padding: '2px 6px', borderRadius: '4px', background: a.bg, color: a.color, fontWeight: 600 }}>
                    {a.level}
                  </span>
                  <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>{timeAgo(a.ts)}</span>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
