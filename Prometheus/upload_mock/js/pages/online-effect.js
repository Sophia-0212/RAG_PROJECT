import { icon } from '../core/icons.js';
import {
  createOnlineFailureTicket,
  saveOnlineAlertRule,
  simulateOnlineAlertRule,
  toggleOnlineAlertRule,
  toggleOnlineExperiment,
} from '../core/mock-api.js';
import { badge, confirmAction, openDrawer, openModal, pageHeader, toast } from '../components/ui.js';
import { escapeHtml, relativeTime } from '../core/utils.js';

const metricDefinitions = {
  selfResolved: {
    label: '自助解决率', shortLabel: '自助解决', direction: 'up', color: '#2468f2', denominatorRatio: .64, unit: '次可判定会话',
    formula: '用户明确点击“已解决”，或回答关联的 CRM 任务成功完成的会话 / 可判定是否解决的有效会话',
    excludes: '排除无反馈且没有关联任务结果的会话、纯导航查询和内部压测。', source: 'RAG 反馈埋点 + CRM 任务结果事件',
  },
  unresolved: {
    label: '未解决率', shortLabel: '未解决', direction: 'down', color: '#b96f08', denominatorRatio: .48, unit: '次可反馈会话',
    formula: '用户明确点击“未解决”的会话 / 已展示答案且提供反馈入口的会话',
    excludes: '不把员工离开系统后去如流求助推断为未解决；该跨系统行为当前不可观测。', source: 'RAG 反馈埋点',
  },
  repeatQuery: {
    label: '重复提问率', shortLabel: '重复提问', direction: 'down', color: '#7657c8', denominatorRatio: .95, unit: '次有效会话',
    formula: '同一用户 10 分钟内再次询问语义相同意图的会话 / 去除机器人和重放流量后的有效会话',
    excludes: '排除系统主动澄清产生的多轮对话，以及用户明确追加新条件的追问。', source: '匿名 user_id + intent_id + 会话时间窗',
  },
  negativeFeedback: {
    label: '负反馈率', shortLabel: '负反馈', direction: 'down', color: '#d83b46', denominatorRatio: .38, unit: '次有反馈会话',
    formula: '被标记为答案错误、过期、不完整或引用无效的会话 / 已提交反馈的会话',
    excludes: '排除无反馈会话和仅评价交互体验、不评价答案质量的反馈。', source: 'RAG 结构化负反馈事件',
  },
  taskCompletion: {
    label: '任务完成率', shortLabel: '任务完成', direction: 'up', color: '#169b62', denominatorRatio: .31, unit: '次任务型会话',
    formula: '得到回答后在归因窗口内成功完成开户、客户归属修改等 CRM 操作的会话 / 可绑定任务结果的会话',
    excludes: '排除政策解释、概念查询等没有明确 CRM 完成事件的问题。', source: 'RAG trace_id + CRM 任务完成事件',
  },
  adoption: {
    label: '答案采纳率', shortLabel: '答案采纳', direction: 'up', color: '#0f8f9b', denominatorRatio: .42, unit: '条可采纳答案',
    formula: '被复制、引用到工单或用于发起后续操作的答案 / 提供采纳能力的有效答案',
    excludes: '排除拒答、纯导航结果，以及页面没有复制或引用能力的答案。', source: '复制、引用、插入工单和后续操作埋点',
  },
};

const metricKeys = Object.keys(metricDefinitions);
const view = {
  days: 14,
  grain: 'day',
  versionMode: 'compare',
  tenant: 'all',
  business: 'all',
  issue: 'all',
  dimension: 'tenant',
  visibleMetrics: new Set(['selfResolved', 'unresolved', 'taskCompletion']),
};

const dimensionLabels = { tenant: '租户', business: '业务线', issue: '问题类型' };
const actionLabels = { alert: '仅告警', pause: '暂停候选组分流', rollback: '自动回滚' };
const alertMetricLabels = {
  ...Object.fromEntries(metricKeys.map((key) => [key, metricDefinitions[key].label])),
  highRiskWrongAnswers: '高风险错答',
  aclLeakage: 'ACL 越权泄漏',
};
const failureResultLabels = {
  selfResolved: '未自助解决',
  unresolved: '点击未解决',
  repeatQuery: '重复提问',
  negativeFeedback: '提交负反馈',
  taskCompletion: '任务未完成',
  adoption: '答案未采纳',
};

function selectedRow(effect, dimension, id) {
  return id === 'all' ? null : effect.dimensions[dimension].find((item) => item.id === id);
}

