# Task Plan: Online Effect Dashboard

## Goal
在现有企业知识运营台中设计并实现第二个质量视图，用于跟踪上线后的业务效果、A/B 实验、失败案例和告警/回滚规则。

## Current Phase
Phase 6

## Next Step
已完成；用户可在 `http://localhost:4174/#/quality/online` 体验。

## Phases

### Phase 1: Discovery and Information Architecture
- [x] 审计现有前端模块与质量评测页
- [x] 确定第二页的入口、信息层级和业务口径
- [x] 定义交互、状态与验收标准
- **Status:** complete

### Phase 2: Modular Implementation
- [x] 添加路由与页面模块
- [x] 实现趋势、维度下钻、A/B 对比、失败明细与规则配置
- [x] 复用现有通用组件并补充必要组件
- **Status:** complete

### Phase 3: Interaction and Visual QA
- [x] 验证所有可点击控件及状态恢复
- [x] 桌面端与移动端语义、几何布局与溢出检查
- [x] 修复布局、文案和数据口径问题
- **Status:** complete

### Phase 4: Delivery
- [x] 汇总文件变更和验收结果
- [x] 说明模拟数据与真实生产数据链路的边界
- **Status:** complete

### Phase 5: Observable Metric Model Correction
- [x] 用自助解决、未解决、重复提问、负反馈、任务完成、答案采纳替换原客服式口径
- [x] 同步趋势、维度、A/B、失败案例和告警规则的数据结构与文案
- [x] 明确六项指标分母不同，并标注如流后续求助不可直接观测
- **Status:** complete

### Phase 6: Regression QA
- [x] 执行语法、静态口径和 HTTP 检查
- [x] 验证桌面端、移动端及主要点击交互
- [x] 验证刷新恢复默认状态
- **Status:** complete

## Decisions Made

| Decision | Rationale |
|---|---|
| 将页面定位为“上线效果”而非简单 Prometheus 监控 | 用户要求的采纳率、转人工率、抽检正确率属于业务分析和发布治理 |
| 保持静态 SPA 和内存 Mock API 架构 | 与现有 `upload_mock` 一致，刷新即恢复默认状态 |
| 新增 `/quality/online` 与“上线效果”导航 | 与离线质量评测区分，同时保持运营人员可直接访问 |
| 所有指标必须可下钻 | 企业管理需要从百分比追溯到分子、分母、会话和失败原因 |
| 回滚规则包含最小样本和连续观测窗口 | 防止小样本波动触发错误自动回滚 |
| 使用业务背景中的 4,600 次日问答和上线前后结果 | 页面必须与项目规模和已有故事一致 |
| 将“答案采纳率”主口径命名为“线上有帮助率” | 对齐背景文档 68.7% 到 76.5% 的已定指标，再在下钻中展示直接/编辑后采纳 |
| 将线上效果改为六项系统内可观测指标 | 内部 CRM 问答没有客服转人工链路，员工转去如流求助不能由本系统直接判断 |

## Errors Encountered

| Error | Resolution |
|---|---|
| 更新计划文件时补丁字符串包含不完整 Unicode escape | 修正该字符串并重新应用补丁 |
| ego-browser 首次打开 URL 时复用了扩展新标签页 | 显式创建 localhost 标签并切换，语义快照成功 |
| ego-browser 内置截图与 CDP `Page.captureScreenshot` 均超时 | 保留布局几何与溢出检查结果，继续使用语义快照和 DOM 尺寸完成交互验收 |
| 移动侧边栏隐藏时，ego-browser 坐标点击不会触发隐藏链接 | 通过 DOM 事件验证路由实现，并单独验证移动菜单可正常展开 |
