import { icon } from '../core/icons.js';
import { cancelJob, retryJob } from '../core/mock-api.js';
import { navigate } from '../core/router.js';
import { badge, confirmAction, emptyState, openDrawer, pageHeader, pagination, toast } from '../components/ui.js';
import { escapeHtml, relativeTime } from '../core/utils.js';

const view = { query: '', status: 'all', type: 'all' };
let openedJobQuery = '';
let filterTimer;

function needsManualReview(job) {
  return job.status === 'failed' && job.reviewRequired && job.reviewStatus !== 'completed';
}

function statusAction(job) {
  if (needsManualReview(job)) return `<button class="button primary small" type="button" data-job-review="${job.id}">${icon('clipboard')}人工复核</button>`;
  if (['failed', 'canceled'].includes(job.status)) return `<button class="button secondary small" type="button" data-job-retry="${job.id}">${icon('refresh')}从断点重试</button>`;
  if (['running', 'queued'].includes(job.status)) return `<button class="button danger-outline small" type="button" data-job-cancel="${job.id}">${icon('x')}取消</button>`;
  if (job.candidateVersionId) return `<button class="button secondary small" type="button" data-version-open="${job.candidateVersionId}">${icon('boxes')}查看版本</button>`;
  return '';
}

function jobDetail(job) {
  const diffTotal = job.added + job.updated + job.removed;
  const reviewNotice = job.reviewRequired
    ? job.reviewStatus === 'completed'
      ? `<div class="notice success form-section">${icon('checkCircle')}<div><strong>人工复核已经提交</strong><span>内容阻断已解除。复核不会自动恢复执行，请确认后从 checkpoint 重试。</span></div></div>`
      : `<div class="notice warning form-section">${icon('clipboard')}<div><strong>需要人工判断 3 个复杂表格</strong><span>先对照 Wiki 原表和解析文本，逐项选择修正、排除或升级；全部提交后才允许重试。</span></div></div>`
    : '';
  const actions = needsManualReview(job)
    ? [{ label: '进入人工复核', variant: 'primary', icon: 'clipboard', onClick: () => navigate('/jobs/review', { job: job.id }) }]
    : job.status === 'failed' || job.status === 'canceled'
      ? [{ label: '从断点重试', variant: 'primary', icon: 'refresh', busyText: '恢复中', onClick: async () => { await retryJob(job.id); toast('任务已从 checkpoint 恢复', 'success'); } }]
      : job.candidateVersionId
        ? [{ label: '查看候选版本', variant: 'primary', icon: 'boxes', onClick: () => navigate('/versions', { version: job.candidateVersionId }) }]
        : [];
  openDrawer({
    title: job.runId, subtitle: `${job.sourceName} · ${job.type === 'versioned' ? '版本化摄取' : '增量摄取'}`,
    body: `${job.error ? `<div class="notice danger">${icon('alert')}<div><strong>任务在 ${escapeHtml(job.stage)} 阶段被阻断</strong><span>${escapeHtml(job.error)}</span></div></div>` : ''}${reviewNotice}<div class="summary-grid form-section"><div><span>状态</span>${badge(job.status)}</div><div><span>执行进度</span><strong>${job.progress}%</strong></div><div><span>执行次数</span><strong>${job.attempts}</strong></div><div><span>最近更新</span><strong>${escapeHtml(relativeTime(job.updatedAt))}</strong></div></div><div class="form-section"><div class="progress ${job.status === 'failed' ? 'danger' : job.status === 'completed' ? 'success' : ''}"><span style="width:${job.progress}%"></span></div></div><dl class="detail-list form-section"><div><dt>新增</dt><dd>+${job.added}</dd></div><div><dt>更新</dt><dd>${job.updated}</dd></div><div><dt>删除</dt><dd>-${job.removed}</dd></div><div><dt>未变化</dt><dd>${job.unchanged}</dd></div></dl><section class="form-section"><h3 class="section-title">执行日志</h3><ol class="timeline">${job.logs.map((log, index) => `<li><span class="timeline-dot ${job.status === 'failed' && index === job.logs.length - 1 ? 'warning' : ''}"></span><div><strong>${escapeHtml(log.slice(0, 8))}</strong><p>${escapeHtml(log.slice(9))}</p></div></li>`).join('')}</ol></section>${diffTotal > 0 ? `<div class="notice info form-section">${icon('clipboard')}<div><strong>变更计划已固定</strong><span>重试会从 checkpoint 继续，使用相同 run_id 和幂等操作标识，不会重复写入。</span></div></div>` : ''}`,
    actions,
  });
}

