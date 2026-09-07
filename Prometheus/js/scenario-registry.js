// ============ 场景注册表 ============
// 新增一个故障场景，只需要在这里加一个对象，不需要改动其它任何模块。
// 每个场景是一个"状态机"：state()负责每 tick 更新自己的内部状态并返回派生指标补丁，
// enter()/exit() 负责场景切换时的一次性副作用（比如显示/隐藏横幅）。
//
// 场景之间通过 engine.js 里的 activeScenario 互斥切换：
// 切场景时会先调旧场景的 exit()，再调新场景的 enter()。

import { normalScenario } from './scenarios/normal.js';
import { incidentScenario } from './scenarios/incident.js';
import { outageScenario } from './scenarios/outage.js';

// key 对应侧边栏按钮的 id 后缀（比如 'normal' 对应 #btn-normal）
export const SCENARIOS = {
  normal: normalScenario,
  incident: incidentScenario,
  outage: outageScenario,
};

export const DEFAULT_SCENARIO = 'normal';