function filteredMetrics(effect) {
  const baseline = Object.fromEntries(metricKeys.map((key) => [key, effect.experiment.control[key]]));
  const current = Object.fromEntries(metricKeys.map((key) => [key, effect.experiment.treatment[key]]));
  const rows = [selectedRow(effect, 'tenant', view.tenant), selectedRow(effect, 'business', view.business), selectedRow(effect, 'issue', view.issue)].filter(Boolean);
  if (view.versionMode === 'baseline') return { current: baseline, baseline, rows };
  if (!rows.length) return { current, baseline, rows };
  const average = (key) => rows.reduce((sum, row) => sum + row[key], 0) / rows.length;
  return { current: Object.fromEntries(metricKeys.map((key) => [key, average(key)])), baseline, rows };
}

function countableTrendPoints(effect) {
  const current = effect.trends.filter((item) => item.date >= '09/01');
  const baseline = effect.trends.filter((item) => item.date < '09/01');
  const points = view.versionMode === 'baseline' ? baseline : current;
  return points.slice(-view.days);
}

function scopedSamples(effect) {
  const total = effect.dimensions.tenant.reduce((sum, item) => sum + item.samples, 0);
  const rows = [selectedRow(effect, 'tenant', view.tenant), selectedRow(effect, 'business', view.business), selectedRow(effect, 'issue', view.issue)].filter(Boolean);
  const periodTotal = countableTrendPoints(effect).reduce((sum, item) => sum + item.questions, 0);
  if (!rows.length) return periodTotal;
  const ratio = rows.reduce((result, row) => result * Math.max(.04, row.samples / total), 1);
  return Math.max(1, Math.round(periodTotal * ratio));
}

function metricCounts(effect, key, value) {
  const definition = metricDefinitions[key];
  const denominator = Math.max(1, Math.round(scopedSamples(effect) * definition.denominatorRatio));
  return { numerator: Math.round(denominator * value / 100), denominator, unit: definition.unit };
}

function metricCard(effect, key, value, baseline) {
  const definition = metricDefinitions[key];
  const counts = metricCounts(effect, key, value);
  const diff = value - baseline;
  const improved = definition.direction === 'up' ? diff >= 0 : diff <= 0;
  return `<button class="effect-metric-card" type="button" data-metric-card="${key}">
    <span class="effect-metric-head"><span>${escapeHtml(definition.label)}</span>${icon('chevronRight')}</span>
    <strong>${value.toFixed(1)}%</strong>
    <span class="effect-metric-delta ${improved ? 'positive' : 'negative'}">${improved ? icon('checkCircle') : icon('alert')}${diff > 0 ? '+' : ''}${diff.toFixed(1)} 个百分点</span>
    <small>${counts.numerator.toLocaleString()} / ${counts.denominator.toLocaleString()} ${escapeHtml(counts.unit)}</small>
  </button>`;
}

function aggregateWeeks(points) {
  const groups = [];
  for (let index = 0; index < points.length; index += 7) {
    const batch = points.slice(index, index + 7);
    const average = (key) => batch.reduce((sum, item) => sum + item[key], 0) / batch.length;
    groups.push({
      date: `${batch[0].date}-${batch.at(-1).date}`,
      questions: batch.reduce((sum, item) => sum + item.questions, 0),
      ...Object.fromEntries(metricKeys.map((key) => [key, average(key)])),
      p95: average('p95'),
      release: batch.some((item) => item.release),
    });
  }
  return groups;
}

function trendPoints(effect) {
  let points = effect.trends.slice(-view.days);
  if (view.versionMode === 'baseline') points = effect.trends.filter((item) => item.date < '09/01').slice(-view.days);
  if (view.versionMode === 'current') points = effect.trends.filter((item) => item.date >= '09/01').slice(-view.days);
  return view.grain === 'week' ? aggregateWeeks(points) : points;
}

function trendChart(effect) {
  const points = trendPoints(effect);
  const width = 760; const height = 228; const left = 42; const right = 20; const top = 18; const bottom = 34;
  const plotWidth = width - left - right; const plotHeight = height - top - bottom;
  const x = (index) => left + (points.length === 1 ? plotWidth / 2 : index * plotWidth / (points.length - 1));
  const y = (value) => top + (100 - value) * plotHeight / 100;
  const grids = [0, 25, 50, 75, 100].map((tick) => `<line x1="${left}" y1="${y(tick)}" x2="${width - right}" y2="${y(tick)}" class="effect-chart-grid"/><text x="${left - 9}" y="${y(tick) + 3}" text-anchor="end">${tick}%</text>`).join('');
  const xLabels = points.map((item, index) => `<text x="${x(index)}" y="${height - 10}" text-anchor="middle">${escapeHtml(item.date)}</text>`).join('');
  const lines = metricKeys.filter((key) => view.visibleMetrics.has(key)).map((key) => {
    const definition = metricDefinitions[key];
    const values = points.map((item, index) => `${x(index)},${y(item[key])}`).join(' ');
    const circles = points.map((item, index) => `<circle cx="${x(index)}" cy="${y(item[key])}" r="4" fill="${definition.color}" data-trend-index="${index}" data-trend-metric="${key}" tabindex="0"><title>${item.date} ${definition.label} ${item[key].toFixed(1)}%</title></circle>`).join('');
    return `<polyline points="${values}" fill="none" stroke="${definition.color}" stroke-width="2.5" vector-effect="non-scaling-stroke"/>${circles}`;
  }).join('');
  const release = points.map((item, index) => item.release ? `<line x1="${x(index)}" y1="${top}" x2="${x(index)}" y2="${height - bottom}" class="effect-release-line"/><text x="${x(index) + 6}" y="${top + 10}" class="effect-release-label">新版上线</text>` : '').join('');
  return `<div class="effect-chart-wrap"><svg class="effect-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="上线效果趋势图">${grids}${release}${lines}${xLabels}</svg></div>`;
}

