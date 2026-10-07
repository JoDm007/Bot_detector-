/* ==========================================================================
   TELEGRAM BOT SENTINEL - CLIENT LOGIC & REALTIME CHARTS
   ========================================================================== */

let timelineChart = null;
let distributionChart = null;
let signalsChart = null;
let currentAnalyses = [];
let selectedAnalyse = null;
let ws = null;

// Initialisation au chargement de la page
document.addEventListener("DOMContentLoaded", () => {
  initCharts();
  loadData();
  setupWebSocket();

  document.getElementById("btn-refresh").addEventListener("click", () => {
    loadData();
    showToast("Données rafraîchies");
  });
});

/* ==========================================================================
   CHARTS INITIALIZATION (CHART.JS)
   ========================================================================== */
function initCharts() {
  const commonOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        labels: {
          color: "#94a3b8",
          font: { family: "Inter", size: 11 }
        }
      },
      tooltip: {
        backgroundColor: "rgba(10, 13, 20, 0.9)",
        titleColor: "#38bdf8",
        bodyColor: "#f1f5f9",
        borderColor: "rgba(56, 189, 248, 0.3)",
        borderWidth: 1,
        padding: 10,
        cornerRadius: 8
      }
    }
  };

  // 1. Timeline Chart (Line)
  const ctxTimeline = document.getElementById("timelineChart").getContext("2d");
  timelineChart = new Chart(ctxTimeline, {
    type: "line",
    data: {
      labels: [],
      datasets: [
        {
          label: "Automatisation (%)",
          data: [],
          borderColor: "#38bdf8",
          backgroundColor: "rgba(56, 189, 248, 0.15)",
          borderWidth: 2,
          tension: 0.3,
          fill: true,
          pointBackgroundColor: "#38bdf8"
        },
        {
          label: "Dangerosité (%)",
          data: [],
          borderColor: "#ef4444",
          backgroundColor: "rgba(239, 68, 68, 0.1)",
          borderWidth: 2,
          borderDash: [4, 4],
          tension: 0.3,
          fill: true,
          pointBackgroundColor: "#ef4444"
        }
      ]
    },
    options: {
      ...commonOptions,
      scales: {
        x: {
          grid: { color: "rgba(255, 255, 255, 0.04)" },
          ticks: { color: "#64748b", font: { family: "JetBrains Mono", size: 10 } }
        },
        y: {
          min: 0,
          max: 100,
          grid: { color: "rgba(255, 255, 255, 0.04)" },
          ticks: { color: "#64748b", font: { family: "JetBrains Mono", size: 10 } }
        }
      }
    }
  });

  // 2. Distribution Chart (Doughnut)
  const ctxDist = document.getElementById("distributionChart").getContext("2d");
  distributionChart = new Chart(ctxDist, {
    type: "doughnut",
    data: {
      labels: ["Bots (≥60%)", "Suspects (30-59%)", "Humains (<30%)"],
      datasets: [{
        data: [0, 0, 0],
        backgroundColor: ["#ef4444", "#f59e0b", "#10b981"],
        borderColor: "#0a0d14",
        borderWidth: 3,
        hoverOffset: 6
      }]
    },
    options: {
      ...commonOptions,
      cutout: "70%",
      plugins: {
        ...commonOptions.plugins,
        legend: { position: "bottom", labels: { color: "#94a3b8", font: { family: "Inter", size: 11 } } }
      }
    }
  });

  // 3. Signals Chart (Bar)
  const ctxSignals = document.getElementById("signalsChart").getContext("2d");
  signalsChart = new Chart(ctxSignals, {
    type: "bar",
    data: {
      labels: [],
      datasets: [{
        label: "Occurrences",
        data: [],
        backgroundColor: "rgba(168, 85, 247, 0.4)",
        borderColor: "#a855f7",
        borderWidth: 1.5,
        borderRadius: 6
      }]
    },
    options: {
      ...commonOptions,
      indexAxis: "y",
      plugins: {
        legend: { display: false },
        tooltip: commonOptions.plugins.tooltip
      },
      scales: {
        x: {
          grid: { color: "rgba(255, 255, 255, 0.04)" },
          ticks: { color: "#64748b", precision: 0 }
        },
        y: {
          grid: { display: false },
          ticks: { color: "#94a3b8", font: { size: 10 } }
        }
      }
    }
  });
}

