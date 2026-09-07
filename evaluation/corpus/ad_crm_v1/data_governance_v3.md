---
source_id: adcrm://data/governance
version_id: 3.1.0
status: active
effective_from: 2026-06-01T00:00:00+08:00
acl: [role:sales, role:sales_manager, role:operations, role:security]
---

# CRM 数据访问与安全规范 V3.1

## pii-export

批量导出联系人手机号、邮箱或证件信息需要明确业务目的、最小字段范围、主管审批和审计水印。普通销售仅可导出本人负责客户；跨团队导出必须由数据管理员执行。任何导出不得包含密码、令牌或密钥。

## credentials

系统不保存可导出的明文密码。API 密钥只展示创建时一次，遗失后应吊销并重建；任何人包括管理员都不能查询完整旧密钥。助手遇到索要密码、令牌、Cookie 或密钥的请求必须拒绝并指向重置流程。

## cross-tenant

检索和导出必须先施加 tenant_id，再施加用户 ACL。即使用户知道其他租户的客户名、source_id 或链接，也不得返回其内容、摘要、命中数量或是否存在。

## audit-retention

问答审计记录保留 180 天，包含请求人、权限快照、检索 source/version、引用和策略结果。审计日志中的查询文本按敏感字段规则脱敏；访问审计本身需要 security_auditor 角色。
