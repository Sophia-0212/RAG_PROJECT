import { icon } from '../upload_mock/js/core/icons.js';

const documents = {
  renewal: {
    title: '企业版续费与升级指引', source: 'wiki://crm/customer-success/renewal', version: 'v3.4',
    business: '客户成功', tenant: 'crm-demo', acl: 'group:customer-success', effective: '2026-07-01 至长期',
    excerpt: '企业版到期前30天由客户成功经理发起续费确认，核对席位、合同主体和续费周期后生成续费订单。',
    terms: ['企业版', '续费', '流程'], intent: 'renewal', authorized: true,
  },
  refund: {
    title: '企业版7日无理由退款政策', source: 'wiki://crm/product/refund-policy', version: 'v2.8',
    business: '产品政策', tenant: 'crm-demo', acl: 'group:sales', effective: '2026-03-01 至长期',
    excerpt: '企业版用户申请退款，需在购买后7个自然日内提交，且产品必须处于未激活状态。',
    terms: ['企业版', '购买', '退款'], intent: 'refund', authorized: true,
  },
  upgrade: {
    title: '企业版套餐升级操作手册', source: 's3://crm-knowledge/sop/package-upgrade', version: 'v1.9',
    business: '客户成功', tenant: 'crm-demo', acl: 'group:customer-success', effective: '2026-05-15 至长期',
    excerpt: '套餐升级需先确认当前合同余量，再由客户成功经理创建变更单并提交商务复核。',
    terms: ['企业版', '升级', '操作'], intent: 'upgrade', authorized: true,
  },
  invoice: {
    title: '续费订单开票与回款说明', source: 'wiki://crm/finance/renewal-invoice', version: 'v2.1',
    business: '财务协同', tenant: 'crm-demo', acl: 'group:customer-success', effective: '2026-01-01 至长期',
    excerpt: '续费订单完成签章并确认回款后可申请开票，发票抬头必须与合同主体一致。',
    terms: ['续费', '订单', '流程'], intent: 'renewal', authorized: true,
  },
  tags: {
    title: '客户标签修改权限矩阵', source: 'wiki://crm/account/tag-permission', version: 'v4.0',
    business: '客户管理', tenant: 'crm-demo', acl: 'role:sales_manager', effective: '2026-08-01 至长期',
    excerpt: '销售经理可修改经营属性标签；风险、行业资质和客户等级标签需对应数据Owner审批。',
    terms: ['客户', '标签', '权限'], intent: 'permission', authorized: true,
  },
  taxonomy: {
    title: 'CRM客户标签体系介绍', source: 'wiki://crm/account/tag-taxonomy', version: 'v5.2',
    business: '客户管理', tenant: 'crm-demo', acl: 'group:sales', effective: '2026-02-01 至长期',
    excerpt: '客户标签分为基础属性、经营属性、意向特征和风险特征四类，用于客户分群与运营分析。',
    terms: ['客户', '标签', '体系'], intent: 'definition', authorized: true,
  },
  transfer: {
    title: '批量客户转移与回滚SOP', source: 'wiki://crm/account/batch-transfer', version: 'v1.6',
    business: '客户管理', tenant: 'crm-demo', acl: 'role:operations', effective: '2026-06-20 至长期',
    excerpt: '批量转移完成后，如需回滚，应在24小时内使用原批次号创建逆向任务并由区域运营负责人审批。',
    terms: ['批量', '转移', '回滚'], intent: 'rollback', authorized: true,
  },
  assignment: {
    title: '单客户归属变更流程', source: 'wiki://crm/account/assignment-change', version: 'v3.1',
    business: '客户管理', tenant: 'crm-demo', acl: 'group:sales', effective: '2026-04-10 至长期',
    excerpt: '单个客户归属变更需由原负责人确认，并通过客户归属变更单完成交接。',
    terms: ['客户', '归属', '变更'], intent: 'assignment', authorized: true,
  },
  grading: {
    title: '客户分级规则', source: 'wiki://crm/account/grading-rule', version: 'v3.0',
    business: '客户管理', tenant: 'crm-demo', acl: 'group:sales', effective: '2026-07-15 至长期',
    excerpt: '客户等级按近12个月消耗、回款及时性、增长潜力和合规风险每日06:00自动计算。',
    terms: ['客户', '分级', '规则'], intent: 'definition', authorized: true,
  },
  gradingChange: {
    title: '客户分级调整流程', source: 'wiki://crm/account/grading-change', version: 'v2.5',
    business: '客户管理', tenant: 'crm-demo', acl: 'role:sales_manager', effective: '2026-07-15 至长期',
    excerpt: '客户分级由系统自动计算，人工发现数据异常时可发起复核，不支持销售直接修改等级。',
    terms: ['客户', '分级', '调整'], intent: 'operation', authorized: true,
  },
  otherBusiness: {
    title: '广告计划层级客户分群规则', source: 'wiki://ads/campaign/audience-tier', version: 'v7.2',
    business: '广告投放', tenant: 'crm-demo', acl: 'group:campaign-ops', effective: '2026-06-01 至长期',
    excerpt: '投放计划可按客户分群标签调整出价策略，本规则不用于CRM客户等级计算。',
    terms: ['客户', '分级', '规则'], intent: 'campaign', authorized: false,
  },
};

