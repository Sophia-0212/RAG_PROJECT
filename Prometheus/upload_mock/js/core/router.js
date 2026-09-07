const routeListeners = new Set();

export const routes = {
  '/overview': { name: 'overview', title: '运营总览', group: '知识运营' },
  '/sources': { name: 'sources', title: '知识源', group: '知识运营' },
  '/sources/new': { name: 'newSource', title: '新建摄取任务', group: '知识源' },
  '/jobs': { name: 'jobs', title: '摄取任务', group: '知识运营' },
  '/jobs/review': { name: 'manualReview', title: '人工复核', group: '摄取任务' },
  '/versions': { name: 'versions', title: '版本发布', group: '知识运营' },
  '/quality': { name: 'quality', title: '质量评测', group: '知识运营' },
  '/quality/online': { name: 'onlineEffect', title: '上线效果', group: '质量评测' },
  '/audit': { name: 'audit', title: '权限审计', group: '知识运营' },
  '/settings': { name: 'settings', title: '环境配置', group: '系统' },
};

export function currentRoute() {
  const raw = window.location.hash.replace(/^#/, '') || '/overview';
  const [path, queryString = ''] = raw.split('?');
  const normalized = routes[path] ? path : '/overview';
  return { ...routes[normalized], path: normalized, query: new URLSearchParams(queryString) };
}

export function navigate(path, params = {}) {
  const query = new URLSearchParams(params).toString();
  window.location.hash = `${path}${query ? `?${query}` : ''}`;
}

export function subscribeRoute(listener) {
  routeListeners.add(listener);
  return () => routeListeners.delete(listener);
}

export function startRouter() {
  if (!window.location.hash || !routes[window.location.hash.replace(/^#/, '').split('?')[0]]) {
    window.history.replaceState(null, '', `${window.location.pathname}#/overview`);
  }
  const notify = () => routeListeners.forEach((listener) => listener(currentRoute()));
  window.addEventListener('hashchange', notify);
  notify();
  return () => window.removeEventListener('hashchange', notify);
}
