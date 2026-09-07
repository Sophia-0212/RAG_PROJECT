// ============ 顶部统计卡片 + 基准线对比条组件 ============

import { state, derived, getStatusText } from '../engine.js';
import { evalBaseline, BASELINES } from '../baselines.js';

function renderBaselineCard(key, value, formatFn) {
  const { pct, status, baselinePct, gradient } = evalBaseline(key, value);
  const bar = document.getElementById('bar-' + key);
  const pointer = document.getElementById('pointer-' + key);
  const mark = document.getElementById('mark-' + key);
  const statusEl = document.getElementById('status-' + key);
  if (!pointer || !statusEl) return;
  if (bar) bar.style.background = gradient; // 按该指标真实的 warnAt/dangerAt 百分比画三色分段，不用 CSS 里写死的固定档位
  pointer.style.left = pct + '%';
  if (mark) mark.style.left = baselinePct + '%';
  const labels = { ok: '正常', warn: '告警', danger: '危险' };
  statusEl.textContent = labels[status] + (formatFn ? `（${formatFn(value)}）` : '');
  statusEl.className = 'baseline-status ' + status;
}

export function renderStatCards() {
  document.getElementById('stat-inflight').textContent = Math.round(derived.inflight);
  document.getElementById('stat-qps').textContent = (state.qpsSuccess + state.qpsRefused).toFixed(1);

  const total = state.qpsSuccess + state.qpsRefused;
  const successRate = total > 0 ? (state.qpsSuccess / total) * 100 : 100;
  const successEl = document.getElementById('stat-success');
  successEl.textContent = successRate.toFixed(1) + '%';
  successEl.className = 'value ' + (successRate >= BASELINES.success.warnAt ? 'green' : successRate >= BASELINES.success.dangerAt ? 'orange' : 'red');

  const p95El = document.getElementById('stat-p95');
  p95El.textContent = Math.round(derived.p95) + ' ms';
  p95El.className = 'value ' + (derived.p95 < BASELINES.p95.warnAt ? 'green' : derived.p95 < BASELINES.p95.dangerAt ? 'orange' : 'red');

  document.getElementById('stat-p95-delta').textContent = getStatusText();

  const avgEl = document.getElementById('stat-avg');
  avgEl.textContent = Math.round(derived.avg) + ' ms';
  avgEl.className = 'value ' + (derived.avg < BASELINES.avg.warnAt ? 'green' : derived.avg < BASELINES.avg.dangerAt ? 'orange' : 'red');

  renderBaselineCard('inflight', derived.inflight, (v) => `${v.toFixed(1)}/36`);
  renderBaselineCard('qps', state.qpsSuccess + state.qpsRefused, (v) => `${v.toFixed(1)} req/s`);
  renderBaselineCard('success', successRate, (v) => `${v.toFixed(1)}%`);
  renderBaselineCard('p95', derived.p95, (v) => `${(v / 1000).toFixed(2)}s`);
  renderBaselineCard('avg', derived.avg, (v) => `${(v / 1000).toFixed(2)}s`);
}
