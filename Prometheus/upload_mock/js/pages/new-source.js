import { icon } from '../core/icons.js';
import { createSource } from '../core/mock-api.js';
import { navigate } from '../core/router.js';
import { panel, pageHeader, toast } from '../components/ui.js';
import { escapeHtml, formatBytes } from '../core/utils.js';

const draft = {
  step: 1, type: 'markdown', name: '', category: '产品政策', tenantId: 'crm-demo',
  uri: 'datas/md/', schedule: '手动', visibility: 'restricted',
  acl: ['group:sales', 'group:customer-success'], files: [],
};

const choices = [
  { type: 'markdown', icon: 'file', title: '本地 Markdown', hint: '上传 .md / .txt 文件，适合产品说明与运营规则' },
  { type: 'wiki', icon: 'book', title: '企业 Wiki', hint: '按空间或页面树定时拉取，支持增量同步' },
  { type: 'object', icon: 'database', title: '对象存储', hint: '读取 S3 兼容桶中的受控内容快照' },
];

function persistForm(root) {
  root.querySelectorAll('[data-draft]').forEach((input) => {
    if (input.type === 'checkbox') return;
    draft[input.dataset.draft] = input.value;
  });
}

function connectorFields() {
  if (draft.type === 'markdown') return `<label class="dropzone" id="fileDropzone"><input id="sourceFiles" type="file" accept=".md,.markdown,.txt,text/markdown,text/plain" multiple><span class="drop-icon">${icon('cloudUpload')}</span><strong>拖放 Markdown 文件，或点击选择</strong><small>支持 .md、.markdown、.txt；模拟页面不会把文件发送到服务器</small></label><div class="file-list">${draft.files.map((file, index) => `<div class="file-item"><span>${escapeHtml(file.name)}</span><span>${formatBytes(file.size)}</span><button class="icon-button compact" type="button" data-remove-file="${index}" aria-label="移除 ${escapeHtml(file.name)}" title="移除">${icon('x')}</button></div>`).join('')}</div>`;
  if (draft.type === 'wiki') return `<div class="form-grid"><label class="field span-full"><span>Wiki 页面地址 <b>*</b></span><input data-draft="uri" value="${escapeHtml(draft.uri.startsWith('wiki://') ? draft.uri : 'wiki://crm/') }" placeholder="wiki://crm/space/page-tree"><small>仅填写已授权空间，系统会沿页面树抓取并保留源页面引用。</small></label><label class="field"><span>同步计划</span><select data-draft="schedule"><option>每 30 分钟</option><option>每小时</option><option>每日 02:00</option><option>手动</option></select></label><label class="field"><span>凭据引用</span><input value="vault://crm/wiki-reader" disabled><small>密钥由 Vault 托管，页面不接触明文。</small></label></div>`;
  return `<div class="form-grid"><label class="field span-full"><span>对象路径 <b>*</b></span><input data-draft="uri" value="${escapeHtml(draft.uri.startsWith('s3://') ? draft.uri : 's3://crm-knowledge/') }" placeholder="s3://bucket/prefix"><small>建议使用版本化前缀，避免源数据在摄取期间变化。</small></label><label class="field"><span>同步计划</span><select data-draft="schedule"><option>每日 02:00</option><option>每小时</option><option>手动</option></select></label><label class="field"><span>凭据引用</span><input value="vault://crm/object-reader" disabled><small>只读角色，仅授予目标前缀的 List/Get 权限。</small></label></div>`;
}

