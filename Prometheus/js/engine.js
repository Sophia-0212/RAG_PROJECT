// ============ 指标状态引擎 ============
// 这是全局唯一一份"当前场景 + 所有指标当前值"的状态容器。
// engine 本身不关心某个具体场景怎么算延迟、怎么算拒绝率——那些逻辑全部在 scenarios/*.js 里，
// engine 只负责：① 维护自由游走的基准量 state ② 调用当前场景的 tick() 拿到覆盖值/范围
// ③ 把场景返回的"范围"和"覆盖值"应用到派生公式上，产出 derived（供图表渲染读取）。
//
// 新增一个指标的步骤（跟场景无关，任何场景都能立刻用上这个新指标）：
// 1. 在 state 或 derived 里加一个字段
// 2. 在 history 里加对应的历史数组
// 3. 如果需要基准线对比，在 baselines.js 的 BASELINES 里注册

import { clamp } from './utils.js';
import { SLOTS } from './baselines.js';
import { SCENARIOS, DEFAULT_SCENARIO } from './scenario-registry.js';

export const MAX_POINTS = 60; // 时间窗口内保留的数据点数
export const TICK_SECONDS = 2; // 每个数据点代表的模拟时间跨度（秒）

// ---- 自由游走的基准量：只有这些会被 randWalk 直接修改，其余全部靠公式派生 ----
export const state = {
  qpsSuccess: 7.6, // 峰值 QPS=9，success 占绝大多数，日常水位设在峰值的 ~85%
  qpsRefused: 0.35,
  p95Base: 3080, // 延迟的唯一自由游走基准，直接取文档"上线后 RAG P95 完整响应 3.08 秒"
  rejQuota: 0.08,
  rejBusy: 0.15,
  rejCoord: 0.015,
  runDuplicate: 0.22, // 幂等命中率参照"重复副作用事故清零"后的低位水平
  recoveryTotal: 0.42, // 每 tick 恢复尝试总量，success/denied/retry 由它按比例拆分
};

// ---- 派生结果：每次 tick 用公式从 state 算出来，不参与随机游走 ----
export let derived = {
  avg: 0, p50: 0, p95: 0, p99: 0,
  inflight: 0,
  rejCapacity: 0, rejCircuitOpen: 0,
  runCreated: 0,
  recoverySuccess: 0, recoveryDenied: 0, recoveryRetry: 0,
};

export const history = {
  qpsSuccess: [], qpsRefused: [],
  avg: [], p50: [], p95: [], p99: [],
  rejQuota: [], rejCapacity: [], rejBusy: [], rejCoord: [], rejCircuitOpen: [],
  runCreated: [], runDuplicate: [],
  recoverySuccess: [], recoveryDenied: [], recoveryRetry: [],
};

// ---- 场景切换上下文：每个场景实例可以在这个对象上挂自己的私有状态（比如熔断器的 circuitState） ----
// 场景切换时会重新赋值这个对象（保留 tickSeconds，清空场景私有字段）
let scenarioCtx = { tickSeconds: TICK_SECONDS };
let activeScenarioId = DEFAULT_SCENARIO;
let statusText = '正常范围（基准 3.08s）';

// ---- 场景周期进度 + 每面板因果说明：由场景 tick() 返回值驱动，engine.js 只转发，不感知具体场景 ----
// cycleTicks=null 表示无固定周期（比如 normal 场景无限循环）；phaseLabel 用于有嵌套子状态机的场景（比如 outage 的熔断器三态）
const EMPTY_PROGRESS = { cycleTicks: null, ticksElapsed: null, phaseLabel: null, phaseTicksLeft: null };
export let progress = { ...EMPTY_PROGRESS };
export let narration = {}; // { [canvasId]: string }，键对应 chart-defs.js 里的 canvas id

export function getProgress() {
  return progress;
}

export function getNarration() {
  return narration;
}

let onScenarioChangeCallbacks = []; // UI 层注册的回调列表，场景切换/到期时依次通知——不能用单变量，否则后注册的回调会覆盖先注册的（比如侧边栏高亮和进度指示器都要监听场景切换）

export function onScenarioChangeCallback(fn) {
  onScenarioChangeCallbacks.push(fn);
}

export function getActiveScenarioId() {
  return activeScenarioId;
}

export function getStatusText() {
  return statusText;
}

// 切换到指定场景：调旧场景 exit()，重置 ctx，调新场景 enter()
export function switchScenario(id) {
  if (!SCENARIOS[id]) return;
  const prev = SCENARIOS[activeScenarioId];
  if (prev && prev.exit) prev.exit(scenarioCtx);

  activeScenarioId = id;
  scenarioCtx = { tickSeconds: TICK_SECONDS };
  const next = SCENARIOS[activeScenarioId];
  if (next.enter) next.enter(scenarioCtx);

  // 立即清空上一个场景残留的进度/说明文字，避免下一次 tick() 之前出现短暂的"串场"闪烁
  progress = { ...EMPTY_PROGRESS };
  narration = {};

  if (onScenarioChangeCallbacks.length) onScenarioChangeCallbacks.forEach((fn) => fn(activeScenarioId));
}

