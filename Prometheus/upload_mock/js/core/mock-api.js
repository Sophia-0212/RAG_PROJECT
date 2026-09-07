import { addAudit, addNotification, getState, update } from './store.js';
import { delay, nextId } from './utils.js';

async function transact(recipe, reason, ms = 260) {
  await delay(ms);
  const state = getState();
  const workspace = state.workspaces.find((item) => item.id === state.activeWorkspaceId);
  const allowedForReadOnly = ['workspace-switched', 'notifications-read', 'notification-read'];
  if (workspace?.role === '只读审计员' && !allowedForReadOnly.includes(reason)) {
    update(() => addAudit('PERMISSION_DENIED', reason, 'denied', `当前工作空间角色“${workspace.role}”没有写权限。`), 'permission-denied');
    throw new Error('当前工作空间为只读审计模式，不能执行写操作');
  }
  return update(recipe, reason);
}

function sourceById(id) {
  return getState().sources.find((item) => item.id === id);
}

function jobById(id) {
  return getState().jobs.find((item) => item.id === id);
}

function versionById(id) {
  return getState().versions.find((item) => item.id === id);
}

function reviewByJobId(jobId) {
  return getState().reviewBatches.find((item) => item.jobId === jobId);
}

function scheduleJob(jobId) {
  const stages = [
    { progress: 24, stage: '扫描来源', log: '来源快照扫描完成' },
    { progress: 51, stage: '治理与切分', log: '已生成稳定文档与 Chunk 标识' },
    { progress: 79, stage: '写入 Collection', log: 'Milvus 批量写入进行中' },
    { progress: 100, stage: '完成', log: 'Manifest 与 checkpoint 已持久化' },
  ];
  stages.forEach((item, index) => {
    window.setTimeout(() => {
      update((state) => {
        const job = state.jobs.find((entry) => entry.id === jobId);
        if (!job || job.status === 'canceled') return;
        job.progress = item.progress;
        job.stage = item.stage;
        job.updatedAt = new Date().toISOString();
        job.logs.push(`${new Date().toLocaleTimeString('zh-CN', { hour12: false })} ${item.log}`);
        if (item.progress === 100) {
          job.status = 'completed';
          const source = state.sources.find((entry) => entry.id === job.sourceId);
          if (source) {
            source.health = 'healthy';
            source.status = 'active';
            source.lastSync = new Date().toISOString();
          }
          const collection = `rag_docs_${new Date().toISOString().slice(0, 10).replaceAll('-', '')}_${String(state.versions.length + 1).padStart(3, '0')}`;
          const version = {
            id: nextId('ver'), collection, alias: null, status: 'candidate',
            documents: 126400 + Number(job.added || 0) - Number(job.removed || 0),
            chunks: 1860214 + (Number(job.added || 0) + Number(job.updated || 0)) * 14,
            qualityScore: null, qualityGate: 'pending', createdAt: new Date().toISOString(),
            operator: job.operator, sourceJobId: job.id, notes: `${job.sourceName} 摄取候选版本`,
          };
          state.versions.unshift(version);
          job.candidateVersionId = version.id;
          addAudit('INGESTION_COMPLETED', job.runId, 'success', `候选 Collection ${collection} 构建完成。`);
          addNotification('success', '摄取任务已完成', `${collection} 等待质量评测。`, '/quality');
        }
      }, `job-progress:${jobId}`);
    }, 350 * (index + 1));
  });
}

export async function createSource(payload) {
  let created;
  await transact((state) => {
    const sourceId = nextId('src');
    created = {
      id: sourceId,
      name: payload.name,
      type: payload.type,
      category: payload.category || '未分类',
      owner: state.user.name,
      tenantId: payload.tenantId,
      visibility: payload.visibility,
      acl: payload.visibility === 'public' ? [] : payload.acl,
      status: 'active', health: 'syncing', documents: payload.files?.length || 0, chunks: 0,
      version: '待生成', lastSync: null, uri: payload.uri, schedule: payload.schedule || '手动',
    };
    state.sources.unshift(created);
    addAudit('SOURCE_CREATED', payload.name, 'success', `创建 ${payload.type} 知识源，权限范围为 ${payload.visibility}。`);
  }, 'source-created', 360);
  const job = await createJob(created.id, { type: 'versioned', added: Math.max(1, payload.files?.length || 12), updated: 0, removed: 0 });
  return { source: created, job };
}

