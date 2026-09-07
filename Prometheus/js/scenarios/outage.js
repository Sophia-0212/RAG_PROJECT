// ============ 场景：LLM 完全不可用（熔断跳闸） ============
// 镜像 rag_service/resilience.py 里 CircuitBreaker 的三态模型：
// CLOSED（正常）→ 连续失败达到阈值 → OPEN（跳闸，直接拒绝，不再等超时）
// → 冷却期满 → HALF_OPEN（放一个试探请求）→ 试探成功回到 CLOSED；试探失败重新计满阈值再次 OPEN。
//
// 教学重点：CLOSED/HALF_OPEN 阶段真的等到 LLM 超时才失败，延迟冲到 llm_timeout_seconds 附近；
// OPEN 阶段熔断器直接拒绝，延迟反而断崖式下跌——这是这个场景跟 incident（纯延迟抖动）
// 最大的区别：那个场景是"延迟涨、成功率基本不变"；这个场景是"延迟先涨后跌、成功率同时跌"。

import { randWalk, clamp } from '../utils.js';

const DURATION_TICKS = 45; // 约 90 秒：足够走完至少一轮 熔断→冷却30s→试探 的完整周期
const CIRCUIT_FAILURE_THRESHOLD = 3; // 对应 settings.py circuit_failure_threshold
const CIRCUIT_RECOVERY_TICKS = 15; // 对应 circuit_recovery_seconds=30s，按 TICK_SECONDS=2s 换算
const LLM_TIMEOUT_MS = 20000; // 对应 settings.py llm_timeout_seconds=20s

// 子阶段人类可读描述，跟 statusText 用的判断条件保持一致（都读 ctx.circuitState 本 tick 转移后的值）
const PHASE_LABELS = {
  CLOSED: '等待 LLM 超时中',
  OPEN: '熔断跳闸，快速拒绝中',
  HALF_OPEN: '试探请求中',
};

// 每张图表的浮动因果说明按熔断器当前状态分组——同一个场景内，随 ctx.circuitState 切换而变化，
// 这正是"每个面板的说明要随秒数/阶段联动变化"的例子：chart-latency 在 CLOSED 和 OPEN 下文案完全不同。
const NARRATION_BY_STATE = {
  CLOSED: {
    'chart-latency': `熔断器仍是 CLOSED，请求真的打给了 LLM，等到约 ${(LLM_TIMEOUT_MS / 1000).toFixed(0)}s 超时才失败——延迟被推到超时阈值附近，这是本阶段延迟"先冲高"的原因。`,
    'chart-rejections': 'circuit_open 尚为 0：熔断器还没跳闸，当前失败走的是"真实调用后超时"，不计入 circuit_open 这个拒绝原因。',
  },
  HALF_OPEN: {
    'chart-latency': '熔断器进入 HALF_OPEN，放行一个试探请求——如果这次也失败，会立刻重新计满失败阈值再次跳闸。',
    'chart-rejections': '试探请求本身不算被拒绝，但试探失败会让 circuit_open 在下一个 tick 重新出现。',
  },
  OPEN: {
    'chart-latency': '熔断器已 OPEN：请求不再真的调用 LLM，直接快速拒绝，延迟反而断崖式下跌到 ~200-350ms——低延迟在这里不是好消息，是熔断跳闸的信号。',
    'chart-rejections': 'circuit_open 持续走高，这段时间几乎所有请求都在冷却期内被快速拒绝，是当前"被拒绝"的主要来源。',
  },
};