function pushHistory(key, value) {
  history[key].push(value);
  if (history[key].length > MAX_POINTS) history[key].shift();
}

// ============ 每一个 tick 更新一次全部状态（模拟 Prometheus 抓取周期） ============
export function tick() {
  const scenario = SCENARIOS[activeScenarioId];
  // 把 engine 里唯一的 state 对象挂到 ctx 上，场景的 tick(ctx) 里才能用 ctx.state 修改它——
  // 之前这里漏挂，场景里 const { state } = ctx 解构出 undefined，一 state.xxx = ... 就抛 TypeError，
  // 定时器里的回调整个中断，页面从那一刻起就冻住不再刷新（现象：切场景后数据消失、页面点不动）。
  scenarioCtx.state = state;
  const result = scenario.tick(scenarioCtx);
  statusText = result.statusText;
  progress = result.progress ?? { ...EMPTY_PROGRESS };
  narration = result.narration ?? {};

  // 场景到期（比如 incident/outage 跑完自己的持续时长）：自动切回正常场景
  if (result.expired) {
    switchScenario(DEFAULT_SCENARIO);
  }

  state.rejQuota = clamp(state.rejQuota + (Math.random() - 0.5) * 0.12, 0, 0.4);
  state.rejBusy = clamp(state.rejBusy + (Math.random() - 0.5) * 0.15, 0, 0.6);
  state.rejCoord = clamp(state.rejCoord + (Math.random() - 0.5) * 0.04, 0, 0.12);
  state.qpsSuccess = clamp(state.qpsSuccess + (Math.random() - 0.5) * 1.2, 5, 9);

  // ---- 从 p95Base（或场景覆盖的 p95Override）派生 P50/Average/P99 ----
  // 分位数曲线的相对次序是数学定义决定的恒等式，不是"通常如此"的经验规律，绝不能独立游走
  const p95 = result.p95Override !== null && result.p95Override !== undefined ? result.p95Override : state.p95Base;
  const p50 = p95 * (0.28 + Math.random() * 0.07); // P50 常年落在 P95 的 28%-35%
  const avgRatio = 0.35 + Math.random() * 0.15; // Average 落在 P50 与 P95 之间的比例位置
  const avg = clamp(p50 + (p95 - p50) * avgRatio, p50, p95);
  const p99 = p95 * (1.35 + Math.random() * 0.25); // P99 常年是 P95 的 1.35-1.6 倍

  // ---- In-Flight 由 Little's Law 从 QPS × Average Latency 直接算出 ----
  const throughput = state.qpsSuccess + state.qpsRefused;
  const littlesLawInflight = throughput * (avg / 1000);
  const inflight = Math.max(0, littlesLawInflight * (1 + (Math.random() - 0.5) * 0.16));

  // ---- capacity 拒绝由并发槽位占用率派生：占用率没到阈值前几乎为 0，超过阈值后才陡增 ----
  const occupancyRatio = inflight / SLOTS;
  const CAPACITY_THRESHOLD = 0.85;
  const rejCapacity = occupancyRatio > CAPACITY_THRESHOLD
    ? Math.max(0, (occupancyRatio - CAPACITY_THRESHOLD) * 14 + Math.random() * 0.3)
    : Math.random() * 0.02;

  // ---- created：按场景给的范围游走 ----
  const [createdMin, createdMax] = result.runCreatedRange;
  const runCreated = createdMin + Math.random() * (createdMax - createdMin);

  // ---- recovery 三个 outcome 从"本 tick 恢复尝试总量"按比例拆分 ----
  const total = state.recoveryTotal;
  const deniedRatio = 0.02 + Math.random() * 0.02; // 鉴权被拒占比稳定且很低（99.93% 恢复成功率的背景）
  const [retryMin, retryMax] = result.retryRatioRange;
  const retryRatio = retryMin + Math.random() * (retryMax - retryMin);
  const successRatio = Math.max(0, 1 - deniedRatio - retryRatio);
  const recoveryDenied = total * deniedRatio;
  const recoveryRetry = total * retryRatio;
  const recoverySuccess = total * successRatio;

  derived = {
    avg, p50, p95, p99,
    inflight,
    rejCapacity, rejCircuitOpen: result.rejCircuitOpen,
    runCreated,
    recoverySuccess, recoveryDenied, recoveryRetry,
  };

  for (const key of Object.keys(history)) {
    const value = key in state ? state[key] : derived[key];
    pushHistory(key, value);
  }
}

// 启动时预填充历史点，避免刚打开时图表是空的
export function primeHistory() {
  SCENARIOS[activeScenarioId].enter(scenarioCtx);
  for (let i = 0; i < MAX_POINTS; i++) tick();
}