function selector(label, id, value, options) {
  return `<label class="filter-control"><span>${escapeHtml(label)}</span><select id="${id}">${options.map((item) => `<option value="${item.value}" ${item.value === value ? 'selected' : ''}>${escapeHtml(item.label)}</option>`).join('')}</select></label>`;
}

function topFilters(effect) {
  const dimensionOptions = (dimension) => [{ value: 'all', label: `全部${dimensionLabels[dimension]}` }, ...effect.dimensions[dimension].map((item) => ({ value: item.id, label: item.name }))];
  return `<section class="panel effect-filter-panel"><div class="filter-bar">
    ${selector('时间范围', 'effectDays', String(view.days), [{ value: '7', label: '近 7 天' }, { value: '14', label: '近 14 天' }])}
    ${selector('版本视图', 'effectVersion', view.versionMode, [{ value: 'compare', label: '上线前后对比' }, { value: 'current', label: '仅现网版本' }, { value: 'baseline', label: '仅基线版本' }])}
    ${selector('租户', 'effectTenant', view.tenant, dimensionOptions('tenant'))}
    ${selector('业务线', 'effectBusiness', view.business, dimensionOptions('business'))}
    ${selector('问题类型', 'effectIssue', view.issue, dimensionOptions('issue'))}
    <button class="button ghost small effect-reset" type="button" id="effectReset">${icon('refresh')}重置</button>
  </div><div class="effect-scope-strip"><span>${icon('database')}18 个 workspace</span><span>${icon('users')}190 日活用户</span><span>${icon('activity')}约 4,600 次 RAG 问答/日</span><span class="mono">${escapeHtml(effect.scope.baselineVersion)} → ${escapeHtml(effect.scope.currentVersion)}</span></div></section>`;
}

function metricSummary(effect) {
  const { current, baseline } = filteredMetrics(effect);
  return `<div class="effect-denominator-note">${icon('info')}六项指标的适用场景和分母不同，不能相加；点击卡片查看计算口径。</div><section class="effect-metric-grid">${metricKeys.map((key) => metricCard(effect, key, current[key], baseline[key])).join('')}</section>`;
}

function trendPanel(effect) {
  const buttons = metricKeys.map((key) => `<button class="effect-legend ${view.visibleMetrics.has(key) ? 'active' : ''}" type="button" data-toggle-metric="${key}"><i style="background:${metricDefinitions[key].color}"></i>${escapeHtml(metricDefinitions[key].shortLabel)}</button>`).join('');
  return `<section class="panel effect-trend-panel"><header class="panel-header"><div class="panel-header-main"><h2>上线前后趋势</h2><p>选择指标并点击节点查看当日口径</p></div><div class="panel-header-actions"><div class="segmented"><button type="button" data-grain="day" class="${view.grain === 'day' ? 'active' : ''}">按日</button><button type="button" data-grain="week" class="${view.grain === 'week' ? 'active' : ''}">按周</button></div></div></header><div class="panel-body"><div class="effect-chart-toolbar">${buttons}<span>百分比统一使用左轴</span></div>${trendChart(effect)}</div></section>`;
}