export const outageScenario = {
  id: 'outage',
  label: 'LLM 完全不可用（熔断跳闸）',
  severity: 'danger',
  bannerId: 'outage-banner',

  enter(ctx) {
    ctx.ticksLeft = DURATION_TICKS;
    ctx.circuitState = 'CLOSED'; // CLOSED | OPEN | HALF_OPEN
    ctx.circuitFailures = 0;
    ctx.circuitCooldownTicksLeft = 0;
  },

  exit(ctx) {
    ctx.circuitState = 'CLOSED';
    ctx.circuitFailures = 0;
  },

  tick(ctx) {
    const { state } = ctx;
    ctx.ticksLeft -= 1;

    let p95Override = null;
    let rejCircuitOpen = 0;

    if (ctx.circuitState === 'CLOSED' || ctx.circuitState === 'HALF_OPEN') {
      // 还没跳闸（或正在试探）：这次调用真的打给 LLM，真等到超时才失败
      p95Override = LLM_TIMEOUT_MS * (0.85 + Math.random() * 0.25);
      ctx.circuitFailures += 1;
      if (ctx.circuitState === 'HALF_OPEN') {
        // 试探失败：重新计满阈值，立刻再次跳闸
        ctx.circuitState = 'OPEN';
        ctx.circuitCooldownTicksLeft = CIRCUIT_RECOVERY_TICKS;
        ctx.circuitFailures = 0;
      } else if (ctx.circuitFailures >= CIRCUIT_FAILURE_THRESHOLD) {
        ctx.circuitState = 'OPEN';
        ctx.circuitCooldownTicksLeft = CIRCUIT_RECOVERY_TICKS;
        ctx.circuitFailures = 0;
      }
    } else {
      // OPEN：熔断器直接拒绝，不再真的调 LLM——延迟断崖式下跌，因为不用等超时了
      ctx.circuitCooldownTicksLeft -= 1;
      p95Override = 200 + Math.random() * 150; // 只是被拒绝前的极小处理开销，不是真实调用延迟
      rejCircuitOpen = 6 + Math.random() * 3; // 冷却期内持续有请求被熔断快速拒绝
      if (ctx.circuitCooldownTicksLeft <= 0) {
        ctx.circuitState = 'HALF_OPEN'; // 冷却期满，放一个试探请求
      }
    }

    // 熔断场景下：qpsRefused/duplicate 也会明显升高（熔断拒绝本身就是一种 refused）
    state.qpsRefused = randWalk(state.qpsRefused, 1, 5, 0.6);
    // 熔断跳闸期客户端超时重试的比例远低于纯延迟抖动场景（快速失败，用户等待时间短，重试冲动较弱）
    state.runDuplicate = randWalk(state.runDuplicate, 0.3, 2, 0.3);
    state.recoveryTotal = randWalk(state.recoveryTotal, 0.3, 1, 0.2);
    // 熔断期这个基准量本身不参与展示（被 p95Override 接管），维持游走避免恢复时突变
    state.p95Base = randWalk(state.p95Base, 2700, 3500, 120);

    const statusText =
      ctx.circuitState === 'OPEN'
        ? `⚠ 熔断跳闸中（快速拒绝，冷却 ${ctx.circuitCooldownTicksLeft * ctx.tickSeconds}s）`
        : '⚠ LLM 不可用，等待超时中';

    const expired = ctx.ticksLeft <= 0;

    const phaseTicksLeft =
      ctx.circuitState === 'OPEN'
        ? ctx.circuitCooldownTicksLeft
        : ctx.circuitState === 'CLOSED'
          ? CIRCUIT_FAILURE_THRESHOLD - ctx.circuitFailures
          : null; // HALF_OPEN 在当前实现里一个 tick 内就会解析完毕，没有可展示的"剩余"概念

    return {
      p95Override,
      rejCircuitOpen,
      runCreatedRange: [3, 7],
      retryRatioRange: [0.35, 0.55],
      statusText,
      expired,
      progress: {
        cycleTicks: DURATION_TICKS,
        ticksElapsed: DURATION_TICKS - ctx.ticksLeft,
        phaseLabel: PHASE_LABELS[ctx.circuitState],
        phaseTicksLeft,
      },
      narration: {
        ...NARRATION_BY_STATE[ctx.circuitState],
        'chart-qps': 'refused 明显升高：熔断跳闸期的快速拒绝也计入 refused。',
        'chart-duplicate': '熔断跳闸期用户等待时间短（快速失败），重试冲动比 incident 场景更弱，duplicate 涨幅相对温和。',
        'chart-recovery': 'retry 占比同样显著抬高：下游依赖仍不可用，恢复尝试大概率继续失败。',
      },
    };
  },
};
