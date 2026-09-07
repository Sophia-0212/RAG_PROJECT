// ============ 图表定义注册表 ============
// 每张图表的 series/颜色/名称/单位定义在这里，供 line-chart.js 渲染和 hover-tooltip.js 展示数值复用。
// labels 统一采用"英文原词（中文）"格式，跟图表标题、图例的写法保持一致，方便对照记忆。
// 新增一张图表：在这里加一个条目，再在 dashboard.html 里加对应的 <canvas> 容器即可。

export const chartDefs = {
  'chart-qps': {
    seriesKeys: ['qpsSuccess', 'qpsRefused'],
    labels: ['success（成功）', 'refused（被拒绝）'],
    colors: ['#3fb950', '#d29922'],
    unit: 'req/s',
    format: (v) => v.toFixed(2),
  },
  'chart-latency': {
    seriesKeys: ['avg', 'p50', 'p95', 'p99'],
    labels: ['Average（平均）', 'P50（中位数）', 'P95', 'P99'],
    colors: ['#3fb950', '#58a6ff', '#d29922', '#f85149'],
    unit: 'ms',
    format: (v) => Math.round(v) + ' ms',
  },
  'chart-rejections': {
    seriesKeys: ['rejQuota', 'rejCapacity', 'rejBusy', 'rejCoord', 'rejCircuitOpen'],
    labels: [
      'quota（配额限流）',
      'capacity（容量超限）',
      'conversation_busy（会话占用中）',
      'coordination_unavailable（协调服务不可用）',
      'circuit_open（熔断跳闸）',
    ],
    colors: ['#d29922', '#f85149', '#bc8cff', '#8b949e', '#79c0ff'],
    unit: 'req/s',
    format: (v) => v.toFixed(2),
  },
  'chart-duplicate': {
    seriesKeys: ['runCreated', 'runDuplicate'],
    labels: ['created（全新请求）', 'duplicate（重复提交）'],
    colors: ['#3fb950', '#f85149'],
    unit: 'req/s',
    format: (v) => v.toFixed(2),
  },
  'chart-recovery': {
    seriesKeys: ['recoverySuccess', 'recoveryDenied', 'recoveryRetry'],
    labels: ['success（恢复成功）', 'authorization_denied（鉴权被拒）', 'retryable_failure（可重试失败）'],
    colors: ['#3fb950', '#f85149', '#d29922'],
    unit: 'req/s',
    format: (v) => v.toFixed(2),
  },
};
