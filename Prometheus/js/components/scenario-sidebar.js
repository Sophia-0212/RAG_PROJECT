// ============ 左侧场景侧边栏组件 ============
// 新增场景步骤：
// 1. 在 scenarios/ 目录加一个场景文件，注册进 scenario-registry.js
// 2. 在 dashboard.html 侧边栏加一个 <button class="scenario-item" data-scenario-id="xxx">
// 这个组件不需要跟着改——它是根据 data-scenario-id 自动找按钮，自动高亮，不需要为每个场景单独写代码。

import { switchScenario, onScenarioChangeCallback, getActiveScenarioId } from '../engine.js';
import { SCENARIOS } from '../scenario-registry.js';

function highlightActive(id) {
  document.querySelectorAll('.scenario-item[data-scenario-id]').forEach((btn) => {
    const isActive = btn.dataset.scenarioId === id;
    btn.classList.toggle('active', isActive);
  });

  // 场景对应的提示横幅：只显示当前激活场景的横幅，其余全部隐藏
  document.querySelectorAll('.incident-banner').forEach((banner) => banner.classList.remove('show'));
  const scenario = SCENARIOS[id];
  if (scenario && scenario.bannerId) {
    const banner = document.getElementById(scenario.bannerId);
    if (banner) banner.classList.add('show');
  }
}

export function setupScenarioSidebar() {
  document.querySelectorAll('.scenario-item[data-scenario-id]').forEach((btn) => {
    btn.addEventListener('click', () => {
      switchScenario(btn.dataset.scenarioId);
    });
  });

  // engine 内部到期自动切回 normal 时，也要同步侧边栏高亮
  onScenarioChangeCallback(highlightActive);

  highlightActive(getActiveScenarioId());
}