/* ==========================================================================
   DATA LOADING & UPDATES
   ========================================================================== */
async function loadData() {
  try {
    const [statsRes, analysesRes] = await Promise.all([
      fetch("/api/stats"),
      fetch("/api/analyses?limit=50")
    ]);

    if (!statsRes.ok || !analysesRes.ok) return;

    const stats = await statsRes.json();
    const analyses = await analysesRes.json();

    updateKPIs(stats);
    updateCharts(stats);
    updateTable(analyses);

    // Si une sélection était en cours, mettre à jour le détail
    if (selectedAnalyse) {
      const updated = analyses.find(a => a.id === selectedAnalyse.id);
      if (updated) renderInspector(updated);
    } else if (analyses.length > 0) {
      renderInspector(analyses[0]);
    }

  } catch (err) {
    console.error("Erreur de chargement des données :", err);
  }
}

function updateKPIs(stats) {
  document.getElementById("kpi-total").innerText = stats.total_analyses;
  document.getElementById("kpi-bots").innerText = stats.total_bots;
  document.getElementById("kpi-suspects").innerText = stats.total_suspects;
  document.getElementById("kpi-humans").innerText = stats.total_humains;
}

function updateCharts(stats) {
  // 1. Timeline
  const labels = stats.timeline.map(t => t.nom);
  const autoData = stats.timeline.map(t => t.auto);
  const dangerData = stats.timeline.map(t => t.danger);

  timelineChart.data.labels = labels;
  timelineChart.data.datasets[0].data = autoData;
  timelineChart.data.datasets[1].data = dangerData;
  timelineChart.update();

  // 2. Distribution
  distributionChart.data.datasets[0].data = [
    stats.total_bots,
    stats.total_suspects,
    stats.total_humains
  ];
  distributionChart.update();

  // 3. Signals
  const signalLabels = stats.top_signaux.map(s => s.signal);
  const signalValues = stats.top_signaux.map(s => s.count);

  signalsChart.data.labels = signalLabels;
  signalsChart.data.datasets[0].data = signalValues;
  signalsChart.update();
}

function updateTable(analyses) {
  currentAnalyses = analyses;
  const tbody = document.getElementById("analyses-table-body");
  const countBadge = document.getElementById("table-count");
  countBadge.innerText = `${analyses.length} entrées`;

  if (analyses.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding: 2rem; color: var(--text-dim);">Aucune analyse enregistrée pour le moment.</td></tr>`;
    return;
  }

  tbody.innerHTML = analyses.map(a => {
    const isBot = a.score_automatisation >= 60;
    const isSuspect = a.score_automatisation >= 30 && a.score_automatisation < 60;
    const scoreClass = isBot ? "score-bot" : (isSuspect ? "score-suspect" : "score-human");
    const scoreIcon = isBot ? "🤖" : (isSuspect ? "⚠️" : "👤");

    const nom = a.first_name || a.username || "Sans Nom";
    const handle = a.username ? `@${a.username}` : "Sans @pseudo";
    const initial = (a.first_name || a.username || "?").charAt(0).toUpperCase();

    const dateStr = a.date_analyse ? new Date(a.date_analyse).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : "-";

    const retourLabel = a.retour_verdict 
      ? `<span style="font-weight:700; color:${a.retour_verdict==='bot'?'#f87171':'#34d399'}">${a.retour_verdict.toUpperCase()}</span>` 
      : `<span style="color:var(--text-dim); font-size:0.75rem;">- Non qualifié -</span>`;

    return `
      <tr class="row-item" onclick="onSelectRow(${a.id})">
        <td>
          <div class="user-cell">
            <div class="user-avatar-mini">${initial}</div>
            <div>
              <div class="user-meta-name">${nom}</div>
              <div class="user-meta-handle">${handle}</div>
            </div>
          </div>
        </td>
        <td style="font-family: var(--font-mono); color: var(--text-dim);">${a.chat_id}</td>
        <td>
          <span class="score-pill ${scoreClass}">${scoreIcon} ${a.score_automatisation}%</span>
        </td>
        <td>
          <span style="font-family: var(--font-mono); font-weight:600; color: ${a.score_danger > 0 ? '#ef4444' : '#64748b'}">
            ${a.score_danger}%
          </span>
        </td>
        <td style="color: var(--text-muted); font-size:0.8rem;">${dateStr}</td>
        <td>${retourLabel}</td>
      </tr>
    `;
  }).join("");
}

