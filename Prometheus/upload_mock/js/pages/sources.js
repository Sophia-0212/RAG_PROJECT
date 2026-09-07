import { icon } from '../core/icons.js';
import { navigate } from '../core/router.js';
import { archiveSource, syncSource, toggleSource, updateSource } from '../core/mock-api.js';
import { badge, closePopover, confirmAction, emptyState, openDrawer, openModal, openPopover, pageHeader, pagination, toast } from '../components/ui.js';
import { escapeHtml, formatNumber, relativeTime } from '../core/utils.js';

const view = { query: '', type: 'all', status: 'all' };
let filterTimer;
const typeLabel = { markdown: 'Markdown', wiki: '企业 Wiki', object: '对象存储' };
const typeIcon = { markdown: 'file', wiki: 'book', object: 'database' };

function filteredSources(state) {
  const q = view.query.toLowerCase();
  return state.sources.filter((source) => (view.type === 'all' || source.type === view.type) && (view.status === 'all' || source.status === view.status) && (!q || `${source.name} ${source.uri} ${source.owner} ${source.category}`.toLowerCase().includes(q)));
}

function openSourceDetail(source) {
  openDrawer({
    title: source.name, subtitle: `${typeLabel[source.type]} · ${source.category}`,
    body: `<div class="summary-grid"><div><span>健康状态</span>${badge(source.health)}</div><div><span>文档数</span><strong>${formatNumber(source.documents)}</strong></div><div><span>Chunk 数</span><strong>${formatNumber(source.chunks)}</strong></div><div><span>同步计划</span><strong>${escapeHtml(source.schedule)}</strong></div></div><dl class="detail-list"><div><dt>来源地址</dt><dd class="mono">${escapeHtml(source.uri)}</dd></div><div><dt>租户标识</dt><dd class="mono">${escapeHtml(source.tenantId)}</dd></div><div><dt>内容版本</dt><dd>${escapeHtml(source.version)}</dd></div><div><dt>负责人</dt><dd>${escapeHtml(source.owner)}</dd></div><div><dt>最近同步</dt><dd>${source.lastSync ? escapeHtml(relativeTime(source.lastSync)) : '尚未同步'}</dd></div><div><dt>可见范围</dt><dd>${source.visibility === 'public' ? '工作空间公开' : source.acl.map(escapeHtml).join('、')}</dd></div></dl>`,
    actions: [{ label: '查看摄取任务', icon: 'history', onClick: () => navigate('/jobs', { source: source.id }) }, { label: '立即同步', variant: 'primary', icon: 'refresh', busyText: '创建任务', onClick: async () => { await syncSource(source.id); toast('增量摄取任务已创建', 'success'); navigate('/jobs'); } }],
  });
}

function openAclEditor(source) {
  openModal({ title: '编辑权限范围', subtitle: source.name, body: `<div class="form-grid"><label class="field span-2"><span>可见性</span><select id="aclVisibility"><option value="restricted" ${source.visibility === 'restricted' ? 'selected' : ''}>按用户组限制</option><option value="public" ${source.visibility === 'public' ? 'selected' : ''}>工作空间公开</option></select></label><label class="field span-2"><span>允许访问的用户组</span><textarea id="aclGroups" rows="4" placeholder="每行一个，例如 group:sales">${escapeHtml(source.acl.join('\n'))}</textarea><small>权限字段会进入每个 Chunk，检索时强制过滤。</small></label></div>`, actions: [{ label: '取消' }, { label: '保存权限', variant: 'primary', icon: 'shield', busyText: '保存中', onClick: async (modal) => { const visibility = modal.querySelector('#aclVisibility').value; const acl = modal.querySelector('#aclGroups').value.split('\n').map((item) => item.trim()).filter(Boolean); if (visibility === 'restricted' && !acl.length) { toast('至少填写一个用户组', 'warning'); return false; } await updateSource(source.id, { visibility, acl }); toast('权限范围已更新', 'success'); } }] });
}

function showSourceMenu(anchor, source) {
  openPopover(anchor, `<ul class="popover-menu"><li><button type="button" data-action="acl">${icon('shield')}编辑权限</button></li><li><button type="button" data-action="toggle">${icon(source.status === 'paused' ? 'play' : 'pause')}${source.status === 'paused' ? '恢复同步' : '暂停同步'}</button></li><li class="popover-divider"></li><li><button class="danger-text" type="button" data-action="archive">${icon('archive')}归档知识源</button></li></ul>`, (popover) => {
    popover.querySelector('[data-action="acl"]').addEventListener('click', () => openAclEditor(source));
    popover.querySelector('[data-action="toggle"]').addEventListener('click', async () => { const wasPaused = source.status === 'paused'; closePopover(); await toggleSource(source.id); toast(wasPaused ? '同步已恢复' : '同步已暂停', 'success'); });
    popover.querySelector('[data-action="archive"]').addEventListener('click', async () => { closePopover(); const yes = await confirmAction({ title: '归档知识源', message: `确认归档“${source.name}”？`, confirmLabel: '确认归档', danger: true, detail: '归档会停止后续同步，但不会删除当前线上版本中的内容。' }); if (yes) { await archiveSource(source.id); toast('知识源已归档', 'success'); } });
  });
}