export function renderJobs(state, route) {
  const q = view.query.toLowerCase();
  const sourceFilter = route?.query?.get('source');
  const rows = state.jobs.filter((job) => (!sourceFilter || job.sourceId === sourceFilter) && (view.status === 'all' || job.status === view.status) && (view.type === 'all' || job.type === view.type) && (!q || `${job.runId} ${job.sourceName} ${job.operator}`.toLowerCase().includes(q)));
  return `${pageHeader({ title: '摄取任务', description: '观察从扫描、治理、切分到 Collection 构建的完整执行链路，并从 checkpoint 恢复失败任务。', actions: `<button class="button secondary" type="button" id="refreshJobs">${icon('refresh')}刷新状态</button><button class="button primary" type="button" id="createJob">${icon('plus')}新建任务</button>` })}<section class="panel"><div class="filter-bar"><label class="filter-search">${icon('search')}<input id="jobSearch" type="search" value="${escapeHtml(view.query)}" placeholder="搜索 run_id、来源或操作人"></label><label class="filter-control"><span>运行状态</span><select id="jobStatus"><option value="all">全部状态</option>${['running','completed','failed','canceled','queued'].map((value) => `<option value="${value}" ${view.status === value ? 'selected' : ''}>${badge(value).replace(/<[^>]+>/g, '')}</option>`).join('')}</select></label><label class="filter-control"><span>任务类型</span><select id="jobType"><option value="all">全部类型</option><option value="incremental" ${view.type === 'incremental' ? 'selected' : ''}>增量摄取</option><option value="versioned" ${view.type === 'versioned' ? 'selected' : ''}>版本化摄取</option></select></label>${sourceFilter ? `<button class="button ghost small" type="button" id="clearSourceFilter">清除来源限定</button>` : '<button class="button ghost small" type="button" id="resetJobFilters">重置</button>'}</div><div class="data-table-wrap"><table class="data-table"><thead><tr><th style="width:24%">任务 / 来源</th><th style="width:12%">状态</th><th style="width:23%">阶段与进度</th><th style="width:15%">变更</th><th style="width:12%">操作人</th><th style="width:14%">操作</th></tr></thead><tbody>${rows.map((job) => `<tr><td><button class="table-link-block" type="button" data-job-open="${job.id}"><strong>${escapeHtml(job.runId)}</strong><small>${escapeHtml(job.sourceName)}</small></button></td><td>${badge(job.status)}</td><td><div class="progress-cell"><span><i style="width:${job.progress}%"></i></span><small>${escapeHtml(job.stage)} · ${job.progress}%</small></div></td><td><strong class="diff-positive">+${job.added}</strong> / ${job.updated} / <span class="diff-negative">-${job.removed}</span><small>新增 / 更新 / 删除</small></td><td><strong>${escapeHtml(job.operator)}</strong><small>${escapeHtml(relativeTime(job.updatedAt))}</small></td><td><div class="table-actions">${statusAction(job)}<button class="icon-button compact" type="button" data-job-open="${job.id}" aria-label="查看详情" title="查看详情">${icon('eye')}</button></div></td></tr>`).join('') || `<tr><td colspan="6">${emptyState('没有匹配的摄取任务', '调整筛选条件或从知识源创建一个新任务。')}</td></tr>`}</tbody></table></div>${pagination(rows.length, '个任务')}</section>`;
}

export function mountJobs(root, state, rerender, route) {
  const apply = () => { view.query = root.querySelector('#jobSearch').value; view.status = root.querySelector('#jobStatus').value; view.type = root.querySelector('#jobType').value; rerender(); };
  root.querySelector('#jobSearch').addEventListener('input', () => { window.clearTimeout(filterTimer); filterTimer = window.setTimeout(apply, 180); }); root.querySelector('#jobStatus').addEventListener('change', apply); root.querySelector('#jobType').addEventListener('change', apply);
  root.querySelector('#refreshJobs').addEventListener('click', () => { rerender(); toast('任务状态已刷新', 'success'); });
  root.querySelector('#createJob').addEventListener('click', () => navigate('/sources'));
  root.querySelector('#resetJobFilters')?.addEventListener('click', () => { view.query = ''; view.status = 'all'; view.type = 'all'; rerender(); });
  root.querySelector('#clearSourceFilter')?.addEventListener('click', () => navigate('/jobs'));
  root.querySelectorAll('[data-job-open]').forEach((button) => button.addEventListener('click', () => jobDetail(state.jobs.find((item) => item.id === button.dataset.jobOpen))));
  root.querySelectorAll('[data-job-review]').forEach((button) => button.addEventListener('click', () => navigate('/jobs/review', { job: button.dataset.jobReview })));
  root.querySelectorAll('[data-job-retry]').forEach((button) => button.addEventListener('click', async () => { button.disabled = true; try { await retryJob(button.dataset.jobRetry); toast('任务已从 checkpoint 恢复', 'success'); } catch (error) { button.disabled = false; toast(error.message, 'danger'); } }));
  root.querySelectorAll('[data-job-cancel]').forEach((button) => button.addEventListener('click', async () => { const job = state.jobs.find((item) => item.id === button.dataset.jobCancel); const yes = await confirmAction({ title: '取消摄取任务', message: `确认取消 ${job.runId}？`, confirmLabel: '取消任务', danger: true, detail: '已完成的 checkpoint 会保留，可稍后从断点重试。' }); if (yes) { await cancelJob(job.id); toast('任务已取消', 'success'); } }));
  root.querySelectorAll('[data-version-open]').forEach((button) => button.addEventListener('click', () => navigate('/versions', { version: button.dataset.versionOpen })));
  const requested = route?.query?.get('job');
  if (!requested) openedJobQuery = '';
  if (requested && requested !== openedJobQuery) {
    openedJobQuery = requested;
    const job = state.jobs.find((item) => item.id === requested);
    if (job) window.setTimeout(() => jobDetail(job), 0);
  }
}
