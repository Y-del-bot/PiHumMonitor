// PiHumMonitor 前端：轮询最新值 + 拉取历史区间绘制双轴折线图
const state = { range: "24h", chart: null };
const $ = (id) => document.getElementById(id);

async function fetchJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url} -> ${r.status}`);
  return r.json();
}

function fmtTime(iso) {
  if (!iso) return "--";
  return new Date(iso).toLocaleString("zh-CN", { hour12: false });
}

async function refreshLatest() {
  try {
    const d = await fetchJSON("/api/latest");
    $("temp").textContent = d.temperature.toFixed(1);
    $("hum").textContent = d.humidity.toFixed(1);
    $("updated").textContent = fmtTime(d.ts);
    $("status").textContent = "在线";
    $("status").className = "status ok";
  } catch (e) {
    $("status").textContent = "离线";
    $("status").className = "status err";
  }
}

async function refreshChart() {
  try {
    const data = await fetchJSON(`/api/readings?range=${state.range}&limit=5000`);
    const labels = data.map((r) =>
      new Date(r.ts).toLocaleTimeString("zh-CN", { hour12: false })
    );
    const temps = data.map((r) => r.temperature);
    const hums = data.map((r) => r.humidity);
    renderChart(labels, temps, hums);
  } catch (e) {
    console.error("chart load failed", e);
  }
}

function renderChart(labels, temps, hums) {
  const ctx = $("chart");
  if (state.chart) {
    state.chart.data.labels = labels;
    state.chart.data.datasets[0].data = temps;
    state.chart.data.datasets[1].data = hums;
    state.chart.update();
    return;
  }
  state.chart = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "温度 (°C)",
          data: temps,
          borderColor: "#e74c3c",
          backgroundColor: "rgba(231,76,60,0.10)",
          yAxisID: "y",
          tension: 0.3,
          pointRadius: 0,
          borderWidth: 2,
        },
        {
          label: "湿度 (%RH)",
          data: hums,
          borderColor: "#3498db",
          backgroundColor: "rgba(52,152,219,0.10)",
          yAxisID: "y1",
          tension: 0.3,
          pointRadius: 0,
          borderWidth: 2,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      scales: {
        x: { ticks: { maxRotation: 0, autoSkip: true } },
        y: { type: "linear", position: "left", title: { display: true, text: "温度 °C" } },
        y1: {
          type: "linear",
          position: "right",
          title: { display: true, text: "湿度 %RH" },
          grid: { drawOnChartArea: false },
        },
      },
      plugins: { legend: { position: "top" } },
    },
  });
}

document.querySelectorAll(".ranges button").forEach((b) => {
  b.addEventListener("click", () => {
    document.querySelectorAll(".ranges button").forEach((x) => x.classList.remove("active"));
    b.classList.add("active");
    state.range = b.dataset.range;
    refreshChart();
  });
});

refreshLatest();
refreshChart();
setInterval(refreshLatest, 30 * 1000);          // 每 30s 刷新当前值
setInterval(refreshChart, 5 * 60 * 1000);         // 每 5min 刷新图表
