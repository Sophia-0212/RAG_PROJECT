import { icon } from '../core/icons.js';
import { saveReviewDecision, submitManualReview } from '../core/mock-api.js';
import { navigate } from '../core/router.js';
import { badge, confirmAction, emptyState, pageHeader, toast } from '../components/ui.js';
import { escapeHtml, relativeTime } from '../core/utils.js';

let selectedItemId = '';
const drafts = new Map();

const decisionMeta = {
  normalize: { label: '修正后保留', icon: 'edit', description: '补全被合并单元格省略的上下文，生成可独立检索的知识文本。' },
  exclude: { label: '从本次摄取排除', icon: 'archive', description: '内容不适合进入检索库，保留原文但不生成 Chunk。' },
  escalate: { label: '升级解析规则', icon: 'settings', description: '业务影响高且结构无法可靠展开，交由解析工程处理。' },
};

function reviewStatus(status) {
  const values = {
    pending: ['待复核', 'warning'],
    in_progress: ['复核中', 'info'],
    ready_to_submit: ['待提交', 'violet'],
    completed: ['复核完成', 'success'],
  };
  const [label, tone] = values[status] || [status, 'neutral'];
  return badge(tone === 'violet' ? 'candidate' : tone, label);
}

function getDraft(item) {
  if (!drafts.has(item.id)) {
    drafts.set(item.id, {
      decision: item.decision || '',
      correctedText: item.correctedText || item.suggestedText,
      note: item.note || '',
    });
  }
  return drafts.get(item.id);
}

function applyDecision(item, draft, decision) {
  draft.decision = decision;
  if (decision === 'normalize') {
    draft.correctedText = draft.correctedText || item.suggestedText;
  } else {
    draft.note = item.decisionNotes?.[decision] || `本项选择“${decisionMeta[decision].label}”，保留原始证据并进入后续治理流程。`;
  }
}