export async function updateSource(sourceId, patch) {
  return transact((state) => {
    const source = state.sources.find((item) => item.id === sourceId);
    if (!source) throw new Error('知识源不存在');
    Object.assign(source, patch);
    addAudit('SOURCE_UPDATED', source.name, 'success', '知识源配置或权限范围已更新。');
  }, 'source-updated');
}

export async function toggleSource(sourceId) {
  return transact((state) => {
    const source = state.sources.find((item) => item.id === sourceId);
    if (!source) throw new Error('知识源不存在');
    const paused = source.status === 'paused';
    source.status = paused ? 'active' : 'paused';
    source.health = paused ? 'healthy' : 'paused';
    addAudit(paused ? 'SOURCE_RESUMED' : 'SOURCE_PAUSED', source.name, 'success', paused ? '恢复自动同步。' : '暂停自动同步。');
  }, 'source-toggled');
}

export async function archiveSource(sourceId) {
  return transact((state) => {
    const source = state.sources.find((item) => item.id === sourceId);
    if (!source) throw new Error('知识源不存在');
    source.status = 'archived';
    source.health = 'archived';
    addAudit('SOURCE_ARCHIVED', source.name, 'success', '知识源已归档，现有在线版本不会立即删除。');
  }, 'source-archived');
}

export async function createJob(sourceId, options = {}) {
  const source = sourceById(sourceId);
  if (!source) throw new Error('知识源不存在');
  let job;
  await transact((state) => {
    job = {
      id: nextId('job'), runId: `${source.tenantId}-${Date.now()}`, sourceId, sourceName: source.name,
      type: options.type || 'incremental', status: 'queued', progress: 0, stage: '等待执行',
      createdAt: new Date().toISOString(), updatedAt: new Date().toISOString(), operator: state.user.name,
      added: options.added ?? 3, updated: options.updated ?? 1, removed: options.removed ?? 0,
      unchanged: options.unchanged ?? Math.max(0, source.documents - 4), attempts: 0,
      logs: [`${new Date().toLocaleTimeString('zh-CN', { hour12: false })} 任务已创建，等待执行器领取`],
    };
    state.jobs.unshift(job);
    addAudit('INGESTION_JOB_CREATED', job.runId, 'success', `为 ${source.name} 创建摄取任务。`);
    addNotification('info', '摄取任务已创建', `${job.runId} 正在等待执行。`, '/jobs');
  }, 'job-created');
  await startJob(job.id);
  return job;
}

export async function syncSource(sourceId) {
  const source = sourceById(sourceId);
  if (!source) throw new Error('知识源不存在');
  if (source.status === 'archived') throw new Error('已归档知识源不能同步');
  return createJob(sourceId, { type: 'incremental', added: 2, updated: 3, removed: 0 });
}

export async function startJob(jobId) {
  const job = jobById(jobId);
  if (!job) throw new Error('摄取任务不存在');
  await transact((state) => {
    const current = state.jobs.find((item) => item.id === jobId);
    current.status = 'running';
    current.progress = Math.min(current.progress || 0, 15);
    current.stage = current.attempts > 0 ? '从 checkpoint 恢复' : '初始化执行器';
    current.attempts += 1;
    current.updatedAt = new Date().toISOString();
    current.error = null;
    current.logs.push(`${new Date().toLocaleTimeString('zh-CN', { hour12: false })} 第 ${current.attempts} 次执行开始`);
    addAudit(current.attempts > 1 ? 'JOB_RESUMED' : 'JOB_STARTED', current.runId, 'success', '执行器已获得任务 lease。');
  }, 'job-started', 180);
  scheduleJob(jobId);
  return jobById(jobId);
}

export async function cancelJob(jobId) {
  return transact((state) => {
    const job = state.jobs.find((item) => item.id === jobId);
    if (!job) throw new Error('摄取任务不存在');
    if (!['queued', 'running'].includes(job.status)) throw new Error('当前状态不能取消');
    job.status = 'canceled'; job.stage = '已取消'; job.updatedAt = new Date().toISOString();
    job.logs.push(`${new Date().toLocaleTimeString('zh-CN', { hour12: false })} 操作者取消任务`);
    addAudit('JOB_CANCELED', job.runId, 'success', '停止剩余操作，已完成 checkpoint 保留。');
  }, 'job-canceled');
}

export async function retryJob(jobId) {
  const job = jobById(jobId);
  if (!job || !['failed', 'canceled'].includes(job.status)) throw new Error('当前任务不能重试');
  if (job.reviewRequired && job.reviewStatus !== 'completed') throw new Error('请先完成并提交人工复核，再从 checkpoint 重试');
  return startJob(jobId);
}

