import { icon } from '../core/icons.js';
import { navigate } from '../core/router.js';
import { badge, panel, pageHeader, statCard } from '../components/ui.js';
import { escapeHtml, formatNumber, relativeTime } from '../core/utils.js';

export function renderOverview(state) {
  const active = state.versions.find((item) => item.status === 'active');
  const running = state.jobs.filter((item) => ['queued', 'running'].includes(item.status));
  const failures = state.jobs.filter((item) => item.status === 'failed');
  const reviewFailure = failures.find((item) => item.reviewRequired && item.reviewStatus !== 'completed');
  const failureRoute = reviewFailure ? `/jobs/review?job=${reviewFailure.id}` : '/jobs';
  const candidate = state.versions.find((item) => item.status === 'candidate');
  const totalDocuments = state.sources.reduce((sum, item) => sum + item.documents, 0);
  const totalChunks = state.sources.reduce((sum, item) => sum + item.chunks, 0);
  const recentRows = state.jobs.slice(0, 5).map((job) => `<tr><td><button class="table-link" type="button" data-job-id="${job.id}">${escapeHtml(job.runId)}</button><small>${escapeHtml(job.sourceName)}</small></td><td>${badge(job.status)}</td><td><div class="progress-cell"><span><i style="width:${job.progress}%"></i></span><small>${job.progress}% · ${escapeHtml(job.stage)}</small></div></td><td>${escapeHtml(relativeTime(job.updatedAt))}</td><td><button class="icon-button compact" type="button" data-job-id="${job.id}" aria-label="查看任务" title="查看任务">${icon('chevronRight')}</button></td></tr>`).join('');
  return `${pageHeader({ title: '运营总览', description: '掌握 CRM 知识资产、摄取运行和线上版本的实时状态。', actions: `<button class="button secondary" type="button" data-route="/quality">${icon('activity')}质量报告</button><button class="button primary" type="button" data-route="/sources/new">${icon('plus')}接入知识源</button>` })}
    <section class="stat-grid">
      ${statCard({ label: '有效知识源', value: state.sources.filter((item) => item.status !== 'archived').length, hint: `${state.sources.filter((item) => item.health === 'warning').length} 个需关注`, iconName: 'file', tone: 'blue', trend: '+1 本月' })}
      ${statCard({ label: '文档资产', value: formatNumber(totalDocuments), hint: `${formatNumber(totalChunks)} chunks`, iconName: 'database', tone: 'cyan', trend: '+2.4%' })}
      ${statCard({ label: '执行中任务', value: running.length, hint: `${failures.length} 个失败待处理`, iconName: 'history', tone: 'amber' })}
      ${statCard({ label: '线上质量分', value: active?.qualityScore?.toFixed(1) || '--', hint: '发布门禁 ≥ 90', iconName: 'activity', tone: 'green', trend: '+0.9' })}
    </section>
    <section class="release-strip">
      <div><small>线上别名</small><strong class="online">${escapeHtml(active?.alias || '--')} · 在线</strong></div>
      <div><small>当前 Collection</small><strong class="mono">${escapeHtml(active?.collection || '--')}</strong></div>
      <div><small>内容规模</small><strong>${formatNumber(active?.documents || 0)} 文档 / ${formatNumber(active?.chunks || 0)} chunks</strong></div>
      <div><small>发布质量</small><strong>${active?.qualityScore?.toFixed(1) || '--'} / 100</strong></div>
      <div><small>候选版本</small><strong>${candidate ? '1 个待发布' : '暂无候选'}</strong></div>
      <div><button class="button secondary small" type="button" data-route="/versions">管理版本 ${icon('chevronRight')}</button></div>
    </section>
    <div class="content-grid two">
      ${panel({ title: '最近摄取任务', description: '按最近更新时间排序', actions: `<button class="button ghost small" type="button" data-route="/jobs">查看全部 ${icon('chevronRight')}</button>`, flush: true, body: `<div class="table-wrap"><table><thead><tr><th>任务</th><th>状态</th><th>进度</th><th>更新时间</th><th></th></tr></thead><tbody>${recentRows}</tbody></table></div>` })}
      <div class="stack">
        ${panel({ title: '快捷操作', body: `<div class="quick-actions"><button class="quick-action" type="button" data-route="/sources/new"><span>${icon('upload')}</span><div><strong>接入知识源</strong><small>文件、Wiki 或对象存储</small></div>${icon('chevronRight')}</button><button class="quick-action" type="button" data-route="/quality"><span>${icon('activity')}</span><div><strong>发起质量评测</strong><small>验证召回与 ACL 隔离</small></div>${icon('chevronRight')}</button><button class="quick-action" type="button" data-route="/versions"><span>${icon('boxes')}</span><div><strong>发布候选版本</strong><small>${candidate ? candidate.collection : '当前没有候选版本'}</small></div>${icon('chevronRight')}</button><button class="quick-action" type="button" data-route="/audit"><span>${icon('shield')}</span><div><strong>导出审计证据</strong><small>按操作人与结果过滤</small></div>${icon('chevronRight')}</button></div>` })}
        ${panel({ title: '风险与待办', body: `<div class="risk-list"><button class="risk-item row-button" type="button" data-route="${failureRoute}"><span class="soft-red">${icon('alert')}</span><div><strong>${failures.length} 个摄取任务失败</strong><small>${reviewFailure ? '复杂表格检查阻断，进入人工复核' : '查看失败原因与恢复状态'}</small></div>${icon('chevronRight')}</button><button class="risk-item row-button" type="button" data-route="/versions"><span class="soft-amber">${icon('boxes')}</span><div><strong>${candidate ? '1 个版本等待发布' : '发布队列为空'}</strong><small>${candidate ? '质量门禁已通过，可发起别名切换' : '完成摄取与评测后生成候选版本'}</small></div>${icon('chevronRight')}</button><button class="risk-item row-button" type="button" data-route="/settings"><span class="soft-blue">${icon('key')}</span><div><strong>Wiki 凭据 7 天后轮换</strong><small>建议在低峰期完成连接验证</small></div>${icon('chevronRight')}</button></div>` })}
      </div>
    </div>`;
}

export function mountOverview(root) {
  root.querySelectorAll('[data-route]').forEach((button) => button.addEventListener('click', () => navigate(button.dataset.route)));
  root.querySelectorAll('[data-job-id]').forEach((button) => button.addEventListener('click', () => navigate('/jobs', { job: button.dataset.jobId })));
}
