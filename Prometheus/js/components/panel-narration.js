// ============ 图表面板浮动因果说明组件 ============
// 每张图表标题下方渲染一条随 tick 更新的浮动说明文字，解释"这个指标现在为什么长这样"。
// 跟 h2 下方原有的静态 .desc（图表整体背景介绍，不随时间变化）区分：
// 这里是 .panel-narration（动态因果解释，随场景/子阶段变化，文字更新时有淡入/上滑过渡）。
// 场景没有为某个面板提供 narration 时，直接隐藏这条浮层，不覆盖已有的静态 .desc。

import { getNarration } from '../engine.js';
import { chartDefs } from '../chart-defs.js';

const lastText = {}; // canvasId -> 上次渲染的文本，用于判断是否需要重新触发过渡动画

function renderNarrationForPanel(canvasId) {
  const el = document.getElementById('narration-' + canvasId);
  if (!el) return;
  const text = getNarration()[canvasId] ?? null;

  if (!text) {
    el.classList.remove('show', 'pulse');
    lastText[canvasId] = null;
    return;
  }

  if (text !== lastText[canvasId]) {
    // 文本变化：重新触发一次淡入/滑入过渡（先移除再在下一帧加回 class 以重启 CSS animation）
    el.classList.remove('pulse');
    el.textContent = text;
    el.classList.add('show');
    requestAnimationFrame(() => el.classList.add('pulse'));
    lastText[canvasId] = text;
  }
}

export function renderAllPanelNarrations() {
  Object.keys(chartDefs).forEach(renderNarrationForPanel);
}
