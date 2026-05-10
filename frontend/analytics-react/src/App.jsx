import React, { useState, useEffect } from 'react';
import { LayoutDashboard, Server, Bell, BarChart2, MonitorPlay, Settings, Activity } from 'lucide-react';
import { Chart as ChartJS, ArcElement, Tooltip, Legend, CategoryScale, LinearScale, PointElement, LineElement, BarElement } from 'chart.js';
import { Doughnut, Line, Bar } from 'react-chartjs-2';
import Machines from './pages/Machines';
import Alerts from './pages/Alerts';
import Analytics from './pages/Analytics';

ChartJS.register(ArcElement, Tooltip, Legend, CategoryScale, LinearScale, PointElement, LineElement, BarElement);

const WS_URL = 'ws://localhost:8000/ws/live';

const API_BASE = 'http://localhost:8000';

function App() {
  const [machines, setMachines] = useState({});
  const [connected, setConnected] = useState(false);
  const [selectedMachine, setSelectedMachine] = useState(null);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [currentPage, setCurrentPage] = useState('dashboard');
  const [historicalOee, setHistoricalOee] = useState(null);
  const [plantTrend, setPlantTrend] = useState({ labels: [], data: [] });

  useEffect(() => {
    let ws;
    let reconnectTimer;

    const connect = () => {
      ws = new WebSocket(WS_URL);
      
      ws.onopen = () => setConnected(true);
      
      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.machines) {
          setMachines(data.machines);
        }
      };

      ws.onclose = () => {
        setConnected(false);
        reconnectTimer = setTimeout(connect, 2000);
      };
    };

    connect();
    return () => {
      clearTimeout(reconnectTimer);
      if (ws) ws.close();
    };
  }, []);

  // Poll /analytics/oee every 30s for TimescaleDB-backed KPIs
  useEffect(() => {
    const fetchOee = async () => {
      try {
        const res = await fetch(`${API_BASE}/analytics/oee?window_minutes=60`);
        if (res.ok) setHistoricalOee(await res.json());

        const res2 = await fetch(`${API_BASE}/analytics/trend?hours=24&bucket_minutes=60`);
        if (res2.ok) {
          const trends = await res2.json();
          const buckets = {};
          Object.values(trends).forEach(machineTrend => {
            machineTrend?.forEach(pt => {
              if (!buckets[pt.bucket]) buckets[pt.bucket] = { sum: 0, count: 0 };
              buckets[pt.bucket].sum += pt.oee;
              buckets[pt.bucket].count += 1;
            });
          });
          const sortedBuckets = Object.keys(buckets).sort();
          const labels = sortedBuckets.map(b => {
            const d = new Date(b);
            return `${d.getHours().toString().padStart(2,'0')}:${d.getMinutes().toString().padStart(2,'0')}`;
          });
          const data = sortedBuckets.map(b => Number((buckets[b].sum / buckets[b].count).toFixed(1)));
          setPlantTrend({ labels, data });
        }
      } catch (_) {}
    };
    fetchOee();
    const timer = setInterval(fetchOee, 30000);
    return () => clearInterval(timer);
  }, []);

  // Calculate Aggregates
  let running = 0, idle = 0, down = 0;
  let totalPower = 0, totalParts = 0;
  
  Object.values(machines).forEach(m => {
    if (!m) return;
    if (m.state === 'RUNNING') running++;
    else if (['IDLE', 'WARM_UP', 'COOLDOWN'].includes(m.state)) idle++;
    else down++;

    if (m.sensors?.energy) totalPower += m.sensors.energy.power_kw;
    if (m.production) totalParts += m.production.part_count_shift;
  });

  const totalMachines = Object.keys(machines).length;
  const runningPct = totalMachines ? Math.round((running / totalMachines) * 100) : 0;
  const idlePct = totalMachines ? Math.round((idle / totalMachines) * 100) : 0;
  
  // ── Real OEE Math from live WebSocket data ──────────────────────────────
  // Availability: fraction of machines currently RUNNING
  const availability = totalMachines > 0 ? (running / totalMachines) : 0;

  // Performance: average (actual_rpm / rated_rpm) across RUNNING machines
  let rpmSum = 0, rpmCount = 0;
  Object.values(machines).forEach(m => {
    if (m?.state === 'RUNNING') {
      const actual = m.sensors?.rpm?.actual || 0;
      const commanded = m.sensors?.rpm?.commanded || 3000;
      rpmSum += Math.min(1, actual / commanded);
      rpmCount++;
    }
  });
  const performance = rpmCount > 0 ? rpmSum / rpmCount : 0;

  // Quality: (parts - defects) / parts across all machines this shift
  let totalDefects = 0;
  Object.values(machines).forEach(m => {
    totalDefects += m?.production?.defect_count_shift || 0;
  });
  const quality = totalParts > 0 ? Math.max(0, (totalParts - totalDefects) / totalParts) : 1;

  // OEE = A × P × Q
  const oee = historicalOee?.plant?.oee ?? parseFloat((availability * performance * quality * 100).toFixed(1));
  const oeeAvail  = historicalOee?.plant?.availability ?? parseFloat((availability * 100).toFixed(1));
  const oeePerf   = historicalOee?.plant?.performance  ?? parseFloat((performance * 100).toFixed(1));
  const oeeQual   = historicalOee?.plant?.quality       ?? parseFloat((quality * 100).toFixed(1));

  const targetParts = 2000;
  const remainingParts = Math.max(0, targetParts - totalParts);
  const completionPct = Math.round((totalParts / targetParts) * 100);

  const donutOptions = {
    cutout: '80%',
    plugins: { tooltip: { enabled: false }, legend: { display: false } },
    maintainAspectRatio: false
  };

  const lineOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { display: false } },
    scales: { x: { display: false }, y: { display: false, min: 40, max: 100 } },
    elements: { line: { tension: 0.4, borderColor: '#8b5cf6', borderWidth: 2 }, point: { radius: 0 } }
  };

  const barOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { display: false } },
    scales: { x: { display: false }, y: { display: false } },
    elements: { bar: { borderRadius: 4 } }
  };

  // Real data for charts
  const mOee = historicalOee?.machines || {};
  const utilLabels = Object.keys(mOee).map(id => id.toUpperCase());
  const utilValues = Object.values(mOee).map(m => m.oee);
  const utilColors = utilValues.map(v => v >= 65 ? '#10b981' : v >= 45 ? '#f59e0b' : '#ef4444');
  
  const utilData = { 
    labels: utilLabels.length > 0 ? utilLabels : ['-'], 
    datasets: [{ 
      data: utilValues.length > 0 ? utilValues : [0], 
      backgroundColor: utilColors.length > 0 ? utilColors : ['#64748b'] 
    }] 
  };

  const trendData = {
    labels: plantTrend.labels.length > 0 ? plantTrend.labels : ['1','2','3','4','5','6','7'],
    datasets: [{ data: plantTrend.data.length > 0 ? plantTrend.data : [0, 0, 0, 0, 0, 0, 0] }]
  };

  // Aggregate active faults
  const activeFaults = [];
  Object.entries(machines).forEach(([id, m]) => {
    if (m?.alarm_codes) {
      m.alarm_codes.forEach(f => {
        if (f !== 'NONE') {
          activeFaults.push(`${id.toUpperCase()}: ${f}`);
        }
      });
    }
  });

  return (
    <div className="app-wrapper">
      {/* SIDEBAR */}
      <aside className="sidebar">
        <div className="sidebar__logo">N</div>
        <nav className="sidebar__nav">
          <a className={`sidebar__link ${currentPage === 'dashboard' ? 'active' : ''}`} onClick={() => setCurrentPage('dashboard')} title="Dashboard"><LayoutDashboard size={20} /></a>
          <a className={`sidebar__link ${currentPage === 'machines' ? 'active' : ''}`} onClick={() => setCurrentPage('machines')} title="Machines"><Server size={20} /></a>
          <a className={`sidebar__link ${currentPage === 'alerts' ? 'active' : ''}`} onClick={() => setCurrentPage('alerts')} title="Alerts"><Bell size={20} /></a>
          <a className={`sidebar__link ${currentPage === 'analytics' ? 'active' : ''}`} onClick={() => setCurrentPage('analytics')} title="Analytics"><BarChart2 size={20} /></a>
        </nav>
        <div className="sidebar__bottom">
          <a href="http://localhost:5173" className="sidebar__link" title="Open Simulator Control Panel"><MonitorPlay size={20} /></a>
          <a className="sidebar__link"><Settings size={20} /></a>
          <div className="sidebar__bottom-label" style={{ fontSize: '9px', color: '#94a3b8', writingMode: 'vertical-rl', transform: 'rotate(180deg)', marginTop: '1rem', letterSpacing: '2px' }}>
            Owner View
          </div>
        </div>
      </aside>

      {/* MAIN CONTENT */}
      <main className="main-content">
        <header className="header">
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '12px' }}>
            <span style={{ fontSize: '1.25rem', fontWeight: 800 }}>NeoLift 4.0</span>
            <span style={{ fontSize: '0.75rem', color: '#00e5ff', border: '1px solid #00e5ff', padding: '2px 6px', borderRadius: '4px' }}>V4.0</span>
            <span style={{ fontSize: '0.875rem', color: '#94a3b8', marginLeft: '12px', fontWeight: 600 }}>SHIFT A</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: connected ? '#10b981' : '#ef4444', boxShadow: connected ? '0 0 8px rgba(16,185,129,0.5)' : 'none' }}></div>
              <span style={{ fontSize: '0.75rem', color: connected ? '#10b981' : '#ef4444', fontWeight: 600 }}>{connected ? 'REAL-TIME' : 'OFFLINE'}</span>
            </div>
            <div style={{ width: '32px', height: '32px', borderRadius: '50%', background: '#1e293b', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.75rem', fontWeight: 700 }}>SP</div>
          </div>
        </header>

        {currentPage === 'dashboard' && (
          <div className="page-content">
            {/* KPI ROW */}
            <div className="stats-bar" style={{ marginBottom: '1rem' }}>
              <div className="stat-card" style={{ borderLeft: '3px solid var(--accent-primary)' }}>
                <div><div className="stat-card__label">Total Machines</div><div className="stat-card__value">{totalMachines}</div><div style={{ fontSize: '0.65rem', color: 'var(--text-muted)' }}>Plant floor</div></div>
              </div>
              <div className="stat-card" style={{ borderLeft: '3px solid var(--status-running)' }}>
                <div><div className="stat-card__label">Running</div><div className="stat-card__value" style={{ color: 'var(--status-running)' }}>{running}</div><div style={{ fontSize: '0.65rem', color: 'var(--status-running)' }}>{runningPct}% active</div></div>
              </div>
              <div className="stat-card" style={{ borderLeft: '3px solid var(--status-idle)' }}>
                <div><div className="stat-card__label">Idle / Warmup</div><div className="stat-card__value" style={{ color: 'var(--status-idle)' }}>{idle}</div><div style={{ fontSize: '0.65rem', color: 'var(--status-idle)' }}>{idlePct}% idle</div></div>
              </div>
              <div className="stat-card" style={{ borderLeft: '3px solid var(--status-down)' }}>
                <div><div className="stat-card__label">Down / Fault</div><div className="stat-card__value" style={{ color: 'var(--status-down)' }}>{down}</div><div style={{ fontSize: '0.65rem', color: 'var(--status-down)' }}>Needs attention</div></div>
              </div>
              <div className="stat-card" style={{ borderLeft: '3px solid var(--accent-violet)' }}>
                <div><div className="stat-card__label">Plant OEE</div><div className="stat-card__value" style={{ color: 'var(--accent-violet)' }}>{oee}%</div><div style={{ fontSize: '0.65rem', color: 'var(--status-running)' }}>↑ 2.1% vs yesterday</div></div>
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1.6fr', gap: '1rem', marginBottom: '1rem' }}>
              {/* OEE & ENERGY */}
              <div className="card">
                <div className="card__header">
                  <span className="card__title">OEE Summary</span>
                  <span className="badge--realtime">LIVE</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '1.5rem', marginBottom: '1.5rem' }}>
                  <div style={{ width: '90px', height: '90px', position: 'relative' }}>
                    <Doughnut data={{ labels: ['OEE', 'Loss'], datasets: [{ data: [oee, 100 - oee], backgroundColor: ['#8b5cf6', 'rgba(255,255,255,0.05)'], borderWidth: 0 }] }} options={donutOptions} />
                    <div style={{ position: 'absolute', top: '0', left: '0', right: '0', bottom: '0', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700 }}>{oee}%</div>
                  </div>
                  <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                    <div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem' }}><span style={{ color: 'var(--text-secondary)' }}>Availability</span><span style={{ fontWeight: 600 }}>{oeeAvail}%</span></div>
                      <div className="progress-bar"><div className="progress-bar__fill progress-bar__fill--blue" style={{ width: `${oeeAvail}%` }}></div></div>
                    </div>
                    <div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem' }}><span style={{ color: 'var(--text-secondary)' }}>Performance</span><span style={{ fontWeight: 600 }}>{oeePerf}%</span></div>
                      <div className="progress-bar"><div className="progress-bar__fill progress-bar__fill--purple" style={{ width: `${oeePerf}%` }}></div></div>
                    </div>
                    <div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem' }}><span style={{ color: 'var(--text-secondary)' }}>Quality</span><span style={{ fontWeight: 600 }}>{oeeQual}%</span></div>
                      <div className="progress-bar"><div className="progress-bar__fill progress-bar__fill--green" style={{ width: `${oeeQual}%` }}></div></div>
                    </div>
                  </div>
                </div>
                
                <div className="card__header" style={{ marginTop: '0.5rem' }}><span className="card__title" style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>⚡ Energy Usage</span></div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem' }}>
                  <div className="metric-tile">
                    <div className="metric-tile__label">Current Load</div>
                    <div className="metric-tile__value">{totalPower.toFixed(1)}<span className="metric-tile__unit"> kW</span></div>
                  </div>
                  <div className="metric-tile">
                    <div className="metric-tile__label">Est. Today</div>
                    <div className="metric-tile__value">186<span className="metric-tile__unit"> kWh</span></div>
                  </div>
                </div>
              </div>

              {/* SHIFT TARGET */}
              <div className="card">
                <div className="card__header"><span className="card__title">Shift Target</span></div>
                <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '1rem' }}>
                  <div style={{ width: '110px', height: '110px', position: 'relative' }}>
                    <Doughnut data={{ labels: ['Produced', 'Remaining'], datasets: [{ data: [totalParts, remainingParts], backgroundColor: ['#10b981', 'rgba(255,255,255,0.05)'], borderWidth: 0 }] }} options={donutOptions} />
                    <div style={{ position: 'absolute', top: '0', left: '0', right: '0', bottom: '0', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontSize: '1.25rem' }}>{completionPct}%</div>
                  </div>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem' }}><span style={{ color: 'var(--text-muted)' }}>Produced</span><span style={{ fontWeight: 600 }}>{totalParts}</span></div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem' }}><span style={{ color: 'var(--text-muted)' }}>Target</span><span style={{ fontWeight: 600 }}>{targetParts}</span></div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem' }}><span style={{ color: 'var(--text-muted)' }}>Remaining</span><span style={{ fontWeight: 600, color: 'var(--status-idle)' }}>{remainingParts}</span></div>
                </div>
              </div>

              {/* MACHINE FLOOR */}
              <div className="card" style={{ display: 'flex', flexDirection: 'column' }}>
                <div className="card__header"><span className="card__title">Machine Floor</span></div>
                <div className="machine-grid" style={{ flex: 1, overflowY: 'auto', alignContent: 'start' }}>
                  {Object.entries(machines).map(([id, m]) => {
                    if(!m) return null;
                    let statusClass = 'down';
                    if (m.state === 'RUNNING') statusClass = 'running';
                    else if (['IDLE', 'WARM_UP'].includes(m.state)) statusClass = 'idle';

                    return (
                      <div 
                        key={id} 
                        className="machine-mini-card"
                        style={{ cursor: 'pointer' }}
                        onClick={() => { setSelectedMachine(id); setIsDrawerOpen(true); }}
                      >
                        <div className="machine-mini-card__header">
                          <span style={{ fontSize: '0.75rem', fontWeight: 700, color: '#e2e8f0' }}>{id.toUpperCase()}</span>
                          <div className={`status-dot ${statusClass}`}></div>
                        </div>
                        <div style={{ fontSize: '0.65rem', color: '#94a3b8', marginBottom: '4px' }}>{m.state}</div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'end' }}>
                          <span style={{ fontSize: '0.875rem', fontWeight: 600 }}>{m.sensors?.energy?.power_kw.toFixed(1) || 0} kW</span>
                          <span style={{ fontSize: '0.65rem', color: '#cbd5e1' }}>P: {m.production?.part_count_shift || 0}</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>

            {/* BOTTOM ROW: Alerts + Utilisation + OEE Trend */}
            <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 1fr 1fr', gap: '1rem' }}>
              {/* ALERTS */}
              <div className="card">
                <div className="card__header">
                  <span className="card__title">Active Alerts</span>
                  <span style={{ fontSize: '0.65rem', padding: '2px 8px', borderRadius: '4px', background: 'var(--alert-critical-bg)', color: 'var(--alert-critical)', fontWeight: 600 }}>
                    {activeFaults.length} active
                  </span>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                  {activeFaults.length === 0 ? (
                    <div style={{ color: 'var(--status-running)', fontSize: '0.875rem' }}>✓ All systems nominal</div>
                  ) : (
                    activeFaults.map((fault, idx) => (
                      <div key={idx} style={{ padding: '0.5rem', background: 'rgba(239, 68, 68, 0.1)', borderLeft: '3px solid var(--alert-critical)', borderRadius: '4px', fontSize: '0.875rem' }}>
                        <span style={{ fontWeight: 700, marginRight: '8px' }}>⚠</span>
                        {fault}
                      </div>
                    ))
                  )}
                </div>
              </div>

              {/* UTILISATION */}
              <div className="card">
                <div className="card__header"><span className="card__title">Utilisation</span></div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', marginBottom: '1rem' }}>
                  {(() => {
                    const mOee = historicalOee?.machines || {};
                    const entries = Object.entries(mOee).sort((a,b) => b[1].oee - a[1].oee);
                    const highest = entries[0];
                    const lowest  = entries[entries.length - 1];
                    return (<>
                      <div className="metric-tile" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderColor: 'rgba(34,197,94,0.15)' }}>
                        <div><div className="metric-tile__label">Highest</div><div style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--status-running)' }}>{highest ? highest[0].toUpperCase() : '—'}</div></div>
                        <div style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--status-running)' }}>{highest ? highest[1].oee + '%' : '—'}</div>
                      </div>
                      <div className="metric-tile" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderColor: 'rgba(239,68,68,0.15)' }}>
                        <div><div className="metric-tile__label">Lowest</div><div style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--alert-critical)' }}>{lowest ? lowest[0].toUpperCase() : '—'}</div></div>
                        <div style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--alert-critical)' }}>{lowest ? lowest[1].oee + '%' : '—'}</div>
                      </div>
                    </>);
                  })()}
                </div>
                <div style={{ height: '120px' }}>
                  <Bar data={utilData} options={barOptions} />
                </div>
              </div>

              {/* OEE TREND 24H */}
              <div className="card">
                <div className="card__header"><span className="card__title">OEE Trend (24h)</span></div>
                <div style={{ height: '140px', marginBottom: '1rem' }}>
                  <Line data={trendData} options={lineOptions} />
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '0.5rem' }}>
                  <div className="metric-tile"><div className="metric-tile__label">Avg OEE</div><div style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--accent-violet)' }}>{historicalOee?.plant?.oee ?? '—'}%</div></div>
                  <div className="metric-tile"><div className="metric-tile__label">Avail</div><div style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--status-running)' }}>{historicalOee?.plant?.availability ?? '—'}%</div></div>
                  <div className="metric-tile"><div className="metric-tile__label">Quality</div><div style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--status-running)' }}>{historicalOee?.plant?.quality ?? '—'}%</div></div>
                </div>
              </div>
            </div>
          </div>
        )}

        {currentPage === 'machines' && (
          <Machines machines={machines} setSelectedMachine={setSelectedMachine} setIsDrawerOpen={setIsDrawerOpen} historicalOee={historicalOee} />
        )}

        {currentPage === 'alerts' && (
          <Alerts machines={machines} />
        )}

        {currentPage === 'analytics' && (
          <Analytics machines={machines} />
        )}

        {/* FAULT TICKER */}
        <div className="fault-ticker">
          <div className="fault-ticker__label"><div style={{ marginRight: '6px' }}>⚠</div>ACTIVE FAULTS:</div>
          <div className="fault-ticker__scroll">
            <div className="fault-ticker__track">
              {activeFaults.length > 0 ? activeFaults.join(' • ') : 'NO ACTIVE ALARMS ACROSS ALL ZONES'}
            </div>
          </div>
        </div>
      </main>

      {/* DRAWER OVERLAY */}
      {isDrawerOpen && (
        <div 
          className="drawer-overlay" 
          style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.5)', zIndex: 100 }}
          onClick={() => setIsDrawerOpen(false)}
        />
      )}

      {/* MACHINE DRAWER */}
      <div 
        className="drawer" 
        style={{ 
          position: 'fixed', top: 0, right: 0, bottom: 0, width: '400px', background: 'var(--bg-card-solid)', 
          borderLeft: '1px solid var(--border-light)', zIndex: 101, transform: isDrawerOpen ? 'translateX(0)' : 'translateX(100%)',
          transition: 'transform 0.3s ease-in-out', padding: '1.5rem', display: 'flex', flexDirection: 'column'
        }}
      >
        {selectedMachine && machines[selectedMachine] && (
          <>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
              <h2 style={{ fontSize: '1.5rem', fontWeight: 800 }}>{selectedMachine.toUpperCase()}</h2>
              <button onClick={() => setIsDrawerOpen(false)} style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: '1.5rem' }}>×</button>
            </div>
            
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', flex: 1, overflowY: 'auto' }}>
              <div className="card">
                <span className="card__title">Status</span>
                <div style={{ marginTop: '0.5rem', fontSize: '1.25rem', fontWeight: 700, color: machines[selectedMachine].state === 'RUNNING' ? 'var(--status-running)' : 'var(--status-idle)' }}>
                  {machines[selectedMachine].state}
                </div>
              </div>
              
              <div className="card">
                <span className="card__title">Live Telemetry</span>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginTop: '1rem' }}>
                  <div className="metric-tile">
                    <div className="metric-tile__label">Power</div>
                    <div className="metric-tile__value">{machines[selectedMachine].sensors?.energy?.power_kw.toFixed(1)} kW</div>
                  </div>
                  <div className="metric-tile">
                    <div className="metric-tile__label">Current</div>
                    <div className="metric-tile__value">{machines[selectedMachine].sensors?.energy?.current_a.toFixed(1)} A</div>
                  </div>
                  <div className="metric-tile">
                    <div className="metric-tile__label">Spindle</div>
                    <div className="metric-tile__value">{machines[selectedMachine].sensors?.rpm?.actual?.toFixed(0) ?? '—'} RPM</div>
                  </div>
                  <div className="metric-tile">
                    <div className="metric-tile__label">Motor Temp</div>
                    <div className="metric-tile__value">{machines[selectedMachine].sensors?.temperature?.motor?.toFixed(1) ?? '—'} °C</div>
                  </div>
                </div>
              </div>

              <div className="card">
                <span className="card__title">Production</span>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '1rem' }}>
                  <div><div className="metric-tile__label">Parts Shift</div><div className="metric-tile__value">{machines[selectedMachine].production?.part_count_shift}</div></div>
                  <div><div className="metric-tile__label">Defects</div><div className="metric-tile__value" style={{color: 'var(--alert-critical)'}}>{machines[selectedMachine].production?.defect_count_shift}</div></div>
                </div>
              </div>
            </div>
          </>
        )}
      </div>

    </div>
  );
}

export default App;