export async function saveReviewDecision(jobId, itemId, payload) {
  const allowed = ['normalize', 'exclude', 'escalate'];
  if (!allowed.includes(payload.decision)) throw new Error('请选择一个处理决定');
  const correctedText = String(payload.correctedText || '').trim();
  const note = String(payload.note || '').trim();
  if (payload.decision === 'normalize' && correctedText.length < 20) throw new Error('修正后的知识文本至少需要 20 个字');
  if (payload.decision !== 'normalize' && note.length < 6) throw new Error('排除或升级时，请填写至少 6 个字的原因');

  return transact((state) => {
    const job = state.jobs.find((entry) => entry.id === jobId);
    const batch = state.reviewBatches.find((entry) => entry.jobId === jobId);
    const item = batch?.items.find((entry) => entry.id === itemId);
    if (!job || !batch || !item) throw new Error('复核任务或异常项不存在');
    if (batch.status === 'completed') throw new Error('该批次已提交，不能再修改');
    Object.assign(item, {
      decision: payload.decision,
      correctedText: payload.decision === 'normalize' ? correctedText : '',
      note,
      status: 'resolved',
      reviewer: state.user.name,
      reviewedAt: new Date().toISOString(),
    });
    const resolved = batch.items.filter((entry) => entry.status === 'resolved').length;
    batch.status = resolved === batch.items.length ? 'ready_to_submit' : 'in_progress';
    job.reviewStatus = batch.status;
    job.updatedAt = new Date().toISOString();
    addAudit('REVIEW_ITEM_RESOLVED', `${job.runId} / 异常 ${item.order}`, 'success', `${item.pageTitle} 已选择 ${payload.decision} 处理。`);
  }, 'review-item-resolved', 220);
}

export async function submitManualReview(jobId) {
  const batch = reviewByJobId(jobId);
  if (!batch) throw new Error('人工复核批次不存在');
  if (batch.items.some((item) => item.status !== 'resolved')) throw new Error('仍有异常项未形成处理决定');

  return transact((state) => {
    const job = state.jobs.find((entry) => entry.id === jobId);
    const current = state.reviewBatches.find((entry) => entry.jobId === jobId);
    if (!job || !current) throw new Error('复核任务不存在');
    if (current.status === 'completed') throw new Error('该批次已经提交');
    current.status = 'completed';
    current.submittedAt = new Date().toISOString();
    current.submittedBy = state.user.name;
    job.reviewStatus = 'completed';
    job.stage = '人工复核完成，等待重试';
    job.error = null;
    job.updatedAt = new Date().toISOString();
    job.logs.push(`${new Date().toLocaleTimeString('zh-CN', { hour12: false })} 人工复核完成，${current.items.length}/${current.items.length} 项已形成处理决定`);
    addAudit('MANUAL_REVIEW_COMPLETED', job.runId, 'success', `${current.items.length} 个复杂表格已完成复核，允许从 checkpoint 恢复。`);
    addNotification('success', '人工复核已完成', `${job.runId} 已解除内容阻断，可以从 checkpoint 重试。`, `/jobs?job=${job.id}`);
  }, 'manual-review-completed', 320);
}

export async function runEvaluation(versionId, datasetId) {
  const version = versionById(versionId);
  const dataset = getState().datasets.find((item) => item.id === datasetId);
  if (!version || !dataset) throw new Error('版本或评测集不存在');
  let evaluation;
  await transact((state) => {
    evaluation = {
      id: nextId('eval'), versionId, version: version.collection, datasetId, dataset: dataset.name,
      status: 'running', score: null, recall: null, citation: null, grounded: null, aclLeakage: null,
      createdAt: new Date().toISOString(), operator: state.user.name,
    };
    state.evaluations.unshift(evaluation);
    version.qualityGate = 'running';
    addAudit('EVALUATION_STARTED', version.collection, 'success', `使用 ${dataset.name} 执行质量评测。`);
  }, 'evaluation-started');
  window.setTimeout(() => {
    update((state) => {
      const current = state.evaluations.find((item) => item.id === evaluation.id);
      const target = state.versions.find((item) => item.id === versionId);
      if (!current || !target) return;
      Object.assign(current, { status: 'passed', score: 95.1, recall: 95.8, citation: 98.1, grounded: 94.4, aclLeakage: 0 });
      target.qualityGate = 'passed'; target.qualityScore = 95.1;
      addAudit('QUALITY_GATE_APPROVED', target.collection, 'success', 'Recall、引用、忠实度与 ACL 泄漏指标全部通过。');
      addNotification('success', '质量门禁已通过', `${target.collection} 可以进入版本发布。`, '/versions');
    }, 'evaluation-completed');
  }, 1500);
  return evaluation;
}