function stepBody() {
  if (draft.step === 1) return `<div class="wizard-step active"><h2 class="section-title">选择内容来源</h2><p class="section-copy">不同连接器共享同一套治理、预检与版本发布流程。</p><div class="source-choice-grid">${choices.map((item) => `<button class="source-choice ${draft.type === item.type ? 'selected' : ''}" type="button" data-source-type="${item.type}">${icon(item.icon)}<strong>${item.title}</strong><small>${item.hint}</small></button>`).join('')}</div><div class="notice info form-section">${icon('shield')}<div><strong>租户隔离贯穿摄取和检索</strong><span>所有来源必须绑定 tenant_id；ACL 会复制到 Chunk 元数据，并在召回时强制过滤。</span></div></div></div>`;
  if (draft.step === 2) return `<div class="wizard-step active"><h2 class="section-title">配置连接与内容</h2><p class="section-copy">填写业务可识别的名称，并指定可追溯的来源地址。</p><div class="form-grid"><label class="field"><span>知识源名称 <b>*</b></span><input data-draft="name" value="${escapeHtml(draft.name)}" placeholder="例如：商业产品准入规则"></label><label class="field"><span>业务分类</span><select data-draft="category">${['产品政策','服务流程','客户规则','风险合规','故障排查','运营公告'].map((item) => `<option ${draft.category === item ? 'selected' : ''}>${item}</option>`).join('')}</select></label></div><div class="form-section">${connectorFields()}</div></div>`;
  if (draft.step === 3) return `<div class="wizard-step active"><h2 class="section-title">设置治理与权限</h2><p class="section-copy">访问控制是知识内容的一部分，必须在进入向量库之前确定。</p><div class="form-grid"><label class="field"><span>租户 ID <b>*</b></span><input data-draft="tenantId" value="${escapeHtml(draft.tenantId)}"></label><label class="field"><span>同步策略</span><select data-draft="schedule"><option ${draft.schedule === '手动' ? 'selected' : ''}>手动</option><option ${draft.schedule === '每 30 分钟' ? 'selected' : ''}>每 30 分钟</option><option ${draft.schedule === '每小时' ? 'selected' : ''}>每小时</option><option ${draft.schedule === '每日 02:00' ? 'selected' : ''}>每日 02:00</option></select></label></div><fieldset class="form-section"><legend class="fieldset-title">可见范围</legend><div class="segmented"><button class="${draft.visibility === 'restricted' ? 'active' : ''}" type="button" data-visibility="restricted">${icon('users')}按用户组限制</button><button class="${draft.visibility === 'public' ? 'active' : ''}" type="button" data-visibility="public">${icon('globe')}工作空间公开</button></div></fieldset>${draft.visibility === 'restricted' ? `<fieldset class="form-section"><legend class="fieldset-title">授权用户组 <b>*</b></legend><div class="acl-grid">${[['group:sales','销售团队','一线销售及主管'],['group:customer-success','客户成功','优化师与客户经理'],['group:crm-ops','CRM 运营','客户运营与策略人员'],['group:risk-control','风险控制','账户审核与合规人员']].map(([value,title,hint]) => `<label class="check-option ${draft.acl.includes(value) ? 'selected' : ''}"><input type="checkbox" value="${value}" ${draft.acl.includes(value) ? 'checked' : ''}><span class="check-box">${icon('check')}</span><span><strong>${title}</strong><small>${hint}</small></span></label>`).join('')}</div></fieldset>` : `<div class="notice warning form-section">${icon('alert')}<div><strong>空间内所有成员均可检索</strong><span>公开内容仍受 tenant_id 隔离，但不会再按用户组缩小结果集。</span></div></div>`}</div>`;
  const fileCount = draft.files.length;
  const predicted = draft.type === 'markdown' ? Math.max(fileCount, 1) : 128;
  return `<div class="wizard-step active"><h2 class="section-title">预检并创建任务</h2><p class="section-copy">此步骤只生成摄取计划；完成治理、索引和质量门禁后才允许发布。</p><div class="preflight-grid"><div class="preflight-item added"><span>预计新增文档</span><strong>${predicted}</strong></div><div class="preflight-item updated"><span>预计更新</span><strong>0</strong></div><div class="preflight-item removed"><span>高风险删除</span><strong>0</strong></div><div class="preflight-item"><span>ACL 规则</span><strong>${draft.visibility === 'public' ? 1 : draft.acl.length}</strong></div></div><dl class="detail-list form-section"><div><dt>知识源</dt><dd>${escapeHtml(draft.name || '未命名知识源')}</dd></div><div><dt>类型</dt><dd>${escapeHtml(choices.find((item) => item.type === draft.type).title)}</dd></div><div><dt>来源</dt><dd class="mono">${escapeHtml(draft.type === 'markdown' ? `${fileCount} 个本地文件` : draft.uri)}</dd></div><div><dt>权限</dt><dd>${draft.visibility === 'public' ? '工作空间公开' : draft.acl.map((item) => item.replace('group:', '')).join('、')}</dd></div></dl><div class="notice success form-section">${icon('checkCircle')}<div><strong>预检通过，可以创建摄取任务</strong><span>租户、来源格式、ACL 完整性和高风险删除阈值均符合要求。</span></div></div></div>`;
}

function sideGuide() {
  return panel({ title: '上线链路', description: '当前操作不会直接影响线上检索', body: `<ol class="pipeline-list"><li class="active"><span>${icon('upload')}</span><div><strong>接入与预检</strong><small>来源、租户和 ACL 校验</small></div></li><li><span>${icon('history')}</span><div><strong>摄取与索引</strong><small>稳定 ID、切分、Embedding</small></div></li><li><span>${icon('activity')}</span><div><strong>质量门禁</strong><small>召回、引用、忠实度、越权</small></div></li><li><span>${icon('rocket')}</span><div><strong>版本发布</strong><small>CAS 切换 rag_active 别名</small></div></li></ol><div class="notice warning form-section">${icon('help')}<div><strong>为什么不直接覆盖线上库？</strong><span>新内容先写入候选 Collection，只有评测通过后才切换别名，从而支持快速回滚。</span></div></div>` });
}