function renderOriginalTable(original) {
  return `<div class="review-table-wrap"><table class="review-source-table"><thead><tr>${original.columns.map((column) => `<th>${escapeHtml(column)}</th>`).join('')}</tr></thead><tbody>${original.rows.map((row) => `<tr>${row.map((cell) => cell.skip ? '' : `<td${cell.rowSpan ? ` rowspan="${cell.rowSpan}"` : ''} class="${cell.flagged ? 'flagged' : ''}">${escapeHtml(cell.text)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
}

function queueItem(item, active) {
  const meta = item.decision ? decisionMeta[item.decision] : null;
  return `<button class="review-queue-item ${active ? 'active' : ''} ${item.status === 'resolved' ? 'resolved' : ''}" type="button" data-review-item="${item.id}" aria-current="${active ? 'true' : 'false'}"><span class="review-queue-index">${item.status === 'resolved' ? icon('check') : item.order}</span><span class="review-queue-copy"><strong>${escapeHtml(item.pageTitle)}</strong><small>${escapeHtml(item.location)}</small>${meta ? `<em>${escapeHtml(meta.label)}</em>` : '<em>等待处理决定</em>'}</span>${icon('chevronRight')}</button>`;
}

function decisionOption(value, draft, disabled) {
  const meta = decisionMeta[value];
  return `<button class="review-decision-option ${draft.decision === value ? 'selected' : ''}" type="button" data-review-decision="${value}" aria-pressed="${draft.decision === value}" ${disabled ? 'disabled' : ''}><span>${icon(meta.icon)}</span><span><strong>${escapeHtml(meta.label)}</strong><small>${escapeHtml(meta.description)}</small></span>${draft.decision === value ? icon('checkCircle') : ''}</button>`;
}

function renderDecisionForm(item, batch) {
  const draft = getDraft(item);
  const disabled = batch.status === 'completed';
  const editor = draft.decision === 'normalize'
    ? `<label class="field review-output-field"><span>修正后的知识文本 <b>*</b><em class="field-auto-label">系统预填</em></span><textarea id="correctedText" ${disabled ? 'disabled' : ''}>${escapeHtml(draft.correctedText)}</textarea><small>已补全表格上下文，可直接确认；也可以根据业务事实调整。</small></label>`
    : draft.decision
      ? `<label class="field review-output-field"><span>处理说明 <b>*</b><em class="field-auto-label">系统预填</em></span><textarea id="reviewNote" placeholder="记录判断依据、影响范围或后续责任人" ${disabled ? 'disabled' : ''}>${escapeHtml(draft.note)}</textarea><small>系统已结合异常原因、业务风险和后续责任人生成，可直接确认。</small></label>`
      : `<div class="review-decision-empty">${icon('clipboard')}<span><strong>等待业务判断</strong><small>选择一种处理方式后，系统会显示对应的结论字段。</small></span></div>`;
  return `<div class="review-inspector-header"><div><span>处理决定</span><strong>异常 ${item.order} / ${batch.items.length}</strong></div>${item.status === 'resolved' ? badge('completed', '已保存') : badge('pending', '未保存')}</div><div class="review-decision-list">${Object.keys(decisionMeta).map((value) => decisionOption(value, draft, disabled)).join('')}</div>${editor}<div class="review-inspector-actions"><button class="button primary" id="saveReviewItem" type="button" ${!draft.decision || disabled ? 'disabled' : ''}>${icon('check')}保存本项决定</button></div>`;
}

export function renderManualReview(state, route) {
  const jobId = route?.query?.get('job');
  const job = state.jobs.find((item) => item.id === jobId);
  const batch = state.reviewBatches.find((item) => item.jobId === jobId);
  if (!job || !batch) {
    return `${pageHeader({ title: '人工复核', description: '处理被质量规则阻断的摄取内容。', actions: `<button class="button secondary" id="backToJobs" type="button">${icon('arrowLeft')}返回任务列表</button>` })}<section class="panel"><div class="panel-body">${emptyState('没有找到复核批次', '该任务可能不需要人工复核，或批次已经被移除。')}</div></section>`;
  }

  const current = batch.items.find((item) => item.id === selectedItemId) || batch.items.find((item) => item.status !== 'resolved') || batch.items[0];
  selectedItemId = current.id;
  const resolved = batch.items.filter((item) => item.status === 'resolved').length;
  const done = batch.status === 'completed';
  const progress = Math.round((resolved / batch.items.length) * 100);

  return `${pageHeader({ eyebrow: '摄取任务 · 内容治理', title: '人工复核工作台', description: '质量规则 TABLE_STRUCTURE 已阻断写入。复核结论将成为本次 run 的治理证据。', actions: `<button class="button secondary" id="backToJobs" type="button">${icon('arrowLeft')}返回任务</button>${done ? `<button class="button primary" id="retryReviewedJob" type="button">${icon('refresh')}从 checkpoint 重试</button>` : ''}` })}
    <section class="review-context-strip">
      <div><small>运行 ID</small><strong class="mono">${escapeHtml(job.runId)}</strong></div>
      <div><small>知识源</small><strong>${escapeHtml(job.sourceName)}</strong></div>
      <div><small>阻断规则</small><strong class="mono">${escapeHtml(batch.rule)}</strong></div>
      <div><small>checkpoint</small><strong>${job.progress}% · 172 / 410 篇</strong></div>
      <div><small>复核状态</small>${reviewStatus(batch.status)}</div>
    </section>
    ${done ? `<div class="notice success review-complete-notice">${icon('checkCircle')}<div><strong>内容阻断已解除，等待恢复执行</strong><span>${escapeHtml(batch.submittedBy)} 于 ${escapeHtml(relativeTime(batch.submittedAt))} 提交了 ${batch.items.length} 项决定。复核只确认内容处理方案，点击“从 checkpoint 重试”后才会继续写入 Collection。</span></div></div>` : ''}
    <section class="review-workbench">
      <aside class="review-queue" aria-label="异常项列表">
        <header><div><span>异常队列</span><strong>${resolved} / ${batch.items.length} 已处理</strong></div><div class="review-progress"><span style="width:${progress}%"></span></div></header>
        <div class="review-queue-list">${batch.items.map((item) => queueItem(item, item.id === current.id)).join('')}</div>
        <footer><span>${icon('alert')} 高风险项会阻断本次摄取</span></footer>
      </aside>
      <div class="review-evidence">
        <header class="review-evidence-header"><div><span class="review-severity ${current.severity}">${current.severity === 'high' ? '高风险' : '中风险'}</span><h2>${escapeHtml(current.pageTitle)}</h2><p>${escapeHtml(current.path)} · ${escapeHtml(current.location)}</p></div><button class="icon-button" type="button" id="openSourcePreview" aria-label="查看原页面信息" title="查看原页面信息">${icon('external')}</button></header>
        <div class="review-rule-explanation"><span>${icon('alert')}</span><div><strong>系统为什么拦截</strong><p>${escapeHtml(current.issue)}</p></div></div>
        <div class="review-comparison">
          <section class="review-artifact"><header><span>Wiki 原表</span><em>事实依据</em></header>${renderOriginalTable(current.original)}<footer>高亮单元格包含合并结构，视觉上能理解，线性文本解析时容易丢失父级语义。</footer></section>
          <section class="review-artifact parsed"><header><span>当前解析结果</span><em>禁止入库</em></header><pre>${escapeHtml(current.parsedText)}</pre><footer>${icon('alert')} ${escapeHtml(current.risk)}</footer></section>
        </div>
      </div>
      <aside class="review-inspector">${renderDecisionForm(current, batch)}</aside>
      <footer class="review-batch-footer">
        <div><strong>${done ? '复核批次已提交' : resolved === batch.items.length ? '所有异常均已形成处理决定' : `还需处理 ${batch.items.length - resolved} 项异常`}</strong><span>${done ? '下一步是恢复摄取任务，验证修正内容能否顺利通过流水线。' : '批次提交后结论会锁定，并开放 checkpoint 重试。'}</span></div>
        <button class="button primary" id="submitReviewBatch" type="button" ${resolved !== batch.items.length || done ? 'disabled' : ''}>${icon('shield')}${done ? '已提交复核' : '提交整批复核'}</button>
      </footer>
    </section>`;
}

export function mountManualReview(root, state, rerender, route) {
  const jobId = route?.query?.get('job');
  const job = state.jobs.find((item) => item.id === jobId);
  const batch = state.reviewBatches.find((item) => item.jobId === jobId);
  root.querySelector('#backToJobs')?.addEventListener('click', () => navigate('/jobs', job ? { job: job.id } : {}));
  if (!job || !batch) return;

  const current = batch.items.find((item) => item.id === selectedItemId) || batch.items[0];
  const draft = getDraft(current);
  root.querySelectorAll('[data-review-item]').forEach((button) => button.addEventListener('click', () => {
    selectedItemId = button.dataset.reviewItem;
    rerender();
  }));
  root.querySelectorAll('[data-review-decision]').forEach((button) => button.addEventListener('click', () => {
    applyDecision(current, draft, button.dataset.reviewDecision);
    rerender();
  }));
  root.querySelector('#correctedText')?.addEventListener('input', (event) => { draft.correctedText = event.target.value; });
  root.querySelector('#reviewNote')?.addEventListener('input', (event) => { draft.note = event.target.value; });
  root.querySelector('#saveReviewItem')?.addEventListener('click', async (event) => {
    const button = event.currentTarget;
    button.disabled = true;
    try {
      await saveReviewDecision(job.id, current.id, draft);
      const latest = state.reviewBatches.find((item) => item.jobId === job.id);
      const next = latest.items.find((item) => item.status !== 'resolved');
      if (next) selectedItemId = next.id;
      toast(next ? '本项决定已保存，已进入下一项' : '三项决定已保存，可以提交整批复核', 'success');
      rerender();
    } catch (error) {
      button.disabled = false;
      toast(error.message, 'danger');
    }
  });
  root.querySelector('#openSourcePreview')?.addEventListener('click', () => toast(`原页面：${current.pageId}（模拟只读快照）`, 'info'));
  root.querySelector('#submitReviewBatch')?.addEventListener('click', async () => {
    const confirmed = await confirmAction({
      title: '提交人工复核结论',
      message: `确认提交 ${batch.items.length} 项处理决定？`,
      confirmLabel: '提交并解除阻断',
      detail: '提交后本批结论会锁定并写入审计记录，但仍需人工点击从 checkpoint 重试。',
    });
    if (!confirmed) return;
    try {
      await submitManualReview(job.id);
      toast('人工复核已提交，任务现在可以恢复执行', 'success');
    } catch (error) { toast(error.message, 'danger'); }
  });
  root.querySelector('#retryReviewedJob')?.addEventListener('click', () => navigate('/jobs', { job: job.id }));
}