export async function addDataset(payload) {
  return transact((state) => {
    state.datasets.unshift({ id: nextId('ds'), name: payload.name, version: payload.version, cases: Number(payload.cases), owner: state.user.name, updatedAt: new Date().toISOString() });
    addAudit('EVALUATION_DATASET_CREATED', payload.name, 'success', `新增 ${payload.cases} 条评测样本。`);
  }, 'dataset-created');
}

export async function toggleOnlineExperiment() {
  return transact((state) => {
    const experiment = state.onlineEffect.experiment;
    experiment.status = experiment.status === 'running' ? 'paused' : 'running';
    const running = experiment.status === 'running';
    addAudit(running ? 'ONLINE_EXPERIMENT_RESUMED' : 'ONLINE_EXPERIMENT_PAUSED', experiment.id, 'success', `${experiment.name}${running ? '恢复分流' : '已停止新流量进入'}。`);
    addNotification(running ? 'success' : 'warning', running ? 'A/B 实验已恢复' : 'A/B 实验已暂停', experiment.name, '/quality/online');
  }, 'online-experiment-toggled', 320);
}

export async function saveOnlineAlertRule(payload) {
  return transact((state) => {
    const rules = state.onlineEffect.alertRules;
    const existing = payload.id ? rules.find((item) => item.id === payload.id) : null;
    const rule = {
      id: existing?.id || nextId('rule'),
      name: payload.name,
      metric: payload.metric,
      operator: payload.operator,
      threshold: Number(payload.threshold),
      window: payload.window,
      minSamples: Number(payload.minSamples),
      consecutive: Number(payload.consecutive),
      action: payload.action,
      rollbackVersion: payload.action === 'rollback' ? payload.rollbackVersion : null,
      owner: payload.owner,
      channel: payload.channel,
      enabled: existing?.enabled ?? true,
      status: 'healthy',
      lastCheckedAt: new Date().toISOString(),
    };
    if (existing) Object.assign(existing, rule);
    else rules.unshift(rule);
    addAudit(existing ? 'ONLINE_ALERT_RULE_UPDATED' : 'ONLINE_ALERT_RULE_CREATED', rule.name, 'success', `指标 ${rule.metric} ${rule.operator} ${rule.threshold}，${rule.consecutive} 个连续窗口后执行 ${rule.action}。`);
  }, payload.id ? 'online-alert-rule-updated' : 'online-alert-rule-created', 320);
}

export async function toggleOnlineAlertRule(ruleId) {
  return transact((state) => {
    const rule = state.onlineEffect.alertRules.find((item) => item.id === ruleId);
    if (!rule) throw new Error('告警规则不存在');
    rule.enabled = !rule.enabled;
    rule.status = rule.enabled ? 'healthy' : 'disabled';
    addAudit(rule.enabled ? 'ONLINE_ALERT_RULE_ENABLED' : 'ONLINE_ALERT_RULE_DISABLED', rule.name, 'success', rule.enabled ? '恢复指标观测。' : '停止该规则的指标判定。');
  }, 'online-alert-rule-toggled');
}

export async function simulateOnlineAlertRule(ruleId) {
  return transact((state) => {
    const rule = state.onlineEffect.alertRules.find((item) => item.id === ruleId);
    if (!rule) throw new Error('告警规则不存在');
    if (!rule.enabled) throw new Error('请先启用规则再执行演练');
    rule.status = 'tested';
    rule.lastCheckedAt = new Date().toISOString();
    rule.lastSimulation = `演练通过：样本量、连续窗口与${rule.action === 'rollback' ? '回滚目标' : '通知动作'}校验成功`;
    addAudit('ONLINE_ALERT_RULE_DRY_RUN', rule.name, 'success', `演练模式未切换线上别名；实际触发将执行 ${rule.action}。`);
    addNotification('success', '告警规则演练通过', `${rule.name}未对线上版本执行真实操作。`, '/quality/online');
  }, 'online-alert-rule-tested', 420);
}

