// Dashboard Main Logic
document.addEventListener('DOMContentLoaded', () => {
    // Initialize empty charts for OEE
    initCharts();
    
    // Connect to Simulator WebSocket
    connectToSimulator();
});

let oeeDonutChart, prodDonutChart, utilBarChart, oeeTrendMini;

function initCharts() {
    // OEE Donut
    const ctxOee = document.getElementById('oee-donut').getContext('2d');
    oeeDonutChart = new Chart(ctxOee, {
        type: 'doughnut',
        data: {
            labels: ['OEE', 'Loss'],
            datasets: [{
                data: [67, 33],
                backgroundColor: ['#8b5cf6', 'rgba(255, 255, 255, 0.05)'],
                borderWidth: 0,
                cutout: '80%'
            }]
        },
        options: {
            responsive: false,
            plugins: { tooltip: { enabled: false }, legend: { display: false } }
        }
    });

    // Shift Target Donut
    const ctxProd = document.getElementById('prod-donut').getContext('2d');
    prodDonutChart = new Chart(ctxProd, {
        type: 'doughnut',
        data: {
            labels: ['Produced', 'Remaining'],
            datasets: [{
                data: [1450, 550],
                backgroundColor: ['#10b981', 'rgba(255, 255, 255, 0.05)'],
                borderWidth: 0,
                cutout: '80%'
            }]
        },
        options: {
            responsive: false,
            plugins: { tooltip: { enabled: false }, legend: { display: false } }
        }
    });
}

function connectToSimulator() {
    const ws = new WebSocket('ws://localhost:8000/ws/live');
    
    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        updateDashboard(data.machines);
    };

    ws.onclose = () => {
        setTimeout(connectToSimulator, 2000);
    };
}

function updateDashboard(machines) {
    let running = 0, idle = 0, down = 0;
    let totalPower = 0;
    let totalParts = 0;

    const grid = document.getElementById('machine-grid');
    grid.innerHTML = '';

    Object.entries(machines).forEach(([id, m]) => {
        if (!m) return;
        
        // Count statuses
        if (m.state === 'RUNNING') running++;
        else if (['IDLE', 'WARM_UP', 'COOLDOWN'].includes(m.state)) idle++;
        else down++;

        // Sum metrics
        if (m.sensors?.energy) totalPower += m.sensors.energy.power_kw;
        if (m.production) totalParts += m.production.part_count_shift;

        // Create Grid Card
        const statusClass = m.state === 'RUNNING' ? 'status-running' : (down ? 'status-down' : 'status-idle');
        const card = document.createElement('div');
        card.className = 'machine-card animate-fade-in';
        card.innerHTML = `
            <div class="machine-card__header">
                <span class="machine-card__name">${id.toUpperCase()}</span>
                <div class="machine-card__status ${statusClass}"></div>
            </div>
            <div style="font-size: 0.75rem; color: #94a3b8;">${m.state}</div>
            <div style="font-size: 1rem; font-weight: 600; margin-top: 8px;">${m.sensors?.energy?.power_kw.toFixed(1) || 0} kW</div>
            <div style="font-size: 0.75rem; color: #cbd5e1;">Parts: ${m.production?.part_count_shift || 0}</div>
        `;
        grid.appendChild(card);
    });

    // Update Top KPIs
    document.getElementById('stat-total').innerText = Object.keys(machines).length;
    document.getElementById('stat-running').innerText = running;
    document.getElementById('stat-idle').innerText = idle;
    document.getElementById('stat-down').innerText = down;

    // Update Energy
    document.getElementById('energy-power').innerText = totalPower.toFixed(1);
    
    // Update Production Target
    document.getElementById('shift-produced-row').innerText = totalParts;
    const target = 2000;
    const remaining = Math.max(0, target - totalParts);
    document.getElementById('shift-remaining').innerText = remaining;
    
    prodDonutChart.data.datasets[0].data = [totalParts, remaining];
    prodDonutChart.update();
}