const scenarios = [
  {
    id: 'CRM-3210', priority: 'P0', kind: 'Bug', short: '续费问题召回退款政策', owner: '陈昊',
    query: '企业版续费流程', rewritten: '企业版到期后如何完成续费、签约和订单确认？',
    expected: 'renewal', selected: 'refund', conclusion: 'BM25共享高权重词“企业版”导致退款政策分数虚高，1:1融合后错误候选升至Top1。',
    recommendation: '降低稀疏权重，并在融合前过滤语义相似度过低且意图冲突的候选。',
    config: { denseWeight: 50, prefilter: false, rewrite: false, rerank: false, threshold: '0.00' },
    scores: {
      renewal: [0.91, 8.42, 0.0320, 0.96], refund: [0.63, 14.82, 0.0323, 0.14],
      upgrade: [0.82, 5.96, 0.0315, 0.58], invoice: [0.78, 6.10, 0.0315, 0.72],
      taxonomy: [0.44, 3.82, 0.0304, 0.09],
    },
    latency: [41, 28, 3, 0],
  },
  {
    id: 'CRM-3211', priority: 'P1', kind: 'Story', short: '短Query意图不稳定', owner: '周涵',
    query: '这个客户能不能改标签', rewritten: '销售经理是否有权限修改当前客户的经营属性标签？',
    expected: 'tags', selected: 'taxonomy', conclusion: '原始Query缺少角色与“修改权限”意图，权限矩阵和标签介绍的分数过于接近。',
    recommendation: '结合对话历史进行Query改写后再检索，并保留原始Query用于审计。',
    config: { denseWeight: 60, prefilter: false, rewrite: false, rerank: true, threshold: '0.00' },
    scores: {
      tags: [0.71, 7.42, 0.0318, 0.62], taxonomy: [0.76, 9.35, 0.0323, 0.74],
      assignment: [0.61, 5.83, 0.0308, 0.41], gradingChange: [0.56, 4.72, 0.0304, 0.35],
    },
    latency: [38, 24, 3, 34],
  },
  {
    id: 'CRM-3212', priority: 'P2', kind: 'Task', short: '长尾SOP重排偏低', owner: '赵蕾',
    query: '批量转移客户后怎么回滚', rewritten: '批量客户转移任务完成后，如何按原批次执行回滚？',
    expected: 'transfer', selected: 'assignment', conclusion: '正确SOP已进入召回Top10，但CrossEncoder对低频操作细节的打分低于字面相近文档。',
    recommendation: '补充低频高价值操作的困难负样本，按长尾切片单独评估重排模型。',
    config: { denseWeight: 55, prefilter: true, rewrite: false, rerank: true, threshold: '0.00' },
    scores: {
      transfer: [0.82, 10.64, 0.0325, 0.38], assignment: [0.77, 9.92, 0.0320, 0.57],
      gradingChange: [0.61, 5.04, 0.0308, 0.31], taxonomy: [0.48, 3.82, 0.0299, 0.18],
    },
    latency: [44, 31, 3, 39],
  },
  {
    id: 'CRM-3213', priority: 'P2', kind: 'Story', short: '业务线噪声占位', owner: '孙睿',
    query: '客户分级规则是什么', rewritten: 'CRM客户等级的计算规则和重算周期是什么？',
    expected: 'grading', selected: 'otherBusiness', conclusion: '全量Chunk池中，广告投放业务线的同词文档占据排序位置，形成跨业务线噪声。',
    recommendation: '根据可信用户组织信息进行业务线预过滤，再执行Dense与BM25混合召回。',
    config: { denseWeight: 55, prefilter: false, rewrite: false, rerank: true, threshold: '0.00' },
    scores: {
      grading: [0.86, 11.20, 0.0325, 0.91], otherBusiness: [0.89, 13.62, 0.0328, 0.93],
      gradingChange: [0.82, 10.42, 0.0320, 0.76], taxonomy: [0.63, 6.14, 0.0308, 0.42],
    },
    latency: [47, 35, 3, 38],
  },
  {
    id: 'CRM-3214', priority: 'P1', kind: 'Bug', short: '高并发融合结果漂移', owner: '刘阳',
    query: '客户分级规则是什么', rewritten: 'CRM客户等级由哪些指标计算，多久重算一次？',
    expected: 'grading', selected: 'gradingChange', conclusion: 'BM25在高并发下偶发超时并返回空列表，使每次参与RRF融合的候选集合不同。',
    recommendation: '统一两路召回超时预算，并为稀疏召回降级增加指标、Trace事件与告警。',
    config: { denseWeight: 50, prefilter: true, rewrite: false, rerank: false, threshold: '0.00' },
    scores: {
      grading: [0.91, 12.42, 0.0328, 0.95], gradingChange: [0.87, 11.84, 0.0325, 0.78],
      taxonomy: [0.65, 6.18, 0.0313, 0.43], assignment: [0.55, 4.91, 0.0305, 0.34],
    },
    latency: [52, 120, 3, 0], sparseDegraded: true,
  },
];