function onSelectRow(id) {
  const item = currentAnalyses.find(a => a.id === id);
  if (item) {
    renderInspector(item);
  }
}

/* ==========================================================================
   INSPECTOR VIEW
   ========================================================================== */
function renderInspector(item) {
  selectedAnalyse = item;
  const container = document.getElementById("inspector-container");
  const badge = document.getElementById("inspector-badge");
  
  badge.innerText = `ID #${item.id}`;

  const isBot = item.score_automatisation >= 60;
  const isSuspect = item.score_automatisation >= 30 && item.score_automatisation < 60;
  const levelText = isBot ? "ÉLEVÉ (BOT DÉCLARÉ/SUSPECT)" : (isSuspect ? "MOYEN (COMPORTEMENT MIXTE)" : "FAIBLE (HUMAIN PROBABLE)");
  const levelColor = isBot ? "var(--status-bot)" : (isSuspect ? "var(--status-suspect)" : "var(--status-human)");

  const nom = item.first_name || item.username || "Sans Nom";
  const handle = item.username ? `@${item.username}` : "Aucun identifiant";
  const initial = (item.first_name || item.username || "?").charAt(0).toUpperCase();

  // Signaux tags
  const autoSignals = (item.signaux_automatisation || []).map(s => `
    <div class="signal-tag">
      <i data-feather="check-circle" style="width: 12px; height: 12px; margin-right: 4px; color: var(--accent-cyan);"></i>
      ${s}
    </div>
  `).join("");

  const dangerSignals = (item.signaux_danger || []).map(s => `
    <div class="signal-tag danger">
      <i data-feather="alert-triangle" style="width: 12px; height: 12px; margin-right: 4px; color: #ef4444;"></i>
      ${s}
    </div>
  `).join("");

  container.innerHTML = `
    <div class="detail-content">
      <div class="detail-hero">
        <div class="detail-profile">
          <div class="detail-avatar-large">${initial}</div>
          <div>
            <h3 style="font-size:1.1rem; color:#fff;">${nom}</h3>
            <p style="color:var(--accent-cyan); font-family:var(--font-mono); font-size:0.85rem;">${handle}</p>
            <p style="color:var(--text-dim); font-size:0.75rem;">Telegram ID : ${item.chat_id}</p>
          </div>
        </div>
      </div>

      <div style="display: flex; gap: 1rem; align-items: center; justify-content: space-between; background: rgba(255,255,255,0.03); padding: 0.8rem 1rem; border-radius: var(--radius-sm); border: 1px solid var(--border-subtle);">
        <div>
          <div style="font-size:0.7rem; color:var(--text-muted); text-transform:uppercase;">Probabilité d'automatisation</div>
          <div style="font-size:1.6rem; font-weight:800; color:${levelColor}; font-family:var(--font-mono);">${item.score_automatisation}%</div>
        </div>
        <div style="text-align: right;">
          <div style="font-size:0.7rem; color:var(--text-muted); text-transform:uppercase;">Score de danger</div>
          <div style="font-size:1.6rem; font-weight:800; color:${item.score_danger > 0 ? '#ef4444' : '#64748b'}; font-family:var(--font-mono);">${item.score_danger}%</div>
        </div>
      </div>

      <div>
        <div style="font-size:0.8rem; font-weight:700; color:var(--text-muted); margin-bottom:0.5rem; text-transform:uppercase; letter-spacing:0.05em;">
          Signaux de profil & métadonnées :
        </div>
        <div class="signals-list">
          ${autoSignals || '<span style="color:var(--text-dim); font-size:0.8rem;">Aucun signal d\'anomalie détecté</span>'}
        </div>
      </div>

      ${item.signaux_danger && item.signaux_danger.length > 0 ? `
        <div>
          <div style="font-size:0.8rem; font-weight:700; color:#ef4444; margin-bottom:0.5rem; text-transform:uppercase; letter-spacing:0.05em;">
            Mots-clés & Signaux de danger :
          </div>
          <div class="signals-list">
            ${dangerSignals}
          </div>
        </div>
      ` : ''}

      <div class="detail-verdict-actions">
        <button class="btn-action btn-bot" onclick="submitVerdict(${item.id}, 'bot')">
          <i data-feather="slash" style="width:14px; height:14px;"></i> Valider Bot
        </button>
        <button class="btn-action btn-humain" onclick="submitVerdict(${item.id}, 'humain')">
          <i data-feather="check" style="width:14px; height:14px;"></i> Valider Humain
        </button>
      </div>
    </div>
  `;

  feather.replace();
}