function dimensionPanel(effect) {
  const rows = effect.dimensions[view.dimension];
  const tabs = Object.entries(dimensionLabels).map(([key, label]) => `<button type="button" data-dimension="${key}" class="${view.dimension === key ? 'active' : ''}">${escapeHtml(label)}</button>`).join('');
  const tableRows = rows.map((row) => `<tr class="effect-dimension-row" data-dimension-row="${row.id}"><td><button type="button"><strong>${escapeHtml(row.name)}</strong><small>${row.id}</small></button></td><td>${row.samples.toLocaleString()}</td><td><strong>${row.selfResolved.toFixed(1)}%</strong></td><td class="${row.unresolved > 19 ? 'danger-text' : ''}">${row.unresolved.toFixed(1)}%</td><td class="${row.repeatQuery > 15 ? 'danger-text' : ''}">${row.repeatQuery.toFixed(1)}%</td><td class="${row.negativeFeedback > 8 ? 'danger-text' : ''}">${row.negativeFeedback.toFixed(1)}%</td><td>${row.taskCompletion.toFixed(1)}%</td><td>${row.adoption.toFixed(1)}%</td><td><span class="badge ${row.failures > 15 ? 'warning' : 'neutral'}">${row.failures} 条</span></td></tr>`).join('');
  return `<section class="panel effect-dimension-panel"><header class="panel-header"><div class="panel-header-main"><h2>维度拆分</h2><p>点击一行应用筛选并下钻失败案例</p></div><div class="segmented">${tabs}</div></header><div class="data-table-wrap"><table class="data-table effect-dimension-table"><thead><tr><th>${dimensionLabels[view.dimension]}</th><th>样本</th><th>自助解决</th><th>未解决</th><th>重复提问</th><th>负反馈</th><th>任务完成</th><th>答案采纳</th><th>失败案例</th></tr></thead><tbody>${tableRows}</tbody></table></div></section>`;
}

function experimentPanel(effect) {
  const experiment = effect.experiment;
  const rows = metricKeys.map((key) => {
    const definition = metricDefinitions[key];
    const a = experiment.control[key]; const b = experiment.treatment[key]; const diff = b - a;
    const improved = definition.direction === 'up' ? diff >= 0 : diff <= 0;
    return [definition.label, a, b, `${diff > 0 ? '+' : ''}${diff.toFixed(1)}pp`, improved];
  });
  const status = experiment.status === 'running' ? badge('running', '分流中') : badge('paused', '已暂停');
  return `<section class="panel effect-experiment-panel"><header class="panel-header"><div class="panel-header-main"><h2>A/B 实验</h2><p>${escapeHtml(experiment.name)} · 50/50 稳定分桶</p></div><div class="panel-header-actions">${status}<button class="button secondary small" type="button" id="experimentDetail">${icon('eye')}详情</button><button class="button ${experiment.status === 'running' ? 'danger-outline' : 'primary'} small" type="button" id="toggleExperiment">${icon(experiment.status === 'running' ? 'pause' : 'play')}${experiment.status === 'running' ? '暂停分流' : '恢复分流'}</button></div></header><div class="panel-body"><div class="experiment-variants"><article><span>A 基线组</span><strong class="mono">${escapeHtml(experiment.control.version)}</strong><small>${experiment.control.samples.toLocaleString()} 会话</small></article><span class="experiment-confidence"><strong>${experiment.confidence}%</strong><small>置信度</small></span><article><span>B 候选组</span><strong class="mono">${escapeHtml(experiment.treatment.version)}</strong><small>${experiment.treatment.samples.toLocaleString()} 会话</small></article></div><div class="experiment-metrics">${rows.map(([label, a, b, delta, improved]) => `<div><span>${escapeHtml(label)}</span><strong>${a}%</strong><span>${icon('arrowRight')}</span><strong>${b}%</strong><em class="${improved ? 'positive' : 'negative'}">${delta}</em></div>`).join('')}</div><div class="effect-guardrails"><span>${icon('shield')}安全护栏</span><strong>ACL 泄漏 0</strong><strong>高风险错答 0</strong><strong>重复副作用 0</strong><strong>P95 ${experiment.treatment.p95}s</strong></div></div></section>`;
}

function filteredFailures(effect) {
  return effect.failures.filter((item) => (view.tenant === 'all' || item.tenantId === view.tenant) && (view.business === 'all' || item.businessId === view.business) && (view.issue === 'all' || item.issueId === view.issue));
}

function failuresPanel(effect) {
  const failures = filteredFailures(effect);
  const rows = failures.map((item) => `<tr><td><button class="table-link-block" type="button" data-failure="${item.id}"><strong class="mono">${item.id}</strong><small>${escapeHtml(item.time)} · ${item.group} 组</small></button></td><td><strong>${escapeHtml(item.business)}</strong><small>${escapeHtml(item.tenant)}</small></td><td>${escapeHtml(item.reason)}</td><td>${badge(item.risk === 'high' ? 'failed' : item.risk === 'medium' ? 'warning' : 'neutral', item.risk === 'high' ? '高风险' : item.risk === 'medium' ? '中风险' : '低风险')}</td><td><strong>${escapeHtml(failureResultLabels[item.metric] || '指标异常')}</strong>${item.ticketId ? `<small>${escapeHtml(item.ticketId)}</small>` : ''}</td><td><button class="icon-button compact" type="button" data-failure="${item.id}" aria-label="查看失败详情" title="查看详情">${icon('eye')}</button></td></tr>`).join('');
  return `<section class="panel effect-failure-panel" id="effectFailures"><header class="panel-header"><div class="panel-header-main"><h2>失败案例明细</h2><p>${failures.length} 条当前筛选案例 · 展示脱敏问题、可观测用户行为与调用链</p></div><button class="button secondary small" type="button" id="clearFailureFilter">${icon('refresh')}清除筛选</button></header>${failures.length ? `<div class="data-table-wrap"><table class="data-table effect-failure-table"><thead><tr><th style="width:18%">会话</th><th style="width:20%">业务场景</th><th style="width:31%">失败原因</th><th style="width:12%">风险</th><th style="width:11%">观测结果</th><th style="width:8%"></th></tr></thead><tbody>${rows}</tbody></table></div>` : '<div class="table-empty"><strong>当前筛选没有失败案例</strong><p>可清除筛选查看全部脱敏样本。</p></div>'}</section>`;
}

