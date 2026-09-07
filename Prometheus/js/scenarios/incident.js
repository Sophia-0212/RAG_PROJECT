// ============ 场景：下游 LLM 延迟抖动 ============
// 延迟渐进升高但请求最终仍能成功——跟 outage 场景（熔断跳闸）的关键区别：
// 这里成功率基本不掉，只是变慢；outage 场景延迟和成功率会同时断崖式下跌。

import { randWalk } from '../utils.js';

const DURATION_TICKS = 15; // 约 30 秒（TICK_SECONDS=2）后自动恢复到 normal

export const incidentScenario = {
  id: 'incident',
  label: 'LLM 延迟抖动',
  severity: 'warn',
  bannerId: 'incident-banner',

  enter(ctx) {
    ctx.ticksLeft = DURATION_TICKS;
  },

  exit(ctx) {
    // 无需额外清理，ticksLeft 由 engine 统一管理
  },

  tick(ctx) {
    const { state } = ctx;
    ctx.ticksLeft -= 1;

    // 故障期间：延迟基准飙高（对照文档基线 P95=4.85s 之上继续恶化，模拟比基线更差的极端场景）
    state.p95Base = randWalk(state.p95Base, 3000, 9800, 800);
    state.qpsRefused = randWalk(state.qpsRefused, 0.5, 4, 0.6);
    state.runDuplicate = randWalk(state.runDuplicate, 3, 12, 2);
    // 恢复面在下游变慢时，retry 占比应显著升高（更多恢复尝试因为下游还没恢复而失败重试）
    state.recoveryTotal = randWalk(state.recoveryTotal, 1.5, 4, 0.5);

    const expired = ctx.ticksLeft <= 0;

    return {
      p95Override: null,
      rejCircuitOpen: 0,
      runCreatedRange: [3, 7], // 下游变慢，新请求因排队效应被间接抑制
      retryRatioRange: [0.35, 0.55],
      statusText: '⚠ 下游延迟抖动中',
      expired,
      progress: {
        cycleTicks: DURATION_TICKS,
        ticksElapsed: DURATION_TICKS - ctx.ticksLeft,
        phaseLabel: null, // 扁平周期，没有子阶段
        phaseTicksLeft: null,
      },
      narration: {
        'chart-latency': '延迟因下游 LLM 抖动持续走高，逼近甚至超过文档基线 4.85s——但请求最终仍会返回成功，这是跟 outage 场景最大的区别：这里只慢，不拒绝。',
        'chart-qps': 'success 曲线基本未受影响，refused 小幅上升——是下游变慢间接抑制了新请求，不是主动拒绝。',
        'chart-duplicate': 'duplicate 因客户端超时重试而暴增：延迟涨得越高，客户端越容易在等待中触发重试，产生同一 request_id 的重复提交。',
        'chart-recovery': 'retry 占比明显抬高：下游还没恢复，本轮恢复尝试大概率依然失败，需要下一轮再试。',
      },
    };
  },
};
