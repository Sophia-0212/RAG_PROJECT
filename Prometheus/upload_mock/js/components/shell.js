import { icon } from '../core/icons.js';
import { activeWorkspace, exportState, getState, resetState } from '../core/store.js';
import { markAllNotificationsRead, markNotificationRead, switchWorkspace } from '../core/mock-api.js';
import { navigate } from '../core/router.js';
import { downloadFile, openDrawer, openModal, openPopover, closeOverlay, closePopover, confirmAction, toast } from './ui.js';
import { escapeHtml, relativeTime } from '../core/utils.js';

const navItems = [
  { path: '/overview', label: '运营总览', icon: 'layout' },
  { path: '/sources', label: '知识源', icon: 'file', count: (state) => state.sources.filter((item) => item.status !== 'archived').length },
  { path: '/jobs', label: '摄取任务', icon: 'history', alert: (state) => state.jobs.some((item) => item.status === 'failed') },
  { path: '/versions', label: '版本发布', icon: 'boxes' },
  { path: '/quality', label: '质量评测', icon: 'activity' },
  { path: '/quality/online', label: '上线效果', icon: 'sliders' },
  { path: '/audit', label: '权限审计', icon: 'shield' },
];
let shortcutBound = false;

export function shellTemplate(route, state) {
  const workspace = activeWorkspace();
  const unread = state.notifications.filter((item) => !item.read).length;
  const nav = navItems.map((item) => `<a class="nav-item ${route.path === item.path || (item.path === '/sources' && route.path.startsWith('/sources/')) || (item.path === '/jobs' && route.path.startsWith('/jobs/')) ? 'active' : ''}" href="#${item.path}" data-nav-link="${item.path}">${icon(item.icon)}<span>${item.label}</span>${item.count ? `<em>${item.count(state)}</em>` : item.alert?.(state) ? '<i class="nav-alert-dot"></i>' : ''}</a>`).join('');
  return `<div class="app-shell">
    <aside class="sidebar" id="sidebar">
      <a class="brand" href="#/overview" aria-label="返回运营总览"><span class="brand-mark"><span></span><span></span><span></span></span><span class="brand-copy"><strong>知策</strong><small>CRM KNOWLEDGE OPS</small></span></a>
      <button class="workspace-switcher" id="workspaceSwitcher" type="button" aria-label="切换工作空间"><span class="workspace-monogram">${escapeHtml(workspace.monogram)}</span><span><small>当前工作空间</small><strong>${escapeHtml(workspace.name)}</strong></span>${icon('chevronDown')}</button>
      <nav class="main-nav" aria-label="主导航"><span class="nav-label">知识运营</span>${nav}<span class="nav-label nav-label-system">系统</span><a class="nav-item ${route.path === '/settings' ? 'active' : ''}" href="#/settings" data-nav-link="/settings">${icon('settings')}<span>环境配置</span></a></nav>
      <div class="sidebar-footer"><div class="operator-avatar">${escapeHtml(state.user.name.slice(0, 1))}</div><div><strong>${escapeHtml(state.user.name)}</strong><small>${escapeHtml(state.user.title)}</small></div><button class="icon-button compact" id="userMenuButton" type="button" aria-label="账户菜单" title="账户菜单">${icon('more')}</button></div>
    </aside>
    <div class="page-shell">
      <header class="topbar"><div class="topbar-left"><button class="icon-button mobile-menu-button" id="mobileMenuButton" type="button" aria-label="打开导航">${icon('menu')}</button><span class="breadcrumb"><span>${escapeHtml(route.group)}</span>${icon('chevronRight')}<strong>${escapeHtml(route.title)}</strong></span></div><div class="topbar-actions"><button class="global-search" id="globalSearchButton" type="button">${icon('search')}<span>搜索知识源、任务或版本</span><kbd>⌘ K</kbd></button><span class="environment-badge"><i></i>模拟环境</span><button class="icon-button notification-button" id="notificationButton" type="button" aria-label="通知" title="通知">${icon('bell')}${unread ? `<em>${unread}</em>` : ''}</button></div></header>
      <main class="page-main"><div class="route-outlet" id="routeOutlet"></div></main>
    </div>
    <div class="mobile-scrim" id="mobileScrim"></div>
  </div>`;
}