function ruleStatus(rule) {
  if (!rule.enabled || rule.status === 'disabled') return badge('canceled', '已停用');
  if (rule.status === 'watching') return badge('warning', '观察中');
  if (rule.status === 'tested') return badge('running', '演练通过');
  return badge('success', '正常');
}

function alertRulesPanel(effect) {
  const percentMetrics = new Set(metricKeys);
  const rows = effect.alertRules.map((rule) => `<tr><td><strong>${escapeHtml(rule.name)}</strong><small>${escapeHtml(rule.channel)} · ${escapeHtml(relativeTime(rule.lastCheckedAt))}</small></td><td><strong>${escapeHtml(alertMetricLabels[rule.metric] || rule.metric)} ${escapeHtml(rule.operator)} ${rule.threshold}${percentMetrics.has(rule.metric) ? '%' : ''}</strong><small>${rule.window} / 最少 ${rule.minSamples} 样本 / 连续 ${rule.consecutive} 次</small></td><td><strong>${escapeHtml(actionLabels[rule.action])}</strong>${rule.rollbackVersion ? `<small class="mono">目标 ${escapeHtml(rule.rollbackVersion)}</small>` : ''}</td><td>${escapeHtml(rule.owner)}</td><td>${ruleStatus(rule)}</td><td><div class="table-actions"><label class="switch" title="启用或停用规则"><input type="checkbox" data-rule-toggle="${rule.id}" ${rule.enabled ? 'checked' : ''}><span></span></label><button class="icon-button compact" type="button" data-rule-test="${rule.id}" aria-label="演练规则" title="演练">${icon('play')}</button><button class="icon-button compact" type="button" data-rule-edit="${rule.id}" aria-label="编辑规则" title="编辑">${icon('edit')}</button></div></td></tr>`).join('');
  return `<section class="panel effect-alert-panel"><header class="panel-header"><div class="panel-header-main"><h2>告警与自动回滚</h2><p>先满足最小样本，再按连续窗口判定；安全硬护栏例外</p></div><button class="button primary small" type="button" id="newAlertRule">${icon('plus')}新建规则</button></header><div class="data-table-wrap"><table class="data-table effect-rule-table"><thead><tr><th style="width:24%">规则</th><th style="width:23%">触发条件</th><th style="width:17%">执行动作</th><th style="width:13%">负责人</th><th style="width:10%">状态</th><th style="width:13%"></th></tr></thead><tbody>${rows}</tbody></table></div></section>`;
}

export function renderOnlineEffect(state) {
  const effect = state.onlineEffect;
  return `${pageHeader({ title: '上线效果', description: '观察 RAG 版本对搜索推广 CRM 自助解决、任务完成和答案采纳的实际影响。', actions: `<button class="button secondary" type="button" id="refreshEffect">${icon('refresh')}刷新指标</button><button class="button primary" type="button" id="headerNewAlert">${icon('sliders')}配置告警</button>` })}${topFilters(effect)}${metricSummary(effect)}<div class="effect-primary-grid">${trendPanel(effect)}${experimentPanel(effect)}</div>${dimensionPanel(effect)}${failuresPanel(effect)}${alertRulesPanel(effect)}<div class="notice info page-note">${icon('database')}<div><strong>数据边界</strong><span>页面按 18 个 workspace、190 DAU、约 4,600 次日问答构造教学数据。指标来自 RAG 与 CRM 系统内事件；员工后续是否转去如流求助当前不可观测，也不会被推断为任何指标。刷新页面恢复默认状态。</span></div></div>`;
}