export async function createOnlineFailureTicket(failureId) {
  return transact((state) => {
    const failure = state.onlineEffect.failures.find((item) => item.id === failureId);
    if (!failure) throw new Error('失败案例不存在');
    if (failure.ticketId) throw new Error('该案例已创建改进任务');
    failure.ticketId = nextId('improve');
    failure.ticketOwner = state.user.name;
    failure.ticketStatus = 'pending';
    addAudit('ONLINE_FAILURE_TICKET_CREATED', failure.id, 'success', `为 ${failure.reason} 创建改进任务 ${failure.ticketId}。`);
  }, 'online-failure-ticket-created', 320);
}

export async function activateVersion(versionId) {
  const candidate = versionById(versionId);
  if (!candidate) throw new Error('目标版本不存在');
  if (candidate.qualityGate !== 'passed') throw new Error('质量门禁未通过，禁止发布');
  return transact((state) => {
    const current = state.versions.find((item) => item.status === 'active');
    const target = state.versions.find((item) => item.id === versionId);
    if (current?.id === target.id) throw new Error('目标版本已经在线');
    if (current) { current.status = 'ready'; current.alias = null; }
    target.status = 'active'; target.alias = state.settings.milvus.activeAlias;
    target.activatedAt = new Date().toISOString();
    addAudit('ALIAS_ACTIVATED', `${target.alias} → ${target.collection}`, 'success', `通过版本门禁并保留 ${current?.collection || '无'} 作为回滚目标。`);
    addNotification('success', '知识库版本发布成功', `${target.alias} 已指向 ${target.collection}。`, '/versions');
  }, 'version-activated', 520);
}

export async function rollbackVersion(versionId) {
  const target = versionById(versionId);
  if (!target) throw new Error('回滚目标不存在');
  if (!['ready', 'archived'].includes(target.status)) throw new Error('该版本不能作为回滚目标');
  return transact((state) => {
    const current = state.versions.find((item) => item.status === 'active');
    const rollbackTarget = state.versions.find((item) => item.id === versionId);
    if (current) { current.status = 'ready'; current.alias = null; }
    rollbackTarget.status = 'active'; rollbackTarget.alias = state.settings.milvus.activeAlias;
    rollbackTarget.activatedAt = new Date().toISOString();
    addAudit('ALIAS_ROLLED_BACK', `${rollbackTarget.alias} → ${rollbackTarget.collection}`, 'success', `从 ${current?.collection || '未知版本'} 回滚，完成陈旧状态校验。`);
    addNotification('warning', '知识库版本已回滚', `线上已恢复至 ${rollbackTarget.collection}。`, '/versions');
  }, 'version-rolled-back', 620);
}

export async function saveSettings(section, values) {
  return transact((state) => {
    if (!(section in state.settings)) throw new Error('配置分组不存在');
    state.settings[section] = { ...state.settings[section], ...values };
    addAudit('SETTINGS_UPDATED', section, 'success', '环境配置已更新，敏感字段仅保存凭据引用。');
  }, 'settings-updated');
}

export async function testConnection(section) {
  await transact((state) => {
    if (!state.settings[section]) throw new Error('连接器不存在');
    state.settings[section].status = 'checking';
  }, 'connection-checking', 80);
  return transact((state) => {
    state.settings[section].status = 'healthy';
    state.settings[section].lastCheckedAt = new Date().toISOString();
    addAudit('CONNECTION_TESTED', section, 'success', '连接、认证与最小权限检查通过。');
  }, 'connection-checked', 700);
}

export async function rotateCredential(section) {
  return transact((state) => {
    const target = state.settings[section];
    if (!target) throw new Error('连接器不存在');
    target.lastRotatedAt = new Date().toISOString();
    addAudit('CREDENTIAL_ROTATED', section, 'success', '凭据引用已轮换，页面未接触明文密钥。');
    addNotification('success', '凭据轮换完成', `${section} 已使用新的 Vault 引用。`, '/settings');
  }, 'credential-rotated', 620);
}

export async function switchWorkspace(workspaceId) {
  return transact((state) => {
    const workspace = state.workspaces.find((item) => item.id === workspaceId);
    if (!workspace) throw new Error('工作空间不存在');
    state.activeWorkspaceId = workspaceId;
    addAudit('WORKSPACE_SWITCHED', workspace.name, 'success', `以 ${workspace.role} 身份进入工作空间。`);
  }, 'workspace-switched', 180);
}

export async function markAllNotificationsRead() {
  return transact((state) => { state.notifications.forEach((item) => { item.read = true; }); }, 'notifications-read', 80);
}

export async function markNotificationRead(notificationId) {
  return transact((state) => {
    const notice = state.notifications.find((item) => item.id === notificationId);
    if (notice) notice.read = true;
  }, 'notification-read', 60);
}