function showWorkspaceChooser() {
  const state = getState();
  openModal({
    title: '切换工作空间',
    subtitle: '不同工作空间的角色和操作权限相互独立。',
    body: `<div class="stack">${state.workspaces.map((workspace) => `<button class="quick-action" type="button" data-workspace-id="${workspace.id}"><span class="workspace-monogram">${escapeHtml(workspace.monogram)}</span><div><strong>${escapeHtml(workspace.name)}</strong><small>${escapeHtml(workspace.role)}${workspace.id === state.activeWorkspaceId ? ' · 当前' : ''}</small></div>${workspace.id === state.activeWorkspaceId ? icon('check') : icon('chevronRight')}</button>`).join('')}</div>`,
    onMount: (modal) => {
      modal.querySelectorAll('[data-workspace-id]').forEach((button) => button.addEventListener('click', async () => {
        try {
          await switchWorkspace(button.dataset.workspaceId);
          closeOverlay();
          toast('工作空间已切换', 'success');
        } catch (error) { toast(error.message, 'danger'); }
      }));
    },
  });
}

function showNotifications() {
  const state = getState();
  openDrawer({
    title: '通知中心',
    subtitle: `${state.notifications.filter((item) => !item.read).length} 条未读通知`,
    body: state.notifications.length ? `<div class="notification-list">${state.notifications.map((item) => `<button class="notification-item ${item.read ? '' : 'unread'}" type="button" data-notice-id="${item.id}" data-route="${item.route}"><i></i><span><strong>${escapeHtml(item.title)}</strong><span>${escapeHtml(item.body)}</span></span><time>${escapeHtml(relativeTime(item.time))}</time></button>`).join('')}</div>` : '<div class="table-empty"><strong>没有通知</strong><p>新的任务、评测与发布事件会显示在这里。</p></div>',
    actions: [{ label: '全部标为已读', icon: 'checkCircle', close: false, onClick: async () => { await markAllNotificationsRead(); toast('通知已全部标为已读', 'success'); showNotifications(); } }],
    onMount: (drawer) => {
      drawer.querySelectorAll('[data-notice-id]').forEach((button) => button.addEventListener('click', async () => {
        await markNotificationRead(button.dataset.noticeId);
        closeOverlay();
        navigate(button.dataset.route);
      }));
    },
  });
}

function searchIndex(state, keyword) {
  const term = keyword.trim().toLowerCase();
  const entries = [
    ...state.sources.map((item) => ({ type: '知识源', icon: 'file', title: item.name, subtitle: item.uri, route: '/sources' })),
    ...state.jobs.map((item) => ({ type: '摄取任务', icon: 'history', title: item.runId, subtitle: item.sourceName, route: '/jobs' })),
    ...state.versions.map((item) => ({ type: '版本', icon: 'boxes', title: item.collection, subtitle: item.status, route: '/versions' })),
    ...state.evaluations.map((item) => ({ type: '评测', icon: 'activity', title: item.id, subtitle: `${item.version} · ${item.dataset}`, route: '/quality' })),
  ];
  if (!term) return entries.slice(0, 8);
  return entries.filter((item) => `${item.title} ${item.subtitle} ${item.type}`.toLowerCase().includes(term)).slice(0, 10);
}

function showGlobalSearch() {
  const state = getState();
  const renderResults = (items) => items.length ? items.map((item) => `<button class="search-result" type="button" data-search-route="${item.route}"><span>${icon(item.icon)}</span><span><strong>${escapeHtml(item.title)}</strong><small>${escapeHtml(item.subtitle)}</small></span><em>${escapeHtml(item.type)}</em></button>`).join('') : '<div class="table-empty"><strong>没有匹配结果</strong><p>尝试搜索知识源名称、run_id、Collection 或评测编号。</p></div>';
  openModal({
    title: '全局搜索', subtitle: '跨知识源、任务、版本和评测记录检索。', size: 'wide',
    body: `<label class="field"><span class="sr-only">搜索内容</span><input id="globalSearchInput" type="search" placeholder="输入名称、ID 或 Collection" autocomplete="off"></label><div class="search-results" id="globalSearchResults">${renderResults(searchIndex(state, ''))}</div>`,
    onMount: (modal) => {
      const input = modal.querySelector('#globalSearchInput');
      const results = modal.querySelector('#globalSearchResults');
      const bindResults = () => results.querySelectorAll('[data-search-route]').forEach((button) => button.addEventListener('click', () => { closeOverlay(); navigate(button.dataset.searchRoute); }));
      bindResults();
      input.addEventListener('input', () => { results.innerHTML = renderResults(searchIndex(getState(), input.value)); bindResults(); });
      input.focus();
    },
  });
}