function showMetricDrawer(effect, key) {
  const definition = metricDefinitions[key];
  const { current, baseline } = filteredMetrics(effect);
  const counts = metricCounts(effect, key, current[key]);
  const failures = filteredFailures(effect).filter((item) => item.metric === key).length;
  openDrawer({
    title: definition.label,
    subtitle: '指标口径与当前样本',
    body: `<div class="metric-detail-hero"><strong>${current[key].toFixed(1)}%</strong><span>基线 ${baseline[key].toFixed(1)}%</span></div><dl class="detail-list"><div><dt>分子</dt><dd>${counts.numerator.toLocaleString()} 次</dd></div><div><dt>分母</dt><dd>${counts.denominator.toLocaleString()} ${escapeHtml(counts.unit)}</dd></div><div><dt>当前失败明细</dt><dd>${failures} 条脱敏样本</dd></div><div><dt>数据源</dt><dd>${escapeHtml(definition.source)}</dd></div></dl><section class="form-section"><h3 class="section-title">计算公式</h3><p class="section-copy">${escapeHtml(definition.formula)}</p><h3 class="section-title">排除项</h3><p class="section-copy">${escapeHtml(definition.excludes)}</p></section>`,
    actions: [{ label: '查看失败明细', icon: 'search', onClick: () => window.setTimeout(() => document.getElementById('effectFailures')?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 0) }],
  });
}

function showTrendDrawer(effect, index, metricKey) {
  const point = trendPoints(effect)[index];
  const definition = metricDefinitions[metricKey];
  const details = metricKeys.map((key) => `<div><dt>${escapeHtml(metricDefinitions[key].label)}</dt><dd>${point[key].toFixed(1)}%</dd></div>`).join('');
  openDrawer({ title: point.date, subtitle: `${definition.label}节点`, body: `<div class="metric-detail-hero"><strong>${point[metricKey].toFixed(1)}%</strong><span>${point.questions.toLocaleString()} 次 RAG 问答</span></div><dl class="detail-list">${details}<div><dt>P95 完整响应</dt><dd>${point.p95.toFixed(2)} 秒</dd></div></dl>${point.release ? `<div class="notice info form-section">${icon('rocket')}<div><strong>版本上线点</strong><span>${escapeHtml(effect.scope.currentVersion)} 开始接收候选组流量。</span></div></div>` : ''}` });
}

function showExperimentDrawer(effect) {
  const exp = effect.experiment;
  openDrawer({ title: exp.name, subtitle: `${exp.id} · ${exp.status === 'running' ? '分流中' : '已暂停'}`, body: `<dl class="detail-list"><div><dt>实验负责人</dt><dd>${escapeHtml(exp.owner)}</dd></div><div><dt>开始时间</dt><dd>2026-09-01 09:00</dd></div><div><dt>分桶单元</dt><dd>workspace_id + user_id</dd></div><div><dt>流量分配</dt><dd>A 50% / B 50%</dd></div><div><dt>统计置信度</dt><dd>${exp.confidence}%</dd></div><div><dt>已入组会话</dt><dd>${(exp.control.samples + exp.treatment.samples).toLocaleString()}</dd></div></dl><section class="form-section"><h3 class="section-title">入组与排除规则</h3><p class="section-copy">同一用户在实验期间固定分组。排除内部压测、请求重放和机器人流量；六项业务指标分别按自己的适用会话计算。</p><h3 class="section-title">结论规则</h3><p class="section-copy">自助解决率和任务完成率为主指标，未解决、重复提问、负反馈和答案采纳用于交叉验证；ACL 泄漏、高风险错答与重复副作用是不可抵消的硬护栏。</p></section>` });
}

function showFailureDrawer(effect, failureId) {
  const item = effect.failures.find((failure) => failure.id === failureId);
  if (!item) return;
  openDrawer({
    title: item.id,
    subtitle: `${item.time} · ${item.tenant} · ${item.group} 组`,
    body: `<div class="failure-question"><span>${badge(item.risk === 'high' ? 'failed' : item.risk === 'medium' ? 'warning' : 'neutral', item.risk === 'high' ? '高风险' : item.risk === 'medium' ? '中风险' : '低风险')}</span><strong>${escapeHtml(item.query)}</strong></div><section class="form-section"><h3 class="section-title">系统回答</h3><p class="section-copy">${escapeHtml(item.answer)}</p><h3 class="section-title">引用证据</h3><p class="section-copy">${escapeHtml(item.citation)}</p></section><div class="notice ${item.risk === 'high' ? 'warning' : 'info'}">${icon('alert')}<div><strong>${escapeHtml(item.reason)}</strong><span>${escapeHtml(item.action)}</span></div></div><section class="form-section"><h3 class="section-title">调用链</h3><ol class="trace-steps">${item.trace.map((step, index) => `<li><span>${index + 1}</span><strong>${escapeHtml(step)}</strong></li>`).join('')}</ol></section>${item.ticketId ? `<div class="notice success form-section">${icon('checkCircle')}<div><strong>已创建改进任务 ${escapeHtml(item.ticketId)}</strong><span>负责人：${escapeHtml(item.ticketOwner)} · 状态：待处理</span></div></div>` : ''}`,
    actions: item.ticketId ? [] : [{ label: '创建改进任务', variant: 'primary', icon: 'clipboard', busyText: '创建中', onClick: async () => { await createOnlineFailureTicket(item.id); toast('已创建改进任务并写入审计日志', 'success'); } }],
  });
}