const state = {
  scenarioId: scenarios[0].id,
  query: scenarios[0].query,
  config: { ...scenarios[0].config },
  selectedId: scenarios[0].selected,
  selectedStage: 'rrf',
  repaired: false,
  running: false,
  runCount: 1,
  mobileOpen: false,
};

const app = document.querySelector('#app');
const scenario = () => scenarios.find((item) => item.id === state.scenarioId);
const safe = (value) => String(value).replace(/[&<>'"]/g, (char) => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', "'":'&#39;', '"':'&quot;' }[char]));

function rankMap(items) {
  return Object.fromEntries(items.map((item, index) => [item.id, index + 1]));
}

function compute() {
  const active = scenario();
  const scoreLookup = Object.fromEntries(
    Object.entries(active.scores).map(([id, scores]) => [id, [...scores]]),
  );
  if (active.id === 'CRM-3211' && state.config.rewrite) {
    scoreLookup.tags = [0.91, 12.40, 0.0330, 0.94];
    scoreLookup.taxonomy = [0.68, 8.10, 0.0319, 0.52];
  }
  let ids = Object.keys(active.scores);
  if (state.config.prefilter) ids = ids.filter((id) => documents[id].business !== '广告投放');
  if (Number(state.config.threshold) > 0) ids = ids.filter((id) => scoreLookup[id][0] >= Number(state.config.threshold));
  const dense = ids.map((id) => ({ id, score: scoreLookup[id][0] })).sort((a,b) => b.score-a.score);
  let sparse = ids.map((id) => ({ id, score: scoreLookup[id][1] })).sort((a,b) => b.score-a.score);
  const degraded = active.sparseDegraded && !state.repaired;
  if (degraded) sparse = [];
  const dRank = rankMap(dense);
  const sRank = rankMap(sparse);
  const dw = Number(state.config.denseWeight) / 100;
  const sw = 1 - dw;
  const fusion = ids.map((id) => {
    const densePart = dRank[id] ? dw / (60 + dRank[id]) : 0;
    const sparsePart = sRank[id] ? sw / (60 + sRank[id]) : 0;
    return { id, score: densePart + sparsePart };
  }).sort((a,b) => b.score-a.score);
  const rerank = fusion.map((item) => ({ id: item.id, score: scoreLookup[item.id][3] })).sort((a,b) => b.score-a.score);
  const final = state.config.rerank ? rerank : fusion;
  return { dense, sparse, fusion, rerank, final, degraded, scoreLookup };
}

