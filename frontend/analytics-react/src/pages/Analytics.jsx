import React, { useState, useEffect } from 'react';
import {
  Chart as ChartJS, CategoryScale, LinearScale, PointElement,
  LineElement, BarElement, Filler, Tooltip, Legend
} from 'chart.js';
import { Line, Bar } from 'react-chartjs-2';

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, BarElement, Filler, Tooltip, Legend);

const API_BASE = 'http://localhost:8000';

function fmt(val, decimals = 1) {
  const n = parseFloat(val);
  return isNaN(n) ? '—' : n.toFixed(decimals);
}

const MACHINE_COLORS = {
  'cnc-001':   '#00e5ff',
  'lathe-001': '#8b5cf6',
  'mill-001':  '#10b981',
  'drill-001': '#f59e0b',
};

function useAnalyticsData(hours, bucketMinutes) {
  const [trendAll, setTrendAll]   = useState({});
  const [power, setPower]         = useState([]);
  const [oeeSum, setOeeSum]       = useState(null);
  const [loading, setLoading]     = useState(true);

  useEffect(() => {
    let cancelled = false;
    const fetch_ = async () => {
      setLoading(true);
      try {
        const [tRes, pRes, oRes] = await Promise.all([
          fetch(`${API_BASE}/analytics/trend?hours=${hours}&bucket_minutes=${bucketMinutes}`),
          fetch(`${API_BASE}/analytics/power?hours=${hours}&bucket_minutes=${bucketMinutes}`),
          fetch(`${API_BASE}/analytics/oee?window_minutes=${hours * 60}`),
        ]);
        if (!cancelled) {
          if (tRes.ok) setTrendAll(await tRes.json());
          if (pRes.ok) setPower((await pRes.json()).trend || []);
          if (oRes.ok) setOeeSum(await oRes.json());
        }
      } catch (_) {}
      if (!cancelled) setLoading(false);
    };
    fetch_();
    const timer = setInterval(fetch_, 60000);
    return () => { cancelled = true; clearInterval(timer); };
  }, [hours, bucketMinutes]);

  return { trendAll, power, oeeSum, loading };
}