export function renderNewSource() {
  const steps = [['选择来源','连接器类型'],['配置内容','地址与文件'],['权限治理','租户与 ACL'],['预检创建','生成摄取任务']];
  return `${pageHeader({ eyebrow: '知识源 / 新建', title: '接入知识源', description: '通过受控流程把企业内容转化为可评测、可发布、可回滚的知识资产。', actions: `<button class="button secondary" type="button" id="cancelWizard">${icon('x')}取消</button>` })}<ol class="stepper">${steps.map(([title,hint], index) => `<li class="${draft.step === index + 1 ? 'active' : draft.step > index + 1 ? 'complete' : ''}"><button type="button" data-step="${index + 1}" ${index + 1 > draft.step ? 'disabled' : ''}><span>${index + 1}</span><div><strong>${title}</strong><small>${hint}</small></div></button></li>`).join('')}</ol><div class="wizard-layout"><section class="panel wizard-panel"><div id="wizardBody">${stepBody()}</div><footer class="wizard-actions"><button class="button secondary" type="button" id="wizardBack" ${draft.step === 1 ? 'disabled' : ''}>${icon('arrowLeft')}上一步</button><div><button class="button ghost" type="button" id="saveDraft">保存草稿</button><button class="button primary" type="button" id="wizardNext">${draft.step === 4 ? `${icon('rocket')}创建摄取任务` : `下一步${icon('arrowRight')}`}</button></div></footer></section>${sideGuide()}</div>`;
}

function validateStep() {
  if (draft.step === 2 && !draft.name.trim()) return '请填写知识源名称';
  if (draft.step === 2 && draft.type === 'markdown' && !draft.files.length) return '请至少选择一个 Markdown 文件';
  if (draft.step === 2 && draft.type !== 'markdown' && !draft.uri.trim()) return '请填写来源地址';
  if (draft.step === 3 && !draft.tenantId.trim()) return '请填写租户 ID';
  if (draft.step === 3 && draft.visibility === 'restricted' && !draft.acl.length) return '请至少选择一个授权用户组';
  return '';
}

export function mountNewSource(root, _state, rerender) {
  root.querySelector('#cancelWizard').addEventListener('click', () => navigate('/sources'));
  root.querySelector('#saveDraft').addEventListener('click', () => { persistForm(root); toast('草稿已保存在当前浏览会话', 'success'); });
  root.querySelector('#wizardBack').addEventListener('click', () => { persistForm(root); draft.step = Math.max(1, draft.step - 1); rerender(); });
  root.querySelectorAll('[data-step]').forEach((button) => button.addEventListener('click', () => { persistForm(root); draft.step = Number(button.dataset.step); rerender(); }));
  root.querySelectorAll('[data-source-type]').forEach((button) => button.addEventListener('click', () => { draft.type = button.dataset.sourceType; draft.uri = draft.type === 'wiki' ? 'wiki://crm/' : draft.type === 'object' ? 's3://crm-knowledge/' : 'datas/md/'; rerender(); }));
  const fileInput = root.querySelector('#sourceFiles'); const dropzone = root.querySelector('#fileDropzone');
  if (fileInput) {
    dropzone.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('click', (event) => event.stopPropagation());
    fileInput.addEventListener('change', () => { draft.files = [...fileInput.files]; rerender(); });
    dropzone.addEventListener('dragover', (event) => { event.preventDefault(); dropzone.classList.add('dragging'); });
    dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragging'));
    dropzone.addEventListener('drop', (event) => { event.preventDefault(); dropzone.classList.remove('dragging'); draft.files = [...event.dataTransfer.files].filter((file) => /\.(md|markdown|txt)$/i.test(file.name)); rerender(); });
  }
  root.querySelectorAll('[data-remove-file]').forEach((button) => button.addEventListener('click', () => { draft.files.splice(Number(button.dataset.removeFile), 1); rerender(); }));
  root.querySelectorAll('[data-visibility]').forEach((button) => button.addEventListener('click', () => { draft.visibility = button.dataset.visibility; rerender(); }));
  root.querySelectorAll('.check-option input').forEach((input) => input.addEventListener('change', () => { draft.acl = [...root.querySelectorAll('.check-option input:checked')].map((item) => item.value); rerender(); }));
  root.querySelector('#wizardNext').addEventListener('click', async (event) => {
    persistForm(root); const error = validateStep(); if (error) { toast(error, 'warning'); return; }
    if (draft.step < 4) { draft.step += 1; rerender(); return; }
    const button = event.currentTarget; button.disabled = true; button.textContent = '正在创建任务';
    try {
      const result = await createSource({ ...draft, files: draft.files.map((file) => ({ name: file.name, size: file.size })) });
      toast(`知识源已创建，任务 ${result.job.runId} 开始执行`, 'success', 4500);
      Object.assign(draft, { step: 1, type: 'markdown', name: '', category: '产品政策', tenantId: 'crm-demo', uri: 'datas/md/', schedule: '手动', visibility: 'restricted', acl: ['group:sales', 'group:customer-success'], files: [] });
      navigate('/jobs', { job: result.job.id });
    } catch (failure) { button.disabled = false; button.textContent = '创建摄取任务'; toast(failure.message, 'danger'); }
  });
}
