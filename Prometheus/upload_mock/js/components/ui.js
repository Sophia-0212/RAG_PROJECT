import { icon } from '../core/icons.js';
import { escapeHtml, csvEscape } from '../core/utils.js';

const overlayRoot = () => document.getElementById('overlay-root');
const popoverRoot = () => document.getElementById('popover-root');
let popoverDismiss = null;

export function pageHeader({ eyebrow = 'CRM 知识运营', title, description = '', actions = '' }) {
  return `<section class="page-heading"><div class="page-heading-main"><div class="eyebrow">${escapeHtml(eyebrow)}</div><h1>${escapeHtml(title)}</h1>${description ? `<p>${escapeHtml(description)}</p>` : ''}</div><div class="page-heading-actions">${actions}</div></section>`;
}

export function panel({ title = '', description = '', actions = '', body = '', footer = '', className = '', flush = false }) {
  return `<section class="panel ${className}">${title || actions ? `<header class="panel-header"><div class="panel-header-main">${title ? `<h2>${escapeHtml(title)}</h2>` : ''}${description ? `<p>${escapeHtml(description)}</p>` : ''}</div><div class="panel-header-actions">${actions}</div></header>` : ''}<div class="panel-body ${flush ? 'flush' : ''}">${body}</div>${footer ? `<footer class="panel-footer">${footer}</footer>` : ''}</section>`;
}

const statusConfig = {
  active: ['服务中', 'success'], healthy: ['正常', 'success'], completed: ['已完成', 'success'], passed: ['已通过', 'success'], success: ['成功', 'success'], ready: ['可回滚', 'info'],
  running: ['运行中', 'info'], syncing: ['同步中', 'info'], checking: ['检查中', 'info'], queued: ['排队中', 'violet'], candidate: ['候选版本', 'violet'], pending: ['待执行', 'violet'],
  warning: ['需关注', 'warning'], paused: ['已暂停', 'warning'], canceled: ['已取消', 'neutral'], archived: ['已归档', 'neutral'],
  failed: ['失败', 'danger'], denied: ['已拒绝', 'danger'], error: ['异常', 'danger'],
};

export function badge(status, label = '') {
  const [fallbackLabel, tone] = statusConfig[status] || [String(status || '未知'), 'neutral'];
  return `<span class="badge ${tone}">${escapeHtml(label || fallbackLabel)}</span>`;
}

export function statCard({ label, value, hint, iconName = 'activity', tone = '', trend = '' }) {
  return `<article class="stat-card"><div class="stat-card-top"><span>${escapeHtml(label)}</span><span class="stat-icon ${tone}">${icon(iconName)}</span></div><strong>${value}</strong><div class="stat-card-bottom">${trend ? `<span class="trend ${trend.startsWith('-') ? 'down' : ''}">${escapeHtml(trend)}</span>` : ''}<span>${escapeHtml(hint || '')}</span></div></article>`;
}

export function emptyState(title, description, action = '') {
  return `<div class="table-empty"><span class="empty-icon">${icon('search')}</span><strong>${escapeHtml(title)}</strong><p>${escapeHtml(description)}</p>${action}</div>`;
}

export function pagination(count, noun = '条记录') {
  return `<div class="pagination"><span>共 ${count} ${escapeHtml(noun)}</span><div class="pagination-controls"><button class="icon-button compact" type="button" data-page-prev aria-label="上一页" title="上一页" disabled>${icon('chevronLeft')}</button><button class="icon-button compact" type="button" data-page-next aria-label="下一页" title="下一页" disabled>${icon('chevronRight')}</button></div></div>`;
}

export function toast(message, type = 'info', duration = 3200) {
  const node = document.createElement('div');
  node.className = `toast ${type}`;
  const iconName = type === 'success' ? 'checkCircle' : type === 'danger' || type === 'warning' ? 'alert' : 'activity';
  node.innerHTML = `${icon(iconName)}<span>${escapeHtml(message)}</span>`;
  document.getElementById('toast-root').appendChild(node);
  window.setTimeout(() => node.remove(), duration);
}

export function setButtonBusy(button, busy, busyText = '处理中') {
  if (!button) return;
  if (busy) {
    button.dataset.originalHtml = button.innerHTML;
    button.classList.add('busy');
    button.disabled = true;
    button.textContent = busyText;
  } else {
    button.classList.remove('busy');
    button.disabled = false;
    if (button.dataset.originalHtml) button.innerHTML = button.dataset.originalHtml;
    delete button.dataset.originalHtml;
  }
}

export function closeOverlay() {
  overlayRoot().innerHTML = '';
  document.body.style.overflow = '';
}

export function closePopover() {
  popoverRoot().innerHTML = '';
  if (popoverDismiss) document.removeEventListener('click', popoverDismiss);
  popoverDismiss = null;
}

function bindOverlayDismiss(overlay) {
  overlay.addEventListener('click', (event) => {
    if (event.target === overlay || event.target.closest('[data-close-overlay]')) closeOverlay();
  });
}