function alertRuleModal(effect, rule = null) {
  const value = (key, fallback = '') => escapeHtml(String(rule?.[key] ?? fallback));
  openModal({
    title: rule ? '编辑告警规则' : '新建告警规则',
    subtitle: '阈值必须同时绑定统计窗口、最小样本和连续触发次数。',
    body: `<div class="form-grid"><label class="field span-full"><span>规则名称 <b>*</b></span><input id="ruleName" value="${value('name', '新版上线效果护栏')}"></label><label class="field"><span>指标</span><select id="ruleMetric">${Object.entries(alertMetricLabels).map(([key, label]) => `<option value="${key}" ${rule?.metric === key ? 'selected' : ''}>${escapeHtml(label)}</option>`).join('')}</select></label><label class="field"><span>判定</span><div class="rule-condition-input"><select id="ruleOperator"><option value="<" ${rule?.operator === '<' ? 'selected' : ''}>低于</option><option value=">" ${rule?.operator === '>' ? 'selected' : ''}>高于</option></select><input id="ruleThreshold" type="number" step="0.1" min="0" value="${value('threshold', 76)}"></div></label><label class="field"><span>统计窗口</span><select id="ruleWindow">${['1 分钟', '5 分钟', '30 分钟', '1 小时'].map((item) => `<option ${rule?.window === item ? 'selected' : ''}>${item}</option>`).join('')}</select></label><label class="field"><span>最小样本数</span><input id="ruleMinSamples" type="number" min="1" value="${value('minSamples', 300)}"></label><label class="field"><span>连续异常窗口</span><input id="ruleConsecutive" type="number" min="1" max="10" value="${value('consecutive', 2)}"></label><label class="field"><span>执行动作</span><select id="ruleAction"><option value="alert" ${rule?.action === 'alert' ? 'selected' : ''}>仅告警</option><option value="pause" ${rule?.action === 'pause' ? 'selected' : ''}>暂停候选组分流</option><option value="rollback" ${rule?.action === 'rollback' ? 'selected' : ''}>自动回滚</option></select></label><label class="field" id="rollbackField"><span>回滚目标</span><select id="ruleRollback"><option value="rag_docs_20260828">rag_docs_20260828</option><option value="rag_docs_20260820">rag_docs_20260820</option></select></label><label class="field"><span>负责人</span><input id="ruleOwner" value="${value('owner', '知识运营')}"></label><label class="field"><span>通知渠道</span><select id="ruleChannel"><option ${rule?.channel === '监控群' ? 'selected' : ''}>监控群</option><option ${rule?.channel === '电话 + IM' ? 'selected' : ''}>电话 + IM</option><option ${rule?.channel === '邮件 + IM' ? 'selected' : ''}>邮件 + IM</option></select></label></div><div class="notice warning form-section">${icon('shield')}<div><strong>自动回滚不看单个波动点</strong><span>除 ACL 泄漏和高风险错答外，必须先满足最小样本，再连续多个窗口越界才执行。</span></div></div>`,
    actions: [{ label: '取消' }, { label: '保存规则', variant: 'primary', icon: 'check', busyText: '保存中', onClick: async (modal) => {
      const name = modal.querySelector('#ruleName').value.trim(); const threshold = modal.querySelector('#ruleThreshold').value;
      if (!name || threshold === '') { toast('请填写规则名称和阈值', 'warning'); return false; }
      await saveOnlineAlertRule({ id: rule?.id, name, metric: modal.querySelector('#ruleMetric').value, operator: modal.querySelector('#ruleOperator').value, threshold, window: modal.querySelector('#ruleWindow').value, minSamples: modal.querySelector('#ruleMinSamples').value, consecutive: modal.querySelector('#ruleConsecutive').value, action: modal.querySelector('#ruleAction').value, rollbackVersion: modal.querySelector('#ruleRollback').value, owner: modal.querySelector('#ruleOwner').value.trim() || '知识运营', channel: modal.querySelector('#ruleChannel').value });
      toast('告警规则已保存', 'success');
    } }],
    onMount: (modal) => {
      const action = modal.querySelector('#ruleAction'); const field = modal.querySelector('#rollbackField');
      const sync = () => field.classList.toggle('hidden', action.value !== 'rollback');
      action.addEventListener('change', sync); sync();
      if (rule?.rollbackVersion) modal.querySelector('#ruleRollback').value = rule.rollbackVersion;
    },
  });
}

function setViewFilter(dimension, value, rerender) {
  view[dimension] = value;
  rerender();
}