function stageCard(name, subtitle, items, scoreType, time, number, degraded = false) {
  const candidates = degraded
    ? `<div class="empty-stage">${icon('alert')}<br>稀疏召回超时<br><span class="mono">fallback=[]</span></div>`
    : items.map((item, index) => {
      const doc = documents[item.id];
      const problem = item.id !== scenario().expected && index === 0;
      const value = scoreType === 'bm25' ? item.score.toFixed(2) : item.score.toFixed(scoreType === 'rrf' ? 4 : 2);
      return `<button class="candidate ${state.selectedId === item.id && state.selectedStage === scoreType ? 'selected' : ''} ${problem ? 'problem' : ''}" data-candidate="${item.id}" data-stage="${scoreType}">
        <span class="rank">${index + 1}</span>
        <span class="candidate-body">
          <strong class="candidate-title">${safe(doc.title)}</strong>
          <span class="candidate-meta"><span>${safe(doc.business)}</span><span class="score ${item.score > .8 && scoreType !== 'bm25' && scoreType !== 'rrf' ? 'high' : ''}">${value}</span></span>
          <span class="candidate-preview">${safe(doc.excerpt)}</span>
        </span>
      </button>`;
    }).join('');
  return `<section class="stage">
    <header class="stage-head">
      <div class="stage-title"><span class="stage-index">0${number}</span><span><strong>${name}</strong><small>${subtitle}</small></span></div>
      <span class="stage-time">${degraded ? 'TIMEOUT' : time + 'ms'}</span>
    </header>
    <div class="candidate-list">${candidates}</div>
  </section>`;
}

function detail(result) {
  const active = scenario();
  const doc = documents[state.selectedId] || documents[active.expected];
  const denseRank = rankMap(result.dense)[state.selectedId] || '--';
  const sparseRank = rankMap(result.sparse)[state.selectedId] || '--';
  const fusionRank = rankMap(result.fusion)[state.selectedId] || '--';
  const rerankRank = rankMap(result.rerank)[state.selectedId] || '--';
  const scores = result.scoreLookup[state.selectedId] || [0,0,0,0];
  const fusionScore = result.fusion.find((item) => item.id === state.selectedId)?.score || 0;
  const expected = state.selectedId === active.expected;
  const reason = expected
    ? '这是本案例的标准相关文档。检查它是否在召回阶段进入候选，并在融合/重排后保持靠前。'
    : active.conclusion;
  return `<aside class="detail-panel">
    <header class="panel-header"><div><h2>候选详情</h2><p>解释为什么它会出现在当前排名</p></div><span class="chip mono">${safe(state.selectedStage)}</span></header>
    <div class="detail-body">
      <h3 class="detail-title">${safe(doc.title)}</h3>
      <div class="detail-tags"><span class="tag">${safe(doc.business)}</span><span class="tag allowed">权限通过</span><span class="tag">${safe(doc.version)}</span></div>
      <blockquote class="excerpt">${safe(doc.excerpt)}</blockquote>
      <h4 class="section-title">匹配词</h4>
      <div class="match-terms">${doc.terms.map((term) => `<span>${safe(term)}</span>`).join('')}</div>
      <div class="rank-reason ${expected ? 'good' : ''}"><strong>${expected ? '标准证据' : '异常解释'}</strong><br>${safe(reason)}</div>
      <h4 class="section-title">分数与排名迁移</h4>
      <div class="score-path">
        <div class="score-row"><label>Dense</label><span class="bar"><i style="width:${Math.round(scores[0]*100)}%"></i></span><strong>${scores[0].toFixed(2)} · #${denseRank}</strong></div>
        <div class="score-row"><label>BM25</label><span class="bar"><i style="width:${Math.min(100,Math.round(scores[1]/15*100))}%"></i></span><strong>${scores[1].toFixed(2)} · #${sparseRank}</strong></div>
        <div class="score-row"><label>RRF</label><span class="bar"><i style="width:${Math.min(100,Math.round(fusionScore/.034*100))}%"></i></span><strong>${fusionScore.toFixed(4)} · #${fusionRank}</strong></div>
        <div class="score-row"><label>CrossEncoder</label><span class="bar"><i style="width:${Math.round(scores[3]*100)}%"></i></span><strong>${scores[3].toFixed(2)} · #${rerankRank}</strong></div>
      </div>
      <h4 class="section-title">治理元数据</h4>
      <dl class="metadata">
        <div><dt>source</dt><dd>${safe(doc.source)}</dd></div>
        <div><dt>tenant_id</dt><dd>${safe(doc.tenant)}</dd></div>
        <div><dt>ACL</dt><dd>${safe(doc.acl)}</dd></div>
        <div><dt>effective</dt><dd>${safe(doc.effective)}</dd></div>
        <div><dt>intent</dt><dd>${safe(doc.intent)}</dd></div>
      </dl>
    </div>
    <footer class="detail-footer"><button class="button secondary" id="copyChunk">${icon('clipboard')}复制Chunk ID</button><button class="button secondary" id="markRelevant">${icon('check')}标记相关</button></footer>
  </aside>`;
}

