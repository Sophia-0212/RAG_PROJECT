// ============ 场景：正常运行 ============
// 所有指标围绕"上线后"文档基准小幅波动，是其它场景恢复后回归的默认状态。

import { randWalk } from '../utils.js';

export const normalScenario = {
  id: 'normal',
  label: '正常场景',
  severity: 'ok',
  bannerId: null, // 没有对应的提示横幅

  enter(ctx) {
    // 无需一次性副作用
  },

  exit(ctx) {
    // 无需清理
  },

  // 每个 tick 调用一次，直接修改 ctx.state（自由游走的基准量），
  // 返回值用于覆盖延迟基准（正常场景不需要覆盖，返回 null）
  tick(ctx) {
    const { state } = ctx;
    state.p95Base = randWalk(state.p95Base, 2700, 3500, 120);
    state.qpsRefused = randWalk(state.qpsRefused, 0.1, 1.2, 0.25);
    state.runDuplicate = randWalk(state.runDuplicate, 0.05, 0.8, 0.15);
    state.recoveryTotal = randWalk(state.recoveryTotal, 0.2, 0.6, 0.1);

    return {
      p95Override: null,
      rejCircuitOpen: 0,
      runCreatedRange: [4, 12],
      retryRatioRange: [0.05, 0.13],
      statusText: '正常范围（基准 3.08s）',
      progress: { cycleTicks: null, ticksElapsed: null, phaseLabel: null, phaseTicksLeft: null },
      narration: {
        'chart-latency': '延迟围绕 3.08s 基准小幅游走，属于正常抓取抖动，不代表异常。',
        'chart-rejections': '各类拒绝均为背景噪声水平，占用率未触及 85% 并发阈值，capacity 拒绝几乎为零。',
      },
    };
  },
};