export function renderSources(state) {
  const sources = filteredSources(state);
  const rows = sources.map((source) => `<tr><td><button class="source-name table-link-block" type="button" data-source-open="${source.id}"><span class="source-type-icon">${icon(typeIcon[source.type])}</span><span><strong>${escapeHtml(source.name)}</strong><small>${escapeHtml(typeLabel[source.type])} · ${escapeHtml(source.category)}</small></span></button></td><td>${badge(source.health)}</td><td><strong>${formatNumber(source.documents)}</strong><small>${formatNumber(source.chunks)} chunks</small></td><td><div class="acl-tags">${source.visibility === 'public' ? badge('success', '空间公开') : source.acl.slice(0, 2).map((item) => badge('neutral', item.replace('group:', ''))).join('')}</div></td><td><strong>${escapeHtml(source.owner)}</strong><small>${source.lastSync ? escapeHtml(relativeTime(source.lastSync)) : '尚未同步'}</small></td><td><div class="table-actions"><button class="button secondary small" type="button" data-source-sync="${source.id}" ${source.status === 'archived' ? 'disabled' : ''}>${icon('refresh')}同步</button><button class="icon-button compact" type="button" data-source-menu="${source.id}" aria-label="更多操作" title="更多操作">${icon('more')}</button></div></td></tr>`).join('');
  return `${pageHeader({ title: '知识源', description: '统一管理 CRM 产品政策、销售 SOP、风控规范等内容来源及访问范围。', actions: `<button class="button secondary" type="button" id="batchCheck">${icon('shield')}权限体检</button><button class="button primary" type="button" id="newSource">${icon('plus')}新建知识源</button>` })}<section class="panel"><div class="filter-bar"><label class="filter-search">${icon('search')}<input id="sourceSearch" type="search" value="${escapeHtml(view.query)}" placeholder="搜索名称、负责人或地址"></label><label class="filter-control"><span>来源类型</span><select id="sourceType"><option value="all">全部类型</option><option value="markdown" ${view.type === 'markdown' ? 'selected' : ''}>Markdown</option><option value="wiki" ${view.type === 'wiki' ? 'selected' : ''}>企业 Wiki</option><option value="object" ${view.type === 'object' ? 'selected' : ''}>对象存储</option></select></label><label class="filter-control"><span>状态</span><select id="sourceStatus"><option value="all">全部状态</option><option value="active" ${view.status === 'active' ? 'selected' : ''}>服务中</option><option value="paused" ${view.status === 'paused' ? 'selected' : ''}>已暂停</option><option value="archived" ${view.status === 'archived' ? 'selected' : ''}>已归档</option></select></label><button class="button ghost small" type="button" id="resetFilters">重置</button></div><div class="table-wrap"><table><thead><tr><th>知识源</th><th>健康状态</th><th>内容规模</th><th>访问范围</th><th>负责人 / 同步</th><th>操作</th></tr></thead><tbody>${rows || `<tr><td colspan="6">${emptyState('没有匹配的知识源', '调整筛选条件，或接入一个新的内容来源。')}</td></tr>`}</tbody></table></div>${pagination(sources.length, '个知识源')}</section>`;
}

export function mountSources(root, state, rerender) {
  root.querySelector('#newSource').addEventListener('click', () => navigate('/sources/new'));
  root.querySelector('#batchCheck').addEventListener('click', () => openModal({ title: '权限体检结果', subtitle: '已检查所有有效知识源与 Chunk ACL 映射。', body: `<div class="gate-status pass">${icon('checkCircle')}<div><strong>未发现跨租户或越权风险</strong><small>${state.sources.length} 个来源均已绑定 tenant_id，受限来源包含显式 ACL 用户组。</small></div></div>`, actions: [{ label: '查看权限审计', variant: 'primary', icon: 'shield', onClick: () => navigate('/audit') }] }));
  const apply = () => { view.query = root.querySelector('#sourceSearch').value; view.type = root.querySelector('#sourceType').value; view.status = root.querySelector('#sourceStatus').value; rerender(); };
  root.querySelector('#sourceSearch').addEventListener('input', () => { window.clearTimeout(filterTimer); filterTimer = window.setTimeout(apply, 180); });
  root.querySelector('#sourceType').addEventListener('change', apply);
  root.querySelector('#sourceStatus').addEventListener('change', apply);
  root.querySelector('#resetFilters').addEventListener('click', () => { view.query = ''; view.type = 'all'; view.status = 'all'; rerender(); });
  root.querySelectorAll('[data-source-open]').forEach((button) => button.addEventListener('click', () => openSourceDetail(state.sources.find((item) => item.id === button.dataset.sourceOpen))));
  root.querySelectorAll('[data-source-sync]').forEach((button) => button.addEventListener('click', async () => { try { button.disabled = true; await syncSource(button.dataset.sourceSync); toast('增量摄取任务已创建', 'success'); navigate('/jobs'); } catch (error) { button.disabled = false; toast(error.message, 'danger'); } }));
  root.querySelectorAll('[data-source-menu]').forEach((button) => button.addEventListener('click', () => showSourceMenu(button, state.sources.find((item) => item.id === button.dataset.sourceMenu))));
}