export function openModal({ title, subtitle = '', body = '', size = '', actions = [], onMount }) {
  closePopover();
  const overlay = document.createElement('div');
  overlay.className = 'overlay';
  overlay.innerHTML = `<section class="modal ${size}" role="dialog" aria-modal="true" aria-label="${escapeHtml(title)}"><header class="modal-header"><div><h2>${escapeHtml(title)}</h2>${subtitle ? `<p>${escapeHtml(subtitle)}</p>` : ''}</div><button class="icon-button" type="button" data-close-overlay aria-label="关闭">${icon('x')}</button></header><div class="modal-body">${body}</div>${actions.length ? `<footer class="modal-actions">${actions.map((action, index) => `<button class="button ${action.variant || 'secondary'}" type="button" data-modal-action="${index}">${action.icon ? icon(action.icon) : ''}${escapeHtml(action.label)}</button>`).join('')}</footer>` : ''}</section>`;
  overlayRoot().replaceChildren(overlay);
  document.body.style.overflow = 'hidden';
  bindOverlayDismiss(overlay);
  actions.forEach((action, index) => {
    overlay.querySelector(`[data-modal-action="${index}"]`).addEventListener('click', async (event) => {
      const button = event.currentTarget;
      try {
        if (action.busyText) setButtonBusy(button, true, action.busyText);
        const result = await action.onClick?.(overlay);
        if (action.close !== false && result !== false) closeOverlay();
      } catch (error) {
        setButtonBusy(button, false);
        toast(error.message || '操作失败', 'danger');
      }
    });
  });
  onMount?.(overlay);
  overlay.querySelector('input, select, button')?.focus();
  return overlay;
}

export function openDrawer({ title, subtitle = '', body = '', actions = [], onMount }) {
  closePopover();
  const overlay = document.createElement('div');
  overlay.className = 'drawer-overlay';
  overlay.innerHTML = `<aside class="drawer" role="dialog" aria-modal="true" aria-label="${escapeHtml(title)}"><header class="drawer-header"><div><h2>${escapeHtml(title)}</h2>${subtitle ? `<p>${escapeHtml(subtitle)}</p>` : ''}</div><button class="icon-button" type="button" data-close-overlay aria-label="关闭">${icon('x')}</button></header><div class="drawer-body">${body}</div>${actions.length ? `<footer class="drawer-actions">${actions.map((action, index) => `<button class="button ${action.variant || 'secondary'}" type="button" data-drawer-action="${index}">${action.icon ? icon(action.icon) : ''}${escapeHtml(action.label)}</button>`).join('')}</footer>` : ''}</aside>`;
  overlayRoot().replaceChildren(overlay);
  document.body.style.overflow = 'hidden';
  bindOverlayDismiss(overlay);
  actions.forEach((action, index) => {
    overlay.querySelector(`[data-drawer-action="${index}"]`).addEventListener('click', async (event) => {
      const button = event.currentTarget;
      try {
        if (action.busyText) setButtonBusy(button, true, action.busyText);
        const result = await action.onClick?.(overlay);
        if (action.close !== false && result !== false) closeOverlay();
      } catch (error) {
        setButtonBusy(button, false);
        toast(error.message || '操作失败', 'danger');
      }
    });
  });
  onMount?.(overlay);
  return overlay;
}

export function confirmAction({ title, message, confirmLabel = '确认', danger = false, detail = '' }) {
  return new Promise((resolve) => {
    openModal({
      title,
      subtitle: message,
      body: detail ? `<div class="notice ${danger ? 'danger' : 'warning'}">${icon(danger ? 'alert' : 'help')}<div><strong>${danger ? '此操作需要谨慎确认' : '操作确认'}</strong><span>${escapeHtml(detail)}</span></div></div>` : '',
      actions: [
        { label: '取消', variant: 'ghost', onClick: () => resolve(false) },
        { label: confirmLabel, variant: danger ? 'danger' : 'primary', onClick: () => resolve(true) },
      ],
    });
  });
}

export function openPopover(anchor, content, onMount) {
  closePopover();
  const node = document.createElement('div');
  node.className = 'popover';
  node.innerHTML = content;
  popoverRoot().replaceChildren(node);
  const rect = anchor.getBoundingClientRect();
  const width = 260;
  node.style.left = `${Math.max(10, Math.min(window.innerWidth - width - 10, rect.right - width))}px`;
  node.style.top = `${Math.min(window.innerHeight - node.offsetHeight - 10, rect.bottom + 7)}px`;
  onMount?.(node);
  window.setTimeout(() => {
    popoverDismiss = function dismiss(event) {
      if (!node.contains(event.target) && !anchor.contains(event.target)) {
        closePopover();
      }
    };
    document.addEventListener('click', popoverDismiss);
  }, 0);
  return node;
}

export function downloadFile(filename, content, type = 'application/json') {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function objectsToCsv(rows, fields) {
  const header = fields.map((field) => csvEscape(field.label)).join(',');
  const body = rows.map((row) => fields.map((field) => csvEscape(row[field.key])).join(',')).join('\n');
  return `\uFEFF${header}\n${body}`;
}

export function bindEscapeKey() {
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      closeOverlay();
      closePopover();
    }
  });
}
