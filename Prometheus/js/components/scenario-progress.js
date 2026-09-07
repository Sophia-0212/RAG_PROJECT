// ============ 侧边栏场景进度指示器 ============
// 在每个场景按钮下方渲染"当前处于周期第几秒 / 子阶段"，每个 tick 跟随 render() 一起刷新。
// 无固定周期的场景（比如 normal）显示"∞ 持续运行"而不是倒计时，避免暗示一个不存在的终点。

import { getActiveScenarioId, getProgress, TICK_SECONDS, onScenarioChangeCallback } from '../engine.js';

function formatProgressLine(progress) {
  if (progress.cycleTicks === null) {
    return '∞ 持续运行';
  }
  const totalSeconds = progress.cycleTicks * TICK_SECONDS;
  const elapsedSeconds = progress.ticksElapsed * TICK_SECONDS;
  let line = `第 ${elapsedSeconds}s / ${totalSeconds}s`;
  if (progress.phaseLabel) {
    line += ` · ${progress.phaseLabel}`;
    if (progress.phaseTicksLeft !== null) {
      line += `（剩 ${progress.phaseTicksLeft * TICK_SECONDS}s）`;
    }
  }
  return line;
}

function renderProgressForButton(btn) {
  const el = btn.querySelector('.scenario-progress');
  if (!el) return;

  if (btn.dataset.scenarioId !== getActiveScenarioId()) {
    el.textContent = '';
    el.classList.remove('show');
    return;
  }
  el.textContent = formatProgressLine(getProgress());
  el.classList.add('show');
}

export function renderScenarioProgress() {
  document.querySelectorAll('.scenario-item[data-scenario-id]').forEach(renderProgressForButton);
}

export function setupScenarioProgress() {
  onScenarioChangeCallback(() => renderScenarioProgress());
  renderScenarioProgress();
}