export default function Analytics({ machines }) {
  const [hours, setHours] = useState(8);
  const [bucketMin, setBucketMin] = useState(15);
  const [selectedMachine, setSelectedMachine] = useState('all');

  const { trendAll, power, oeeSum, loading } = useAnalyticsData(hours, bucketMin);

  // Build OEE trend datasets for the line chart
  const machineIds = Object.keys(machines);
  const allBuckets = new Set();
  Object.values(trendAll).forEach(trend => trend?.forEach(p => allBuckets.add(p.bucket)));
  const sortedBuckets = [...allBuckets].sort();
  const bucketLabels = sortedBuckets.map(b => {
    const d = new Date(b);
    return `${d.getHours().toString().padStart(2,'0')}:${d.getMinutes().toString().padStart(2,'0')}`;
  });

  const oeeLineData = {
    labels: bucketLabels,
    datasets: selectedMachine === 'all'
      ? machineIds.map(id => ({
          label: id.toUpperCase(),
          data: sortedBuckets.map(b => {
            const pt = trendAll[id]?.find(p => p.bucket === b);
            return pt ? pt.oee : null;
          }),
          borderColor: MACHINE_COLORS[id] || '#64748b',
          backgroundColor: 'transparent',
          borderWidth: 2,
          tension: 0.4,
          spanGaps: true,
          pointRadius: 0,
        }))
      : [{
          label: selectedMachine.toUpperCase(),
          data: sortedBuckets.map(b => {
            const pt = trendAll[selectedMachine]?.find(p => p.bucket === b);
            return pt ? pt.oee : null;
          }),
          borderColor: MACHINE_COLORS[selectedMachine] || '#00e5ff',
          backgroundColor: `${MACHINE_COLORS[selectedMachine] || '#00e5ff'}20`,
          fill: true,
          borderWidth: 2,
          tension: 0.4,
          spanGaps: true,
          pointRadius: 0,
        }],
  };

  // Power trend stacked bar
  const powerBarData = {
    labels: power.map(p => {
      const d = new Date(p.bucket);
      return `${d.getHours().toString().padStart(2,'0')}:${d.getMinutes().toString().padStart(2,'0')}`;
    }),
    datasets: machineIds.map(id => ({
      label: id.toUpperCase(),
      data: power.map(p => p.by_machine?.[id] || 0),
      backgroundColor: `${MACHINE_COLORS[id] || '#64748b'}bb`,
      borderRadius: 3,
      stack: 'power',
    })),
  };

  // Per-machine OEE bar from summary
  const oeeBarData = {
    labels: Object.keys(oeeSum?.machines || {}).map(id => id.toUpperCase()),
    datasets: [
      {
        label: 'OEE %',
        data: Object.values(oeeSum?.machines || {}).map(m => m.oee),
        backgroundColor: Object.keys(oeeSum?.machines || {}).map(id => MACHINE_COLORS[id] || '#64748b'),
        borderRadius: 6,
      },
    ],
  };

  const lineOpts = {
    responsive: true, maintainAspectRatio: false,
    plugins: { legend: { position: 'bottom', labels: { color: '#94a3b8', font: { size: 11 } } }, tooltip: { mode: 'index', intersect: false } },
    scales: {
      x: { ticks: { color: '#64748b', font: { size: 10 }, maxRotation: 0 }, grid: { color: 'rgba(255,255,255,0.04)' } },
      y: { min: 0, max: 100, ticks: { color: '#64748b', font: { size: 10 }, callback: v => v + '%' }, grid: { color: 'rgba(255,255,255,0.04)' } },
    },
  };

  const powerOpts = {
    responsive: true, maintainAspectRatio: false,
    plugins: { legend: { position: 'bottom', labels: { color: '#94a3b8', font: { size: 11 } } } },
    scales: {
      x: { stacked: true, ticks: { color: '#64748b', font: { size: 10 } }, grid: { display: false } },
      y: { stacked: true, ticks: { color: '#64748b', font: { size: 10 }, callback: v => v + ' kW' }, grid: { color: 'rgba(255,255,255,0.04)' } },
    },
  };

  const barOpts = {
    responsive: true, maintainAspectRatio: false,
    plugins: { legend: { display: false } },
    scales: {
      x: { ticks: { color: '#94a3b8' }, grid: { display: false } },
      y: { min: 0, max: 100, ticks: { color: '#64748b', callback: v => v + '%' }, grid: { color: 'rgba(255,255,255,0.04)' } },
    },
  };

  return (
    <div className="page-content" style={{ paddingBottom: '2rem' }}>
      {/* Header + Controls */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.5rem' }}>
        <div>
          <h1 style={{ fontSize: '1.5rem', fontWeight: 800, marginBottom: '4px' }}>Analytics & History</h1>
          <p style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
            OEE trends, energy profiles and reliability metrics — powered by TimescaleDB.
            {loading && <span style={{ color: 'var(--accent-primary)', marginLeft: '8px' }}>⟳ loading…</span>}
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Window:</span>
          {[
            { label: '2h',  h: 2,  b: 5  },
            { label: '8h',  h: 8,  b: 15 },
            { label: '24h', h: 24, b: 30 },
          ].map(({ label, h, b }) => (
            <button key={label} onClick={() => { setHours(h); setBucketMin(b); }} style={{
              padding: '4px 10px', borderRadius: '6px', border: '1px solid var(--border-light)',
              background: hours === h ? 'rgba(0,229,255,0.12)' : 'transparent',
              color: hours === h ? 'var(--accent-primary)' : 'var(--text-muted)',
              cursor: 'pointer', fontSize: '0.75rem', fontWeight: 600,
            }}>{label}</button>
          ))}
        </div>
      </div>

      {/* Plant-level OEE Summary KPIs */}
      {oeeSum?.plant && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1rem', marginBottom: '1.5rem' }}>
          {[
            { label: 'Plant OEE',    value: oeeSum.plant.oee + '%',          color: '#8b5cf6' },
            { label: 'Availability', value: oeeSum.plant.availability + '%',  color: '#3b82f6' },
            { label: 'Performance',  value: oeeSum.plant.performance + '%',   color: '#a78bfa' },
            { label: 'Quality',      value: oeeSum.plant.quality + '%',       color: '#10b981' },
          ].map(({ label, value, color }) => (
            <div key={label} className="card" style={{ padding: '1rem 1.25rem' }}>
              <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: '4px' }}>{label}</div>
              <div style={{ fontSize: '1.75rem', fontWeight: 900, color }}>{value}</div>
              <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', marginTop: '2px' }}>Last {hours}h avg</div>
            </div>
          ))}
        </div>
      )}

      {/* OEE Trend Line Chart */}
      <div className="card" style={{ marginBottom: '1rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <span style={{ fontWeight: 700, fontSize: '0.875rem', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
            OEE % Trend — Last {hours}h
          </span>
          <div style={{ display: 'flex', gap: '6px' }}>
            <button onClick={() => setSelectedMachine('all')} style={{
              padding: '3px 10px', borderRadius: '6px', border: '1px solid var(--border-light)',
              background: selectedMachine === 'all' ? 'rgba(0,229,255,0.1)' : 'transparent',
              color: selectedMachine === 'all' ? 'var(--accent-primary)' : 'var(--text-muted)',
              cursor: 'pointer', fontSize: '0.7rem', fontWeight: 600,
            }}>All</button>
            {machineIds.map(id => (
              <button key={id} onClick={() => setSelectedMachine(id)} style={{
                padding: '3px 10px', borderRadius: '6px', border: `1px solid ${MACHINE_COLORS[id] || '#64748b'}40`,
                background: selectedMachine === id ? `${MACHINE_COLORS[id] || '#64748b'}20` : 'transparent',
                color: selectedMachine === id ? MACHINE_COLORS[id] : 'var(--text-muted)',
                cursor: 'pointer', fontSize: '0.7rem', fontWeight: 600,
              }}>{id.split('-')[0].toUpperCase()}</button>
            ))}
          </div>
        </div>
        <div style={{ height: '260px' }}>
          {bucketLabels.length > 0
            ? <Line data={oeeLineData} options={lineOpts} />
            : <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-muted)', fontSize: '0.875rem' }}>
                No historical data yet — let the simulator run for a few minutes.
              </div>
          }
        </div>
      </div>

      {/* Bottom 2-col */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
        {/* Power Profile */}
        <div className="card">
          <div style={{ fontWeight: 700, fontSize: '0.875rem', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: '1rem' }}>
            Plant Power Load — Last {hours}h
          </div>
          <div style={{ height: '220px' }}>
            {power.length > 0
              ? <Bar data={powerBarData} options={powerOpts} />
              : <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-muted)', fontSize: '0.875rem' }}>
                  No power data yet.
                </div>
            }
          </div>
        </div>

        {/* Per-machine OEE bar */}
        <div className="card">
          <div style={{ fontWeight: 700, fontSize: '0.875rem', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: '1rem' }}>
            OEE by Machine — Last {hours}h
          </div>
          <div style={{ height: '180px', marginBottom: '1rem' }}>
            {Object.keys(oeeSum?.machines || {}).length > 0
              ? <Bar data={oeeBarData} options={barOpts} />
              : <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-muted)', fontSize: '0.875rem' }}>
                  No data yet.
                </div>
            }
          </div>
          {/* Machine OEE table */}
          {oeeSum?.machines && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', borderTop: '1px solid var(--border-light)', paddingTop: '0.75rem' }}>
              {Object.entries(oeeSum.machines).map(([id, m]) => (
                <div key={id} style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.75rem' }}>
                  <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: MACHINE_COLORS[id] || '#64748b', flexShrink: 0 }} />
                  <span style={{ width: '90px', fontWeight: 600 }}>{id.toUpperCase()}</span>
                  <div style={{ flex: 1, height: '4px', background: 'rgba(255,255,255,0.06)', borderRadius: '999px', overflow: 'hidden' }}>
                    <div style={{ width: `${m.oee}%`, height: '100%', background: MACHINE_COLORS[id] || '#64748b', borderRadius: '999px' }} />
                  </div>
                  <span style={{ width: '38px', textAlign: 'right', fontWeight: 700, color: MACHINE_COLORS[id] || '#64748b' }}>{m.oee}%</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Parts & Defects table */}
      {oeeSum?.machines && (
        <div className="card">
          <div style={{ fontWeight: 700, fontSize: '0.875rem', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: '1rem' }}>
            Production Summary — Last {hours}h
          </div>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem' }}>
            <thead>
              <tr style={{ color: 'var(--text-muted)', textAlign: 'left', borderBottom: '1px solid var(--border-light)' }}>
                {['Machine', 'Parts', 'Defects', 'Quality %', 'Avg Power kW', 'Availability', 'Performance'].map(h => (
                  <th key={h} style={{ padding: '6px 10px', fontWeight: 600, fontSize: '0.7rem', textTransform: 'uppercase' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {Object.entries(oeeSum.machines).map(([id, m]) => (
                <tr key={id} style={{ borderBottom: '1px solid rgba(255,255,255,0.03)' }}>
                  <td style={{ padding: '8px 10px', fontWeight: 700, color: MACHINE_COLORS[id] }}>{id.toUpperCase()}</td>
                  <td style={{ padding: '8px 10px' }}>{m.parts_produced}</td>
                  <td style={{ padding: '8px 10px', color: m.defects > 0 ? 'var(--alert-critical)' : 'var(--status-running)' }}>{m.defects}</td>
                  <td style={{ padding: '8px 10px' }}>{m.quality}%</td>
                  <td style={{ padding: '8px 10px' }}>{fmt(m.avg_power_kw)}</td>
                  <td style={{ padding: '8px 10px' }}>{m.availability}%</td>
                  <td style={{ padding: '8px 10px' }}>{m.performance}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