function showProfile() {
  const state = getState();
  openDrawer({
    title: state.user.name,
    subtitle: state.user.title,
    body: `<dl class="detail-list"><div><dt>用户 ID</dt><dd class="mono">${escapeHtml(state.user.id)}</dd></div><div><dt>当前工作空间</dt><dd>${escapeHtml(activeWorkspace().name)}</dd></div><div><dt>角色</dt><dd>${state.user.roles.map(escapeHtml).join(' / ')}</dd></div><div><dt>认证来源</dt><dd>企业 IAM（模拟）</dd></div></dl><div class="form-section"><div class="notice info">${icon('shield')}<div><strong>最小权限说明</strong><span>发布与回滚动作会独立检查 release_manager 角色，并记录审计事件。</span></div></div></div>`,
    actions: [{ label: '查看我的审计操作', icon: 'shield', onClick: () => navigate('/audit', { actor: state.user.name }) }],
  });
}

function showUserMenu(anchor) {
  openPopover(anchor, `<ul class="popover-menu"><li><button type="button" data-user-action="profile">${icon('user')}个人与权限</button></li><li><button type="button" data-user-action="export">${icon('download')}导出模拟状态</button></li><li class="popover-divider"></li><li><button class="danger-text" type="button" data-user-action="reset">${icon('refresh')}重置模拟数据</button></li></ul>`, (popover) => {
    popover.querySelector('[data-user-action="profile"]').addEventListener('click', () => { closePopover(); showProfile(); });
    popover.querySelector('[data-user-action="export"]').addEventListener('click', () => { downloadFile('knowledge-ops-mock-state.json', JSON.stringify(exportState(), null, 2)); closePopover(); toast('模拟状态已导出', 'success'); });
    popover.querySelector('[data-user-action="reset"]').addEventListener('click', async () => {
      closePopover();
      const confirmed = await confirmAction({ title: '重置模拟数据', message: '当前页面中的所有模拟操作将恢复为初始状态。', confirmLabel: '确认重置', danger: true, detail: '模拟状态只保存在当前页面内存中。刷新浏览器也会自动重置，不影响项目文件或后端服务。' });
      if (confirmed) { resetState(); toast('模拟数据已恢复', 'success'); navigate('/overview'); }
    });
  });
}

function closeMobileMenu() {
  document.getElementById('sidebar')?.classList.remove('open');
  document.getElementById('mobileScrim')?.classList.remove('open');
}

export function mountShell() {
  document.getElementById('workspaceSwitcher').addEventListener('click', showWorkspaceChooser);
  document.getElementById('globalSearchButton').addEventListener('click', showGlobalSearch);
  document.getElementById('notificationButton').addEventListener('click', showNotifications);
  document.getElementById('userMenuButton').addEventListener('click', (event) => showUserMenu(event.currentTarget));
  document.getElementById('mobileMenuButton').addEventListener('click', () => {
    document.getElementById('sidebar').classList.add('open');
    document.getElementById('mobileScrim').classList.add('open');
  });
  document.getElementById('mobileScrim').addEventListener('click', closeMobileMenu);
  document.querySelectorAll('[data-nav-link]').forEach((link) => link.addEventListener('click', closeMobileMenu));
  if (!shortcutBound) {
    document.addEventListener('keydown', (event) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        document.getElementById('globalSearchButton')?.click();
      }
    });
    shortcutBound = true;
  }
}
