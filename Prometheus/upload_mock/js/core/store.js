import { createSeedData } from './data.js';
import { deepClone, nextId, nowText } from './utils.js';

const LEGACY_STORAGE_KEY = 'zhice-knowledge-ops-v3';
const listeners = new Set();

try {
  window.localStorage.removeItem(LEGACY_STORAGE_KEY);
} catch {
  // Storage may be unavailable in privacy-restricted browser contexts.
}

let state = createSeedData();

function touch() {
  state.meta.updatedAt = new Date().toISOString();
}

function emit(reason = 'update') {
  listeners.forEach((listener) => listener(state, reason));
}

export function getState() {
  return state;
}

export function update(recipe, reason = 'update') {
  recipe(state);
  touch();
  emit(reason);
  return state;
}

export function subscribe(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function resetState() {
  const count = Number(state.meta?.resetCount || 0) + 1;
  state = createSeedData();
  state.meta.resetCount = count;
  touch();
  emit('reset');
}

export function exportState() {
  return deepClone(state);
}

export function activeWorkspace() {
  return state.workspaces.find((item) => item.id === state.activeWorkspaceId) || state.workspaces[0];
}

export function activeVersion() {
  return state.versions.find((item) => item.status === 'active') || null;
}

export function addAudit(action, target, result = 'success', detail = '', extra = {}) {
  state.audits.unshift({
    id: nextId('audit'),
    time: new Date().toISOString(),
    actor: extra.actor || state.user.name,
    action,
    target,
    result,
    ip: extra.ip || '10.24.18.36',
    requestId: extra.requestId || nextId('req'),
    detail,
  });
}

export function addNotification(type, title, body, route) {
  state.notifications.unshift({ id: nextId('notice'), type, title, body, time: new Date().toISOString(), read: false, route });
}

export function describeState() {
  return `${nowText()} · ${state.sources.length} sources · ${state.jobs.length} jobs · ${state.versions.length} versions`;
}
