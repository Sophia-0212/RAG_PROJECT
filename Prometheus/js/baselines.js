// ============ 基准线定义模块 ============
// 所有阈值按"基准 × 倍数"计算，倍数按各指标业务含义单独设定，不是机械套统一公式。
// 数值来源见页面"基准线一览表"，这里是同一份定义的代码实现。
// 数据基准全部来自 test/002_1. 模拟业务背景与结果总览.md 的"上线后"数值。

export const SLOTS = 36; // 应用并发槽位上限，对应文档"RAG Service 3 Pod × 1 worker × 12 并发"

export const BASELINES = {
  inflight: { baseline: 27.7, warnAt: 30.6, dangerAt: 34.2, max: 36, reverse: false }, // 占用率 85% / 95%，对应 SLOTS=36
  qps: { baseline: 9, warnAt: 11.7, dangerAt: 16.2, max: 18, reverse: false }, // 1.3x / 1.8x 基准
  success: { baseline: 90, warnAt: 82, dangerAt: 70, max: 100, reverse: true }, // 越低越差，方向相反；基准=90%（不是文档里"审批恢复成功率99.93%"——那是HITL人工审批流程的分母，跟RAG请求outcome=success是两件事，文档自己也禁止混用；90%是按 refusal_reason 里15种业务拒答原因+ACL拒答在真实RAG服务中的正常占比估算的更现实基准）
  p95: { baseline: 3080, warnAt: 4620, dangerAt: 7700, max: 9000, reverse: false }, // 1.5x / 2.5x 基准（ms）
  avg: { baseline: 1400, warnAt: 2100, dangerAt: 3500, max: 4200, reverse: false }, // 1.5x / 2.5x 基准（ms）
};

export function clamp(v, min, max) {
  return Math.max(min, Math.min(max, v));
}

// 根据当前值 + 基准定义，算出：状态（ok/warn/danger）+ 在条形图里的百分比位置
export function evalBaseline(key, value) {
  const b = BASELINES[key];
  const pct = clamp((value / b.max) * 100, 0, 100);
  let status;
  if (b.reverse) {
    status = value >= b.warnAt ? 'ok' : value >= b.dangerAt ? 'warn' : 'danger';
  } else {
    status = value < b.warnAt ? 'ok' : value < b.dangerAt ? 'warn' : 'danger';
  }
  const baselinePct = clamp((b.baseline / b.max) * 100, 0, 100);
  // 条形图三色分段必须跟 status 判定用同一套 warnAt/dangerAt 换算，否则背景色分界点和指针位置各算各的，
  // 会出现"指针已经落在橙色区间，但背景条那一段还画着绿色"的不一致——每个指标的百分比档位都不一样，不能写死成固定的 40%/70%。
  const warnPct = clamp((b.warnAt / b.max) * 100, 0, 100);
  const dangerPct = clamp((b.dangerAt / b.max) * 100, 0, 100);
  const gradient = b.reverse
    ? `linear-gradient(to right, var(--red) 0%, var(--red) ${dangerPct}%, var(--orange) ${dangerPct}%, var(--orange) ${warnPct}%, var(--green) ${warnPct}%, var(--green) 100%)`
    : `linear-gradient(to right, var(--green) 0%, var(--green) ${warnPct}%, var(--orange) ${warnPct}%, var(--orange) ${dangerPct}%, var(--red) ${dangerPct}%, var(--red) 100%)`;
  return { pct, status, baselinePct, gradient };
}
