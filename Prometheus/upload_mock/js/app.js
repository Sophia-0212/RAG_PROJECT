import { currentRoute, startRouter, subscribeRoute } from './core/router.js';
import { getState, subscribe } from './core/store.js';
import { bindEscapeKey, closeOverlay, closePopover } from './components/ui.js';
import { mountShell, shellTemplate } from './components/shell.js';
import { renderOverview, mountOverview } from './pages/overview.js';
import { renderSources, mountSources } from './pages/sources.js';
import { renderNewSource, mountNewSource } from './pages/new-source.js';
import { renderJobs, mountJobs } from './pages/jobs.js';
import { renderManualReview, mountManualReview } from './pages/manual-review.js';
import { renderVersions, mountVersions } from './pages/versions.js';
import { renderQuality, mountQuality } from './pages/quality.js';
import { renderOnlineEffect, mountOnlineEffect } from './pages/online-effect.js';
import { renderAudit, mountAudit } from './pages/audit.js';
import { renderSettings, mountSettings } from './pages/settings.js';

const pages = {
  overview: { render: renderOverview, mount: mountOverview },
  sources: { render: renderSources, mount: mountSources },
  newSource: { render: renderNewSource, mount: mountNewSource },
  jobs: { render: renderJobs, mount: mountJobs },
  manualReview: { render: renderManualReview, mount: mountManualReview },
  versions: { render: renderVersions, mount: mountVersions },
  quality: { render: renderQuality, mount: mountQuality },
  onlineEffect: { render: renderOnlineEffect, mount: mountOnlineEffect },
  audit: { render: renderAudit, mount: mountAudit },
  settings: { render: renderSettings, mount: mountSettings },
};
let pageCleanup = null;
let rendering = false;

function renderApplication(route = currentRoute()) {
  if (rendering) return;
  rendering = true;
  try {
    const activeId = document.activeElement?.id;
    const selectionStart = document.activeElement?.selectionStart;
    pageCleanup?.();
    pageCleanup = null;
    const state = getState();
    const app = document.getElementById('app');
    app.innerHTML = shellTemplate(route, state);
    const page = pages[route.name] || pages.overview;
    const outlet = document.getElementById('routeOutlet');
    outlet.innerHTML = page.render(state, route);
    mountShell();
    pageCleanup = page.mount?.(outlet, state, () => renderApplication(currentRoute()), route) || null;
    if (activeId) {
      const nextActive = document.getElementById(activeId);
      nextActive?.focus();
      if (Number.isInteger(selectionStart) && nextActive?.setSelectionRange) nextActive.setSelectionRange(selectionStart, selectionStart);
    }
    document.title = `${route.title} - 知策 CRM 知识运营台`;
  } finally {
    rendering = false;
  }
}

bindEscapeKey();
subscribe(() => renderApplication(currentRoute()));
subscribeRoute((route) => renderApplication(route));
startRouter();

window.addEventListener('beforeunload', () => {
  closeOverlay();
  closePopover();
  pageCleanup?.();
});