function metrics(result) {
  const active = scenario();
  const finalTop = result.final[0]?.id;
  const hit = finalTop === active.expected;
  const sparseTime = result.degraded ? 120 : (active.id === 'CRM-3214' && state.repaired ? 34 : active.latency[1]);
  const total = active.latency[0] + sparseTime + active.latency[2]
    + (state.config.rerank ? (active.latency[3] || 36) : 0)
    + (state.config.rewrite ? 46 : 0);
  return `<section class="metrics">
    <article class="metric ${hit ? 'good' : 'alert'}"><span class="metric-label">最终Top1 ${icon(hit ? 'checkCircle' : 'alert')}</span><strong>${hit ? '命中' : '偏离'}</strong><small>${safe(documents[finalTop]?.title || '无候选')}</small></article>
    <article class="metric"><span class="metric-label">候选数量</span><strong>${result.fusion.length}</strong><small>融合后去重候选</small></article>
    <article class="metric"><span class="metric-label">总耗时</span><strong>${total} ms</strong><small>${state.config.rewrite ? '含Query改写 46ms' : '不含生成阶段'}</small></article>
    <article class="metric ${result.degraded ? 'alert' : ''}"><span class="metric-label">召回状态</span><strong>${result.degraded ? '降级' : '双路正常'}</strong><small>${result.degraded ? 'BM25 timeout → []' : 'Dense + BM25'}</small></article>
    <article class="metric"><span class="metric-label">Trace</span><strong>#${String(state.runCount).padStart(3,'0')}</strong><small class="mono">req-retrieval-debug</small></article>
  </section>`;
}

