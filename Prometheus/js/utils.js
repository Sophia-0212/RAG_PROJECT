// ============ 通用小工具 ============

export function clamp(v, min, max) {
  return Math.max(min, Math.min(max, v));
}

export function randWalk(prev, min, max, step) {
  const next = prev + (Math.random() - 0.5) * step;
  return clamp(next, min, max);
}

// 把 tick 序号换算成"相对现在多久之前"，给图表 hover tooltip 用
export function formatRelativeTime(pointIndexInSeries, seriesLength, tickSeconds) {
  const ticksAgo = seriesLength - 1 - pointIndexInSeries;
  const secondsAgo = ticksAgo * tickSeconds;
  if (secondsAgo === 0) return '现在';
  if (secondsAgo < 60) return `${secondsAgo}s 前`;
  return `${Math.floor(secondsAgo / 60)}m${secondsAgo % 60}s 前`;
}
