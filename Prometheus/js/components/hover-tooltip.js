// ============ 图表 hover：横纵坐标数据披露组件 ============
// 模拟 ECharts 的 tooltip + 十字辅助线：鼠标移到图表上，展示该时刻每条曲线的具体数值。

import { MAX_POINTS, TICK_SECONDS, history } from '../engine.js';
import { chartGeometry } from './line-chart.js';
import { chartDefs } from '../chart-defs.js';
import { clamp, formatRelativeTime } from '../utils.js';

export function setupHoverTooltip(canvasId) {
  const canvas = document.getElementById(canvasId);
  const tooltip = document.getElementById('tooltip-' + canvasId);
  const crosshair = document.getElementById('crosshair-' + canvasId);
  const def = chartDefs[canvasId];

  canvas.addEventListener('mousemove', (evt) => {
    const geo = chartGeometry[canvasId];
    if (!geo || geo.seriesLength < 2) return;
    const rect = canvas.getBoundingClientRect();
    const mouseX = evt.clientX - rect.left;

    const pointIndex = clamp(Math.round((mouseX / rect.width) * (MAX_POINTS - 1)), 0, geo.seriesLength - 1);
    const xPos = (pointIndex / (MAX_POINTS - 1)) * rect.width;

    crosshair.style.display = 'block';
    crosshair.style.left = xPos + 'px';

    const timeLabel = formatRelativeTime(pointIndex, geo.seriesLength, TICK_SECONDS);
    let html = `<div class="t-time">${timeLabel}</div>`;
    def.seriesKeys.forEach((key, i) => {
      const val = history[key][pointIndex];
      if (val === undefined) return;
      html += `<div class="t-row"><span class="t-dot" style="background:${def.colors[i]}"></span>${def.labels[i]}: <b>${def.format(val)}</b></div>`;
    });
    tooltip.innerHTML = html;
    tooltip.style.display = 'block';

    let tipLeft = xPos + 12;
    const tipWidth = 180;
    if (tipLeft + tipWidth > rect.width) tipLeft = xPos - tipWidth - 12;
    tooltip.style.left = tipLeft + 'px';
    tooltip.style.top = '6px';
  });

  canvas.addEventListener('mouseleave', () => {
    tooltip.style.display = 'none';
    crosshair.style.display = 'none';
  });
}

export function setupAllHoverTooltips() {
  Object.keys(chartDefs).forEach(setupHoverTooltip);
}