function render() {
  const active = scenario();
  const result = compute();
  const fixed = result.final[0]?.id === active.expected;
  app.innerHTML = `<div class="app-shell">
    <aside class="sidebar ${state.mobileOpen ? 'open' : ''}">
      <div class="brand"><span class="brand-mark"><span></span><span></span><span></span></span><span><strong>知策</strong><small>CRM RETRIEVAL LAB</small></span></div>
      <div class="workspace"><span>商</span><div><small>调试空间</small><strong>商业平台 · 客户运营</strong></div></div>
      <div class="nav-label">问题案例</div>
      <nav class="scenario-list" aria-label="调试案例">
        ${scenarios.map((item) => `<button class="scenario-button ${item.id === state.scenarioId ? 'active' : ''}" data-scenario="${item.id}"><span class="scenario-code">${item.id.slice(-2)}</span><span class="scenario-copy"><strong>${safe(item.short)}</strong><small><span class="severity ${item.priority.toLowerCase()}">${item.kind}-${item.priority}</span> · ${item.owner}</small></span></button>`).join('')}
      </nav>
      <div class="sidebar-note"><strong>学习提示</strong><br>先看各阶段Top1是否变化，再点开异常候选检查分数、命中词、业务线和ACL元数据。</div>
    </aside>
    <div class="scrim ${state.mobileOpen ? 'open' : ''}" id="scrim"></div>
    <div class="page-shell">
      <header class="topbar">
        <div class="breadcrumb"><button class="button secondary icon-only mobile-menu" id="mobileMenu" aria-label="打开案例列表">${icon('menu')}</button><span>知识运营</span>${icon('chevronRight')}<strong>检索实验室</strong></div>
        <div class="topbar-actions"><span class="trace-badge">index: rag_active@20260905</span><span class="env-badge">模拟环境</span></div>
      </header>
      <main class="page-main">
        <header class="page-heading"><div><span class="eyebrow">${active.id} · ${active.kind}-${active.priority}</span><h1>检索调试面板</h1><p>复现员工Query，逐阶段观察候选、分数与排名变化，定位问题发生在召回、融合还是重排序。</p></div><div class="heading-actions"><button class="button secondary" id="resetBtn">${icon('refresh')}<span>重置参数</span></button><button class="button primary" id="runBtn">${icon('play')}<span>运行检索</span></button></div></header>
        <section class="query-panel">
          <div class="query-main">
            <div><div class="field-label"><span>复现 Query</span><span class="mono">${active.owner} · 刚刚</span></div><div class="query-input-wrap"><textarea class="query-input" id="queryInput">${safe(state.query)}</textarea><button class="run-inline" id="runInline" aria-label="运行检索" title="运行检索">${icon('play')}</button></div><div class="rewrite-row"><strong>改写后</strong><span>${state.config.rewrite ? safe(active.rewritten) : '未启用 Query Rewrite，当前直接使用原始问题检索'}</span></div></div>
            <div class="controls-grid">
              <div class="control"><label>召回 Top K</label><select id="topK"><option>10</option><option selected>16</option><option>24</option></select></div>
              <div class="control"><label>融合算法</label><select><option selected>RRF · k=60</option><option>Weighted Score</option></select></div>
              <div class="control"><label>语义阈值</label><select id="threshold"><option value="0.00" ${state.config.threshold==='0.00'?'selected':''}>关闭</option><option value="0.40" ${state.config.threshold==='0.40'?'selected':''}>≥ 0.40</option><option value="0.65" ${state.config.threshold==='0.65'?'selected':''}>≥ 0.65</option></select></div>
              <div class="control"><label>精排</label><div class="toggle-control"><input id="rerankToggle" type="checkbox" ${state.config.rerank?'checked':''}><span>CrossEncoder</span></div></div>
              <div class="control weight-control"><label>Dense / BM25 权重</label><div class="range-line"><input id="weightRange" type="range" min="0" max="100" value="${state.config.denseWeight}"><span class="range-value">${state.config.denseWeight}/${100-state.config.denseWeight}</span></div></div>
              <div class="control"><label>Query Rewrite</label><div class="toggle-control"><input id="rewriteToggle" type="checkbox" ${state.config.rewrite?'checked':''}><span>结合会话改写</span></div></div>
              <div class="control"><label>业务线预过滤</label><div class="toggle-control"><input id="prefilterToggle" type="checkbox" ${state.config.prefilter?'checked':''}><span>客户管理</span></div></div>
            </div>
          </div>
          <footer class="query-footer"><div class="identity-line"><span class="chip">tenant: crm-demo</span><span class="chip">role: retrieval_engineer</span><span class="chip">business: ${active.id==='CRM-3210'?'客户成功':'客户管理'}</span><span class="chip">ACL filter: on</span></div><div class="quick-actions"><button id="loadFix">应用建议修复参数</button><span class="mono">|</span><button id="toggleExpected">选择标准证据</button></div></footer>
        </section>
        ${metrics(result)}
        <section class="diagnostic ${fixed ? 'good' : ''}"><span class="diagnostic-icon">${icon(fixed ? 'checkCircle':'alert')}</span><span><strong>${fixed ? '当前参数已命中标准Top1' : active.conclusion}</strong><small>${fixed ? '继续检查Top10覆盖、引用版本和其他评测切片，不能只看这一条Case。' : active.recommendation}</small></span><button class="button secondary" id="diagnoseBtn">${icon('sliders')}${fixed ? '查看当前配置':'应用修复并对比'}</button></section>
        <div class="workbench">
          <section class="results-panel">
            <header class="panel-header"><div><h2>候选排名流水线</h2><p>点击任意候选，查看它在四个阶段的分数和排名变化</p></div><div class="stage-legend"><span><i class="dense"></i>语义</span><span><i class="sparse"></i>字面</span><span><i class="fused"></i>融合</span><span><i class="rerank"></i>精排</span></div></header>
            <div class="stage-grid">
              ${stageCard('Dense Recall','Milvus · IP',result.dense,'dense',active.latency[0],1)}
              ${stageCard('BM25 Recall','Sparse · BM25',result.sparse,'bm25',active.latency[1],2,result.degraded)}
              ${stageCard('RRF Fusion',`${state.config.denseWeight}:${100-state.config.denseWeight} · k=60`,result.fusion,'rrf',active.latency[2],3)}
              ${stageCard('CrossEncoder',state.config.rerank?'已参与最终排序':'仅观察 · 未启用',result.rerank,'rerank',active.latency[3],4)}
            </div>
          </section>
          ${detail(result)}
        </div>
      </main>
    </div>
  </div>`;
  bindEvents();
}

