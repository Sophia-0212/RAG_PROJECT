---
source_id: adcrm://glossary/fields
version_id: 1.2.0
status: active
effective_from: 2026-01-15T00:00:00+08:00
acl: [role:sales, role:sales_manager, role:operations, role:support, role:finance]
---

# CRM 字段与术语字典 V1.2

## field-mapping

`advertiser_id` 是广告投放账户 ID，`account_id` 是 CRM 客户主账号 ID，二者不可互换。`contract_subject_id` 是合同签约主体 ID，一个客户主账号可以关联多个合同主体。

## acronyms

`MQL` 是营销确认线索，`SQL` 是销售确认线索；`Commit` 是满足严格条件的当月承诺预测，不能解释为已经签约；`NCA` 是新客户开户申请，不是新增客户账号本身。

## status-codes

`WON_PENDING_SYNC` 表示商机已赢单但订单尚未同步完成；`ACTIVE_RISK_HOLD` 表示账号存在可投放资格但被风险暂停；`CLOSED_NURTURE` 表示本轮商机关闭并转入培育任务。

## amount-fields

`gross_spend` 是扣除退款前消耗，`net_confirmed_spend` 是扣除退款、赠款和测试金后的已确认净消耗。返货和经营分级使用后者，实时看板的未确认消耗不能直接用于结算。
