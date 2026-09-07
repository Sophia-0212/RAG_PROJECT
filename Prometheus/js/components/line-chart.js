// ============ Canvas 折线图渲染组件 ============
// 每张图表只需要调用 renderLineChart(canvasId, series, colors, opts)。
// 渲染结果的几何信息存进 chartGeometry，供 hover-tooltip.js 复用（避免重复计算坐标换算）。

import { MAX_POINTS } from '../engine.js';

export const chartGeometry = {};

export function renderLineChart(canvasId, series, colors, opts) {
  const canvas = document.getElementById(canvasId);
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth || 400;
  const h = canvas.clientHeight || 160;
  canvas.width = w * dpr;
  canvas.height = h * dpr;
  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, w, h);

  const allValues = series.flat().filter((v) => typeof v === 'number');
  const maxVal = opts && opts.max !== undefined ? opts.max : Math.max(1, ...allValues) * 1.15;
  const minVal = opts && opts.min !== undefined ? opts.min : 0;

  // 网格线 + 纵轴刻度数值（Y 轴披露）
  ctx.strokeStyle = '#21262d';
  ctx.lineWidth = 1;
  ctx.fillStyle = '#6e7681';
  ctx.font = '10px Consolas, monospace';
  for (let i = 0; i <= 4; i++) {
    const y = h * (i / 4);
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(w, y);
    ctx.stroke();
    const val = maxVal - (maxVal - minVal) * (i / 4);
    const label = opts && opts.unit === 'ms' ? Math.round(val) : val.toFixed(1);
    ctx.fillText(label, 4, y > 10 ? y - 4 : y + 12);
  }

  series.forEach((s, idx) => {
    if (s.length < 2) return;
    ctx.strokeStyle = colors[idx];
    ctx.lineWidth = 1.8;
    ctx.beginPath();
    s.forEach((v, i) => {
      const x = (i / (MAX_POINTS - 1)) * w;
      const y = h - ((v - minVal) / (maxVal - minVal || 1)) * h;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();

    // 面积填充（淡）
    ctx.globalAlpha = 0.08;
    ctx.fillStyle = colors[idx];
    ctx.lineTo(w, h);
    ctx.lineTo(0, h);
    ctx.closePath();
    ctx.fill();
    ctx.globalAlpha = 1;
  });

  chartGeometry[canvasId] = { w, h, minVal, maxVal, seriesLength: series[0] ? series[0].length : 0 };
}
