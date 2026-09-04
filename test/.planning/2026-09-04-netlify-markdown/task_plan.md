# Task Plan: Netlify 左侧步骤 Markdown 拆分

## Goal
将指定网站编号 0 至 15 的每个顶层条目分别保存为独立 Markdown 文档，并在同一文件内保留其全部子条目，不修改内容。

## Next Step
向用户交付修正后的 16 份顶层 Markdown 文档。

## Current Phase
Complete

## Phases

### Phase 1: Requirements & Discovery
- [x] Understand user intent
- [x] Identify constraints
- [x] Identify every left-side step and its content container
- **Status:** complete

### Phase 2: Content Extraction
- [x] Extract each step's exact source content
- [x] Record step order, titles, and source mapping
- **Status:** complete

### Phase 3: Markdown Split
- [x] Create one Markdown file per left-side step
- [x] Preserve source wording, code, and ordering
- **Status:** complete

### Phase 4: Testing & Verification
- [x] Verify file count equals step count
- [x] Verify filenames, ordering, and content fidelity
- **Status:** complete

### Phase 5: Delivery
- [x] Review outputs
- [x] Report files and verification to user
- **Status:** complete

### Phase 6: Top-Level Mapping Correction
- [x] Map H2 entries 0 through 15 to their following H3 child files
- [x] Exclude the H1 project-title section from output
- **Status:** complete

### Phase 7: Regenerate Top-Level Markdown
- [x] Generate 16 merged Markdown files in a temporary directory
- [x] Replace the previous 52-file split only after validation
- **Status:** complete

### Phase 8: Final Verification and Delivery
- [x] Verify 16 files, child inclusion, ordering, and content preservation
- [x] Report corrected output to user
- **Status:** complete

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| 将每个左侧步骤输出为一个独立 `.md` 文件 | 严格对应用户要求的结构拆分 |
| 不对源内容做润色、摘要或重写 | 用户明确要求只拆分、不修改内容 |
| 包含左侧全部 52 个可点击目录项 | “每一个步骤”按页面实际导航粒度解释，包含总标题、顶层步骤和子步骤 |
| 父步骤只保留自身直属内容，嵌套子步骤单独保存 | 避免拆分后正文重复，同时保持原导航层级边界 |
| 包含总标题对应的第一份文档 | 总标题是 `Dossier index` 同一目录列表中的首个链接 |
| 修正为只输出编号 0 至 15 的 16 个 H2 顶层条目 | 用户明确说明顶层条目为文件边界，H3 子条目须合并进父文件 |
| 不输出 H1 项目总标题文件 | 用户明确要求顶层步骤从 0 到 15，总标题不是步骤文件 |
| 替换时先将旧文件移动到临时备份 | 最终核验前保留可回滚路径，核验通过后再删除备份 |

## Errors Encountered
| Error | Resolution |
|-------|------------|
| 初始化脚本报告 `C.UTF-8` locale 不可用 | 不影响计划文件创建，继续执行 |
| ego-browser 批量写入脚本因 CommonJS `require` 与顶层 `await` 冲突而报语法错误 | 改用动态 `import('node:...')`，不重复原执行方式 |
| 动态 `import` 版本仍被 ego-browser 运行时按 CommonJS 编译 | 显式以 async IIFE 包裹完整脚本，消除顶层 `await` |
| async IIFE 版本出现 `missing ) after argument list` | 定位为内层 Markdown 反引号提前结束外层模板；改用字符码构造并先只读预览 |
| 首次语义核验报告 16 项差异 | 核验器误把编号标题和代码块竖线当作列表/表格；修正后 52/52 全部匹配 |
