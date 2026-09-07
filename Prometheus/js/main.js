// ============ 主入口：把所有模块组装起来 ============

import { TICK_SECONDS, tick, primeHistory, history } from './engine.js';
import { chartDefs } from './chart-defs.js';
import { renderLineChart } from './components/line-chart.js';
import { setupAllHoverTooltips } from './components/hover-tooltip.js';
import { setupInfoIconViewportClamp } from './components/info-tooltip.js';
import { renderStatCards } from './components/stat-cards.js';
import { setupScenarioSidebar } from './components/scenario-sidebar.js';
import { setupScenarioProgress, renderScenarioProgress } from './components/scenario-progress.js';
import { renderAllPanelNarrations } from './components/panel-narration.js';

function renderCharts() {
  Object.entries(chartDefs).forEach(([canvasId, def]) => {
    const series = def.seriesKeys.map((key) => history[key]);
    renderLineChart(canvasId, series, def.colors, { unit: def.unit });
  });
}

function render() {
  renderStatCards();
  renderCharts();
  renderScenarioProgress();
  renderAllPanelNarrations();
}

function updateClock() {
  document.getElementById('clock-text').textContent = new Date().toLocaleTimeString('zh-CN');
}

function onTick() {
  tick();
  render();
}

// ---- 启动 ----
primeHistory();
render();
setupScenarioSidebar();
setupScenarioProgress();
setupAllHoverTooltips();
setupInfoIconViewportClamp();
setInterval(onTick, TICK_SECONDS * 1000); // 模拟约 2 秒一次的"抓取周期"（真实 Prometheus 常见配置是 15s，这里加快方便观察）
setInterval(updateClock, 1000);
updateClock();
