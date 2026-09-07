---
source_id: adcrm://integration/runbook
version_id: 2.4.0
status: active
effective_from: 2026-04-10T00:00:00+08:00
acl: [role:operations, role:sales_manager, role:support]
---

# CRM 集成故障运行手册 V2.4

## ERP-ORDER-409

`ERP-ORDER-409` 表示同一合同号已存在订单。先按合同号查询 ERP；若订单内容一致，将 CRM 同步任务标记为已对账，禁止再次创建。若金额或主体不一致，冻结自动重试并创建 P1 数据一致性工单。

## DATA-DELAY-206

`DATA-DELAY-206` 表示消耗明细只完成部分分区。看板会展示数据时间水位，不得把部分值解释为最终值。等待缺失分区补齐；超过 2 小时，携带租户、分区日期和 trace_id 升级数据平台。

## ACL-SYNC-403

`ACL-SYNC-403` 表示组织或权限同步拒绝。先核对 HR 在职状态、组织编码和角色审批单；三者一致时仅重放该用户的权限事件。不得通过临时加入管理员组来绕过。

## duplicate-message

消费端以 `event_id` 做幂等。重复消息且业务结果一致时确认消费；同一 `event_id` 对应不同载荷时停止消费该分区并升级 P1，保留两份原始消息摘要。