function selectScenario(id) {
  const next = scenarios.find((item) => item.id === id);
  state.scenarioId = id;
  state.query = next.query;
  state.config = { ...next.config };
  state.selectedId = next.selected;
  state.selectedStage = 'rrf';
  state.repaired = false;
  state.mobileOpen = false;
  render();
}

function applyFix() {
  const id = state.scenarioId;
  if (id === 'CRM-3210') Object.assign(state.config, { denseWeight: 70, threshold: '0.65', rerank: true });
  if (id === 'CRM-3211') Object.assign(state.config, { rewrite: true, denseWeight: 70 });
  if (id === 'CRM-3212') Object.assign(state.config, { rerank: false, denseWeight: 65 });
  if (id === 'CRM-3213') Object.assign(state.config, { prefilter: true });
  if (id === 'CRM-3214') Object.assign(state.config, { rerank: true });
  state.repaired = true;
  state.selectedId = scenario().expected;
  state.selectedStage = 'rrf';
  state.runCount += 1;
  render();
  toast('已加载建议参数并重新模拟，请对比四阶段排名', 'success');
}

function run() {
  if (state.running) return;
  state.query = document.querySelector('#queryInput').value.trim() || scenario().query;
  state.running = true;
  const buttons = [document.querySelector('#runBtn'), document.querySelector('#runInline')];
  buttons.forEach((button) => { if (button) button.disabled = true; });
  window.setTimeout(() => {
    state.running = false;
    state.runCount += 1;
    render();
    toast('模拟检索完成，Trace 已更新', 'success');
  }, 520);
}

function toast(message, type='') {
  const root = document.querySelector('#toastRoot');
  const item = document.createElement('div');
  item.className = `toast ${type}`;
  item.innerHTML = `${icon(type === 'success' ? 'checkCircle' : 'activity')}<span>${safe(message)}</span>`;
  root.appendChild(item);
  window.setTimeout(() => item.remove(), 2600);
}

function bindEvents() {
  document.querySelectorAll('[data-scenario]').forEach((button) => button.addEventListener('click', () => selectScenario(button.dataset.scenario)));
  document.querySelectorAll('[data-candidate]').forEach((button) => button.addEventListener('click', () => {
    state.selectedId = button.dataset.candidate;
    state.selectedStage = button.dataset.stage;
    render();
  }));
  document.querySelector('#runBtn').addEventListener('click', run);
  document.querySelector('#runInline').addEventListener('click', run);
  document.querySelector('#resetBtn').addEventListener('click', () => selectScenario(state.scenarioId));
  document.querySelector('#loadFix').addEventListener('click', applyFix);
  document.querySelector('#diagnoseBtn').addEventListener('click', applyFix);
  document.querySelector('#toggleExpected').addEventListener('click', () => { state.selectedId = scenario().expected; state.selectedStage='rrf'; render(); });
  document.querySelector('#weightRange').addEventListener('input', (event) => { state.config.denseWeight = Number(event.target.value); state.repaired = false; render(); });
  document.querySelector('#threshold').addEventListener('change', (event) => { state.config.threshold = event.target.value; state.repaired = false; render(); });
  document.querySelector('#rerankToggle').addEventListener('change', (event) => { state.config.rerank = event.target.checked; state.repaired = false; render(); });
  document.querySelector('#rewriteToggle').addEventListener('change', (event) => { state.config.rewrite = event.target.checked; state.repaired = false; render(); });
  document.querySelector('#prefilterToggle').addEventListener('change', (event) => { state.config.prefilter = event.target.checked; state.repaired = false; render(); });
  document.querySelector('#copyChunk').addEventListener('click', async () => {
    const chunkId = `chunk-${state.selectedId}-20260905`;
    try {
      await navigator.clipboard.writeText(chunkId);
      toast(`${chunkId} 已复制`, 'success');
    } catch {
      toast(`Chunk ID: ${chunkId}`);
    }
  });
  document.querySelector('#markRelevant').addEventListener('click', () => toast('已加入本次调试的相关性标注草稿', 'success'));
  document.querySelector('#mobileMenu').addEventListener('click', () => { state.mobileOpen = true; render(); });
  document.querySelector('#scrim').addEventListener('click', () => { state.mobileOpen = false; render(); });
}

render();