/* ==========================================================================
   FEEDBACK SUBMISSION
   ========================================================================== */
async function submitVerdict(analyseId, verdict) {
  try {
    const res = await fetch("/api/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ analyse_id: analyseId, verdict: verdict })
    });

    if (res.ok) {
      showToast(`Vérité terrain enregistrée : ${verdict.toUpperCase()}`);
      loadData();
    } else {
      showToast("Erreur lors de l'enregistrement", true);
    }
  } catch (err) {
    console.error(err);
    showToast("Erreur de connexion", true);
  }
}

/* ==========================================================================
   WEBSOCKET REALTIME STREAM
   ========================================================================== */
function setupWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/ws`;

  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    document.getElementById("live-indicator").style.borderColor = "rgba(16, 185, 129, 0.4)";
    document.getElementById("live-text").innerText = "FLUX EN DIRECT ACTIF";
  };

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      if (msg.type === "new_analysis") {
        showToast(`⚡ Nouvelle analyse : ${msg.data.username || 'Compte #' + msg.data.chat_id} (${msg.data.score_automatisation}%)`);
        loadData();
      } else if (msg.type === "feedback_added") {
        loadData();
      }
    } catch (err) {
      console.error("WS Parse Error", err);
    }
  };

  ws.onclose = () => {
    document.getElementById("live-indicator").style.borderColor = "rgba(239, 68, 68, 0.4)";
    document.getElementById("live-text").innerText = "RECONNEXION DU FLUX...";
    setTimeout(setupWebSocket, 3000);
  };
}

/* ==========================================================================
   TOAST HELPER
   ========================================================================== */
function showToast(text, isError = false) {
  const container = document.getElementById("toast-container");
  const toast = document.createElement("div");
  toast.className = "toast";
  if (isError) toast.style.borderColor = "#ef4444";

  toast.innerHTML = `
    <i data-feather="${isError ? 'alert-circle' : 'bell'}" style="color:${isError ? '#ef4444' : 'var(--accent-cyan)'}; width:16px;"></i>
    <span>${text}</span>
  `;

  container.appendChild(toast);
  feather.replace();

  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateX(50px)";
    toast.style.transition = "all 0.3s ease";
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}
