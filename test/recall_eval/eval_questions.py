"""
召回率评测集：24个问题，覆盖12篇CRM测试文档，每篇2题。
ground_truth_source: 该问题对应的标准答案来源文档（文件名，不含路径）。
用于计算 Recall@k / Precision@k —— 检索结果里包含 ground_truth_source 视为命中。
"""

EVAL_QUESTIONS = [
    # 01_sales_sop_lead_to_deal.md —— 销售SOP：线索到成单
    {"id": 1, "question": "线索在CRM系统里超过多久没有跟进会被自动退回公共池？", "ground_truth_source": "01_sales_sop_lead_to_deal.md"},
    {"id": 2, "question": "报价折扣力度在什么范围需要销售总监二级审批？", "ground_truth_source": "01_sales_sop_lead_to_deal.md"},

    # 02_objection_price.md —— 价格类异议
    {"id": 3, "question": "客户觉得价格太贵，标准应对话术分为哪几个步骤？", "ground_truth_source": "02_objection_price.md"},
    {"id": 4, "question": "客户说预算不足，应该怎么判断是真的预算有限还是礼貌性拒绝？", "ground_truth_source": "02_objection_price.md"},

    # 03_objection_feature_service.md —— 功能与服务类异议
    {"id": 5, "question": "客户担心数据迁移风险，标准的迁移周期大概是多久？", "ground_truth_source": "03_objection_feature_service.md"},
    {"id": 6, "question": "客户抱怨售后服务响应慢，应该怎么处理这类异议？", "ground_truth_source": "03_objection_feature_service.md"},

    # 04_feature_lead_opportunity.md —— 线索与商机管理模块
    {"id": 7, "question": "商机从初步接触推进到需求确认阶段，需要满足什么条件？", "ground_truth_source": "04_feature_lead_opportunity.md"},
    {"id": 8, "question": "商机标记为已流失时，系统要求填写什么字段？", "ground_truth_source": "04_feature_lead_opportunity.md"},

    # 05_feature_customer_success.md —— 客户成功与续费管理模块
    {"id": 9, "question": "客户健康度评分是由哪几个维度组成的，各自权重是多少？", "ground_truth_source": "05_feature_customer_success.md"},
    {"id": 10, "question": "合同到期前系统会在哪些时间节点自动触发续费提醒？", "ground_truth_source": "05_feature_customer_success.md"},

    # 06_feature_report_permission.md —— 报表分析与数据权限模块
    {"id": 11, "question": "CRM系统的数据权限范围从小到大分为哪几个层级？", "ground_truth_source": "06_feature_report_permission.md"},
    {"id": 12, "question": "报表数据和实际业务不符，可能是哪些原因导致的？", "ground_truth_source": "06_feature_report_permission.md"},

    # 07_troubleshoot_login_permission.md —— 登录与账号权限问题排查
    {"id": 13, "question": "账号连续输错密码会被锁定多久？", "ground_truth_source": "07_troubleshoot_login_permission.md"},
    {"id": 14, "question": "单点登录SSO集成出现认证成功但身份映射错误，应该怎么处理？", "ground_truth_source": "07_troubleshoot_login_permission.md"},

    # 08_troubleshoot_sync_import_export.md —— 数据同步与导入导出问题
    {"id": 15, "question": "Excel批量导入失败，最常见的原因有哪些？", "ground_truth_source": "08_troubleshoot_sync_import_export.md"},
    {"id": 16, "question": "数据导出的下载链接有效期是多久？", "ground_truth_source": "08_troubleshoot_sync_import_export.md"},

    # 09_troubleshoot_mobile_performance.md —— 移动端与系统性能问题
    {"id": 17, "question": "移动端App拍照上传附件失败，可能是什么原因？", "ground_truth_source": "09_troubleshoot_mobile_performance.md"},
    {"id": 18, "question": "系统整体响应速度慢，排查思路应该按什么顺序进行？", "ground_truth_source": "09_troubleshoot_mobile_performance.md"},

    # 10_objection_decision_contract.md —— 决策链与合同条款类异议
    {"id": 19, "question": "客户说需要跟领导汇报再决定，销售应该怎么应对？", "ground_truth_source": "10_objection_decision_contract.md"},
    {"id": 20, "question": "客户想先试用一段时间再决定，试用方案应该怎么设计？", "ground_truth_source": "10_objection_decision_contract.md"},

    # 11_sales_sop_team_kpi.md —— 团队协作与业绩考核
    {"id": 21, "question": "销售季度成交总金额是按照什么日期归属考核周期的？", "ground_truth_source": "11_sales_sop_team_kpi.md"},
    {"id": 22, "question": "销售话术库的内容更新需要经过什么审核流程？", "ground_truth_source": "11_sales_sop_team_kpi.md"},

    # 12_feature_integration_security.md —— 系统集成与安全合规模块
    {"id": 23, "question": "CRM系统的API调用频率限制是多少？", "ground_truth_source": "12_feature_integration_security.md"},
    {"id": 24, "question": "系统对外承诺的服务可用性指标是多少？", "ground_truth_source": "12_feature_integration_security.md"},
]

if __name__ == "__main__":
    print(f"共 {len(EVAL_QUESTIONS)} 个评测问题，覆盖 {len(set(q['ground_truth_source'] for q in EVAL_QUESTIONS))} 篇文档")