export function mountOnlineEffect(root, state, rerender) {
  const effect = state.onlineEffect;
  root.querySelector('#refreshEffect').addEventListener('click', () => toast(`指标已刷新 · ${new Date().toLocaleTimeString('zh-CN', { hour12: false })}`, 'success'));
  root.querySelector('#headerNewAlert').addEventListener('click', () => alertRuleModal(effect));
  root.querySelector('#newAlertRule').addEventListener('click', () => alertRuleModal(effect));
  root.querySelector('#effectDays').addEventListener('change', (event) => { view.days = Number(event.target.value); rerender(); });
  root.querySelector('#effectVersion').addEventListener('change', (event) => { view.versionMode = event.target.value; rerender(); });
  root.querySelector('#effectTenant').addEventListener('change', (event) => setViewFilter('tenant', event.target.value, rerender));
  root.querySelector('#effectBusiness').addEventListener('change', (event) => setViewFilter('business', event.target.value, rerender));
  root.querySelector('#effectIssue').addEventListener('change', (event) => setViewFilter('issue', event.target.value, rerender));
  root.querySelector('#effectReset').addEventListener('click', () => { Object.assign(view, { days: 14, grain: 'day', versionMode: 'compare', tenant: 'all', business: 'all', issue: 'all', dimension: 'tenant' }); view.visibleMetrics = new Set(['selfResolved', 'unresolved', 'taskCompletion']); rerender(); });
  root.querySelectorAll('[data-metric-card]').forEach((button) => button.addEventListener('click', () => showMetricDrawer(effect, button.dataset.metricCard)));
  root.querySelectorAll('[data-grain]').forEach((button) => button.addEventListener('click', () => { view.grain = button.dataset.grain; rerender(); }));
  root.querySelectorAll('[data-toggle-metric]').forEach((button) => button.addEventListener('click', () => { const key = button.dataset.toggleMetric; if (view.visibleMetrics.has(key) && view.visibleMetrics.size === 1) { toast('至少保留一条趋势线', 'warning'); return; } view.visibleMetrics.has(key) ? view.visibleMetrics.delete(key) : view.visibleMetrics.add(key); rerender(); }));
  root.querySelectorAll('[data-trend-index]').forEach((point) => { const open = () => showTrendDrawer(effect, Number(point.dataset.trendIndex), point.dataset.trendMetric); point.addEventListener('click', open); point.addEventListener('keydown', (event) => { if (event.key === 'Enter' || event.key === ' ') open(); }); });
  root.querySelectorAll('[data-dimension]').forEach((button) => button.addEventListener('click', () => { view.dimension = button.dataset.dimension; rerender(); }));
  root.querySelectorAll('[data-dimension-row]').forEach((row) => row.addEventListener('click', () => { view[view.dimension] = row.dataset.dimensionRow; rerender(); window.setTimeout(() => document.getElementById('effectFailures')?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 0); }));
  root.querySelector('#experimentDetail').addEventListener('click', () => showExperimentDrawer(effect));
  root.querySelector('#toggleExperiment').addEventListener('click', async () => { const pausing = effect.experiment.status === 'running'; const confirmed = await confirmAction({ title: pausing ? '暂停 A/B 实验' : '恢复 A/B 实验', message: pausing ? '停止新会话进入候选组？' : '恢复 50% 候选组分流？', confirmLabel: pausing ? '确认暂停' : '确认恢复', danger: pausing, detail: '已入组会话保持原分组，操作会写入权限审计。' }); if (confirmed) { await toggleOnlineExperiment(); toast(pausing ? 'A/B 实验已暂停' : 'A/B 实验已恢复', 'success'); } });
  root.querySelector('#clearFailureFilter').addEventListener('click', () => { view.tenant = 'all'; view.business = 'all'; view.issue = 'all'; rerender(); });
  root.querySelectorAll('[data-failure]').forEach((button) => button.addEventListener('click', () => showFailureDrawer(effect, button.dataset.failure)));
  root.querySelectorAll('[data-rule-edit]').forEach((button) => button.addEventListener('click', () => alertRuleModal(effect, effect.alertRules.find((item) => item.id === button.dataset.ruleEdit))));
  root.querySelectorAll('[data-rule-toggle]').forEach((input) => input.addEventListener('change', async () => { try { await toggleOnlineAlertRule(input.dataset.ruleToggle); toast(input.checked ? '告警规则已启用' : '告警规则已停用', 'success'); } catch (error) { input.checked = !input.checked; toast(error.message, 'danger'); } }));
  root.querySelectorAll('[data-rule-test]').forEach((button) => button.addEventListener('click', async () => { const confirmed = await confirmAction({ title: '执行告警规则演练', message: '使用模拟异常样本验证触发链路？', confirmLabel: '开始演练', detail: '演练会验证通知、暂停或回滚参数，但不会真实切换线上 Collection 别名。' }); if (confirmed) { await simulateOnlineAlertRule(button.dataset.ruleTest); toast('规则演练通过，未执行真实回滚', 'success'); } }));
  return null;
}
