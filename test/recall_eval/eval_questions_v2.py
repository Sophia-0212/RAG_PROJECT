"""
召回率评测集 v2：40题，覆盖12篇CRM测试文档，按文章方法论标注四种难度/类型：
  - factual: 简单事实题，答案在单个chunk里
  - multi_hop: 多跳推理题，需要综合同一文档内多个段落/多篇文档才能完整回答
  - negation: 否定性查询，容易召回"看起来相关但实际答非所问"的干扰chunk
  - colloquial: 口语化查询，表述跟文档原文用词差异大

每题标注：
  - ground_truth_source: 标准答案所在文档（可能是1篇，多跳题可能是2篇）
  - ground_truth_snippet: 标准答案在文档中的关键原文片段（用于chunk级证据匹配，比文档级judge更精确）
  - reference_answer: 人工撰写的参考答案（生成层评估用）
  - question_type: factual / multi_hop / negation / colloquial
"""

EVAL_QUESTIONS = [
    # ========== 01_sales_sop_lead_to_deal.md ==========
    {"id": 1, "question": "线索在CRM系统里超过多久没有跟进会被自动退回公共池？",
     "ground_truth_source": ["04_feature_lead_opportunity.md"],
     "ground_truth_snippet": "个人池中的线索如果超过系统设定的跟进时效（默认72小时无任何跟进记录更新）会被自动退回公共池",
     "reference_answer": "个人池中的线索如果超过系统设定的跟进时效（默认72小时无任何跟进记录更新）会被自动退回公共池，退回前系统会提前24小时给持有销售发送提醒通知。",
     "question_type": "factual"},
    {"id": 2, "question": "报价折扣力度在什么范围需要销售总监二级审批？",
     "ground_truth_source": ["01_sales_sop_lead_to_deal.md"],
     "ground_truth_snippet": "折扣在7折到9折之间需要销售总监二级审批",
     "reference_answer": "折扣在7折到9折之间（优惠幅度10%到30%之间）需要销售总监二级审批。",
     "question_type": "factual"},
    {"id": 3, "question": "客户签合同后，销售大概要跟进多久才能确认这个客户不会轻易流失？",
     "ground_truth_source": ["01_sales_sop_lead_to_deal.md"],
     "ground_truth_snippet": "任务周期覆盖签约后的前90天，这个阶段是流失率最高的窗口期",
     "reference_answer": "系统设置的客户维护任务周期覆盖签约后前90天，这是流失率最高的窗口期，维护节奏包括第3天首次回访、第7天核心流程确认、第30天深度调研、第60天续费预热、第90天正式续费谈判。",
     "question_type": "multi_hop"},

    # ========== 02_objection_price.md ==========
    {"id": 4, "question": "客户觉得价格太贵，标准应对话术分为哪几个步骤？",
     "ground_truth_source": ["02_objection_price.md"],
     "ground_truth_snippet": "共情—价值重申—方案调整—收尾确认",
     "reference_answer": "分为共情、价值重申、方案调整、收尾确认四个步骤。",
     "question_type": "factual"},
    {"id": 5, "question": "客户说预算不足，应该怎么判断是真的预算有限还是礼貌性拒绝？",
     "ground_truth_source": ["02_objection_price.md"],
     "ground_truth_snippet": "判断的关键线索是客户是否主动提供了具体的预算数字或者预算审批的时间节点",
     "reference_answer": "关键判断线索是客户是否主动提供具体预算数字或审批时间节点，能说出具体数字说明是真预算约束，只是笼统说预算不够却不愿透露细节更可能是意向不足或观望。",
     "question_type": "factual"},
    {"id": 6, "question": "客户说贵，但是没有像价格类异议手册里说的先讨论价值就直接给折扣，这样做法对不对，为什么？",
     "ground_truth_source": ["02_objection_price.md"],
     "ground_truth_snippet": "把降价作为最后的谈判手段，而不是应对异议的第一反应",
     "reference_answer": "不对。应该先做好价值论证工作，把降价作为最后的谈判手段而非第一反应，直接降价会强化客户'只要提异议就能拿到更低价格'的预期，增加后续每次谈判的成本。",
     "question_type": "negation"},

    # ========== 03_objection_feature_service.md ==========
    {"id": 7, "question": "客户担心数据迁移风险，标准的迁移周期大概是多久？",
     "ground_truth_source": ["03_objection_feature_service.md"],
     "ground_truth_snippet": "1万条客户记录以内的迁移，标准周期是3到5个工作日",
     "reference_answer": "1万条以内数据量标准周期3到5个工作日，1万到10万条是7到10个工作日，超过10万条需要单独评估制定专项方案。",
     "question_type": "factual"},
    {"id": 8, "question": "客户抱怨售后服务响应慢，应该怎么处理这类异议？",
     "ground_truth_source": ["03_objection_feature_service.md"],
     "ground_truth_snippet": "诚恳承认并具体了解客户遇到的问题细节",
     "reference_answer": "第一步诚恳承认并具体了解问题细节，第二步说明售后服务体系的具体改进措施（如SLA时间承诺），第三步主动提供具体可执行的补偿或保障措施（如专属客户成功经理）。",
     "question_type": "factual"},
    {"id": 9, "question": "客户说友商功能比我们全，遇到这种情况销售不应该怎么回应？",
     "ground_truth_source": ["03_objection_feature_service.md"],
     "ground_truth_snippet": "不应该含糊其辞或者夸大宣传声称我们也有类似功能",
     "reference_answer": "不应该含糊其辞或夸大宣传声称'我们也有类似功能'，这种不诚实的回应一旦被发现名不副实会严重损害客户信任，也可能产生合同履约纠纷。",
     "question_type": "negation"},

    # ========== 04_feature_lead_opportunity.md ==========
    {"id": 10, "question": "商机从初步接触推进到需求确认阶段，需要满足什么条件？",
     "ground_truth_source": ["04_feature_lead_opportunity.md"],
     "ground_truth_snippet": "进入条件要求销售至少完成一次有效的客户沟通记录（电话时长超过3分钟或者面谈记录）",
     "reference_answer": "需要至少完成一次有效客户沟通记录，电话时长超过3分钟或有面谈记录，系统会自动统计通话时长做强制校验。",
     "question_type": "factual"},
    {"id": 11, "question": "商机标记为已流失时，系统要求填写什么字段？",
     "ground_truth_source": ["04_feature_lead_opportunity.md"],
     "ground_truth_snippet": "系统要求销售必须填写流失原因字段才能完成状态变更",
     "reference_answer": "必须填写'流失原因'字段，是结构化下拉选项，包括价格因素、竞品选择、预算取消、决策人变动、需求消失、长期无响应等。",
     "question_type": "factual"},
    {"id": 12, "question": "一个大客户同时要销售、技术顾问、法务一起跟，这种情况下商机归属和权限应该怎么分配？",
     "ground_truth_source": ["04_feature_lead_opportunity.md"],
     "ground_truth_snippet": "支持设置主要负责人+协作成员的团队协作模式",
     "reference_answer": "系统支持'主要负责人+协作成员'团队协作模式，协作成员可查看详情并添加沟通记录，但只有主要负责人具备阶段推进、报价提交等关键操作权限，商机的商务决策权始终归主要负责人。",
     "question_type": "colloquial"},

    # ========== 05_feature_customer_success.md ==========
    {"id": 13, "question": "客户健康度评分是由哪几个维度组成的，各自权重是多少？",
     "ground_truth_source": ["05_feature_customer_success.md"],
     "ground_truth_snippet": "登录活跃度权重占30%，功能使用深度占35%，支持工单情况占20%，续费历史占15%",
     "reference_answer": "四个维度：登录活跃度30%、核心功能使用深度35%、支持工单情况20%、续费历史记录15%。",
     "question_type": "factual"},
    {"id": 14, "question": "合同到期前系统会在哪些时间节点自动触发续费提醒？",
     "ground_truth_source": ["05_feature_customer_success.md"],
     "ground_truth_snippet": "到期前90天生成续费预热任务...到期前60天...到期前30天...到期前15天",
     "reference_answer": "到期前90天生成续费预热任务，60天升级提醒并通知销售负责人，30天标记续费高风险并通知部门主管，15天触发最高优先级预警推送给业务线负责人。",
     "question_type": "factual"},
    {"id": 15, "question": "客户健康度评分显示是黄色，但客户成功经理判断这个客户其实没有真正的流失风险，这种情况下该怎么处理？",
     "ground_truth_source": ["05_feature_customer_success.md"],
     "ground_truth_snippet": "有些客户可能因为业务淡季...但并不代表真正的流失风险，客户成功经理...应当结合与客户的实际沟通了解真实情况",
     "reference_answer": "健康度评分是辅助判断工具，不能完全替代主观了解，应结合与客户的实际沟通了解真实情况，而不是机械按分数执行统一挽留话术，避免过度介入引起客户困惑或反感。",
     "question_type": "negation"},

    # ========== 06_feature_report_permission.md ==========
    {"id": 16, "question": "CRM系统的数据权限范围从小到大分为哪几个层级？",
     "ground_truth_source": ["06_feature_report_permission.md"],
     "ground_truth_snippet": "仅本人负责的数据、本人及下属团队的数据...本部门全部数据、跨部门指定范围数据、全公司数据",
     "reference_answer": "从小到大依次是：仅本人负责的数据、本人及下属团队的数据、本部门全部数据、跨部门指定范围数据、全公司数据。",
     "question_type": "factual"},
    {"id": 17, "question": "报表数据和实际业务不符，可能是哪些原因导致的？",
     "ground_truth_source": ["06_feature_report_permission.md"],
     "ground_truth_snippet": "筛选条件设置不当...数据权限范围限制...数据统计口径的定义差异...数据同步延迟",
     "reference_answer": "四类常见原因：筛选条件设置不当（如时间范围理解偏差）、数据权限范围限制、统计口径定义差异、跨系统数据同步延迟。",
     "question_type": "factual"},
    {"id": 18, "question": "普通销售看不到别的同事的客户数据，这个不是bug对吧？",
     "ground_truth_source": ["06_feature_report_permission.md"],
     "ground_truth_snippet": "普通销售的默认数据范围是仅本人负责的数据，只能看到自己名下的线索、商机、客户",
     "reference_answer": "不是bug，是正常的数据权限设计。普通销售默认数据范围是'仅本人负责的数据'，这既保护销售个人客户资源、也符合数据最小化访问的安全原则。",
     "question_type": "negation"},

    # ========== 07_troubleshoot_login_permission.md ==========
    {"id": 19, "question": "账号连续输错密码会被锁定多久？",
     "ground_truth_source": ["07_troubleshoot_login_permission.md"],
     "ground_truth_snippet": "连续5次密码错误后自动锁定30分钟",
     "reference_answer": "连续5次密码错误后自动锁定30分钟。",
     "question_type": "factual"},
    {"id": 20, "question": "单点登录SSO集成出现认证成功但身份映射错误，应该怎么处理？",
     "ground_truth_source": ["07_troubleshoot_login_permission.md"],
     "ground_truth_snippet": "立即将涉事账号设置为临时禁用登录状态，防止数据泄露风险扩大",
     "reference_answer": "一旦发现要立即将涉事账号临时禁用防止风险扩大，常见原因是身份映射字段唯一性不足（如用姓氏缩写而非工号/邮箱），根本解决方案是要求IT方调整为具备唯一性的标识字段。",
     "question_type": "factual"},
    {"id": 21, "question": "我登录不上系统，是不是一定是系统故障？",
     "ground_truth_source": ["07_troubleshoot_login_permission.md"],
     "ground_truth_snippet": "很多登录失败案例最终排查出来的原因只是用户输错了密码或者账号处于锁定状态",
     "reference_answer": "不一定。绝大多数登录失败的常见原因是密码输错或账号锁定、账号状态异常（禁用/订阅到期/超出账号数上限）、网络浏览器环境问题，只有排除这些常见原因后才需要考虑系统级故障。",
     "question_type": "negation"},
    {"id": 22, "question": "部门主管换了个新领导，但是新领导说看不到团队里某个客户的信息，这是权限没配对吗？",
     "ground_truth_source": ["07_troubleshoot_login_permission.md"],
     "ground_truth_snippet": "如果一个客户记录的负责人在组织架构调整后已经变更了所属团队，但客户记录本身的团队归属字段没有同步更新",
     "reference_answer": "不一定是权限配置错误，可能是数据字段与组织架构变化不同步——客户记录的团队归属字段没有跟着组织架构调整同步更新，系统判断数据归属依据的是记录上的团队字段，需要手动核对更新该字段。",
     "question_type": "colloquial"},

    # ========== 08_troubleshoot_sync_import_export.md ==========
    {"id": 23, "question": "Excel批量导入失败，最常见的原因有哪些？",
     "ground_truth_source": ["08_troubleshoot_sync_import_export.md"],
     "ground_truth_snippet": "数据格式不符合模板要求...数据重复问题...编码格式问题",
     "reference_answer": "三类常见原因：数据格式不符合模板要求（必填字段空/类型不匹配/超长度）、数据重复（唯一性校验冲突）、编码格式问题（GBK与UTF-8冲突导致乱码）。",
     "question_type": "factual"},
    {"id": 24, "question": "数据导出的下载链接有效期是多久？",
     "ground_truth_source": ["08_troubleshoot_sync_import_export.md"],
     "ground_truth_snippet": "标准是生成后72小时内有效",
     "reference_answer": "标准是生成后72小时内有效，超过有效期需要重新提交导出请求生成新链接。",
     "question_type": "factual"},
    {"id": 25, "question": "客户导入的数据里有一堆重复记录被系统跳过了，是不是系统坏了？",
     "ground_truth_source": ["08_troubleshoot_sync_import_export.md"],
     "ground_truth_snippet": "系统在导入时会根据设定的唯一性判断规则...检测到重复时的默认处理策略是跳过导入",
     "reference_answer": "不是系统故障，是正常的默认策略——系统检测到重复记录（按手机号或企业名称+联系人组合判断）会默认跳过导入，避免同一客户被重复创建，如果确实需要更新可以切换为更新模式。",
     "question_type": "negation"},

    # ========== 09_troubleshoot_mobile_performance.md ==========
    {"id": 26, "question": "移动端App拍照上传附件失败，可能是什么原因？",
     "ground_truth_source": ["09_troubleshoot_mobile_performance.md"],
     "ground_truth_snippet": "图片文件过大超出单次上传大小限制...网络环境不稳定...设备存储空间不足",
     "reference_answer": "常见原因：图片超过单张10MB上传限制、网络环境不稳定导致上传中断（外勤场景常见）、设备存储空间不足无法生成临时缓存文件。",
     "question_type": "factual"},
    {"id": 27, "question": "系统整体响应速度慢，排查思路应该按什么顺序进行？",
     "ground_truth_source": ["09_troubleshoot_mobile_performance.md"],
     "ground_truth_snippet": "第一层排查是确认问题的影响范围...第二层排查方向是用户本地的网络环境...第三层排查方向是浏览器本身的性能问题...第四层排查方向是特定功能模块的性能问题",
     "reference_answer": "四层递进排查：先确认是单用户还是多用户反映（判断是否后端问题）、再查本地网络环境、再查浏览器插件/标签页占用资源、最后查特定功能模块本身的数据计算量是否过大。",
     "question_type": "factual"},
    {"id": 28, "question": "只有一个客户反馈系统卡，是不是说明后端服务器出问题了？",
     "ground_truth_source": ["09_troubleshoot_mobile_performance.md"],
     "ground_truth_snippet": "如果确认是多个用户同时反馈类似的响应慢问题，大概率是系统后端服务层面的性能瓶颈...如果确认是仅该用户或者小范围用户遇到的问题，第二层排查方向是用户本地的网络环境",
     "reference_answer": "不一定，只有单个用户反馈时更可能是该用户本地网络环境或浏览器插件占用资源的问题，而不是后端服务器问题——多个用户同时反馈才更倾向于判断是后端服务负载问题。",
     "question_type": "negation"},

    # ========== 10_objection_decision_contract.md ==========
    {"id": 29, "question": "客户说需要跟领导汇报再决定，销售应该怎么应对？",
     "ground_truth_source": ["10_objection_decision_contract.md"],
     "ground_truth_snippet": "主动询问几个关键问题：最终决策人是谁、大概的决策时间点...主动提出协助准备汇报材料",
     "reference_answer": "主动询问决策人是谁、决策时间点、决策人关心的因素、联系人的角色权重，并主动协助准备汇报材料（价值总结、案例、预判应答清单），条件允许尽量争取直接跟决策人沟通。",
     "question_type": "factual"},
    {"id": 30, "question": "客户想先试用一段时间再决定，试用方案应该怎么设计？",
     "ground_truth_source": ["10_objection_decision_contract.md"],
     "ground_truth_snippet": "明确的试用周期（通常建议14到30天）...明确的核心验证指标...明确的试用结束后的决策时间承诺",
     "reference_answer": "应包含明确试用周期（建议14到30天）、明确的核心验证指标（提前约定要验证的具体指标）、明确试用结束后的决策时间承诺，且试用期内要保持定期主动跟进。",
     "question_type": "factual"},
    {"id": 31, "question": "客户法务对合同条款提了修改意见，销售能不能自己当场答应下来？",
     "ground_truth_source": ["10_objection_decision_contract.md"],
     "ground_truth_snippet": "销售个人没有权限自行承诺修改，必须严格遵循内部审批流程，任何在合同条款上的口头承诺如果没有经过正式的合同修订流程确认，都不具备法律效力",
     "reference_answer": "不能。涉及SLA、数据安全保密、提前终止条款等争议点时，销售个人没有权限自行承诺修改，必须走内部审批流程，未经正式合同修订流程确认的口头承诺不具备法律效力。",
     "question_type": "negation"},

    # ========== 11_sales_sop_team_kpi.md ==========
    {"id": 32, "question": "销售季度成交总金额是按照什么日期归属考核周期的？",
     "ground_truth_source": ["11_sales_sop_team_kpi.md"],
     "ground_truth_snippet": "严格以合同上盖章生效的实际日期为准",
     "reference_answer": "严格以合同盖章生效的实际日期为准，不是回款到账日期，也不是商机创建日期。",
     "question_type": "factual"},
    {"id": 33, "question": "销售话术库的内容更新需要经过什么审核流程？",
     "ground_truth_source": ["11_sales_sop_team_kpi.md"],
     "ground_truth_snippet": "需要先经过销售运营团队的初步审核...再提交给销售管理层最终审批通过后才会正式上线",
     "reference_answer": "先经过销售运营团队初步审核（确认逻辑清晰、符合公司价值观和合规要求），再提交销售管理层最终审批通过才会正式上线替换。",
     "question_type": "factual"},
    {"id": 34, "question": "上个季度谈的合同，这个季度才盖章，这笔业绩算哪个季度的？",
     "ground_truth_source": ["11_sales_sop_team_kpi.md"],
     "ground_truth_snippet": "即便合同谈判的绝大部分工作是在上一个季度完成的，只要最终盖章日期落在新的季度，这笔业绩就归属新的季度考核周期",
     "reference_answer": "算新季度的业绩。即便谈判大部分工作在上季度完成，只要最终盖章日期落在新季度，这笔业绩就归属新季度考核周期，因为盖章日期是唯一确定且不可篡改的客观依据。",
     "question_type": "colloquial"},

    # ========== 12_feature_integration_security.md ==========
    {"id": 35, "question": "CRM系统的API调用频率限制是多少？",
     "ground_truth_source": ["12_feature_integration_security.md"],
     "ground_truth_snippet": "标准套餐的限流规则是每个应用每分钟最多调用600次接口请求",
     "reference_answer": "标准套餐每个应用每分钟最多调用600次接口请求，超过会被直接拒绝并返回限流错误码。",
     "question_type": "factual"},
    {"id": 36, "question": "系统对外承诺的服务可用性指标是多少？",
     "ground_truth_source": ["12_feature_integration_security.md"],
     "ground_truth_snippet": "系统对外承诺的服务可用性指标是99.9%",
     "reference_answer": "99.9%，即年度累计不可用时间不超过约8.76小时，该指标涵盖计划外故障停机，不包含提前通知的计划性维护窗口。",
     "question_type": "factual"},
    {"id": 37, "question": "客户误删了一大批数据，是不是彻底没法恢复了？",
     "ground_truth_source": ["12_feature_integration_security.md"],
     "ground_truth_snippet": "标准套餐支持将数据恢复到过去30天内任意一个备份时间点",
     "reference_answer": "不是没法恢复，标准套餐支持恢复到过去30天内任意一个备份时间点，但需要联系客户支持团队提交恢复申请，且恢复操作会覆盖恢复时间点之后产生的所有数据变更。",
     "question_type": "negation"},

    # ========== 跨文档多跳推理题 ==========
    {"id": 38, "question": "一个客户健康度评分是红色，同时账号使用量已经接近套餐上限，客户成功经理应该怎么同时处理流失风险和扩容机会这两件事？",
     "ground_truth_source": ["05_feature_customer_success.md"],
     "ground_truth_snippet": "红色客户则需要更高优先级的挽留动作...增购管理...识别潜在的扩容信号，比如客户的实际登录用户数已经接近或超过当前套餐的许可账号上限",
     "reference_answer": "红色客户需要更高优先级的挽留动作（可能需要主管甚至销售总监介入了解真实流失原因），同时账号接近上限属于扩容信号，客户成功模块会同时标记为扩容机会推送跟进——两者需要客户成功经理综合评估，先理解客户真实顾虑，扩容建议要基于实际业务瓶颈提出。",
     "question_type": "multi_hop"},
    {"id": 39, "question": "销售在合同审批流程中，如果客户对折扣有异议，同时又对合同条款有法务方面的顾虑，这两类问题分别应该走什么流程？",
     "ground_truth_source": ["01_sales_sop_lead_to_deal.md", "10_objection_decision_contract.md"],
     "ground_truth_snippet": "折扣在7折到9折之间需要销售总监二级审批 / 合同条款需要法务审核...销售个人没有权限自行承诺修改，必须严格遵循内部审批流程",
     "reference_answer": "折扣异议走CRM系统自动路由的审批流程（按折扣力度分级由主管/总监/总经理审批），合同条款异议走法务审核流程（销售无权自行承诺修改，需升级给法务或更高管理层评估），两者是独立的流程体系不能混用。",
     "question_type": "multi_hop"},
    {"id": 40, "question": "客户提了一个功能需求说友商能做但我们系统做不到，同时客户还提到之前有一次工单响应比较慢，这两个问题在销售话术上处理思路有什么共同点？",
     "ground_truth_source": ["03_objection_feature_service.md"],
     "ground_truth_snippet": "不应该含糊其辞或者夸大宣传...正确的处理方式，第一步是诚恳承认并具体了解客户遇到的问题细节",
     "reference_answer": "两者的共同处理思路都是先诚实/诚恳承认问题本身（不夸大宣传声称有类似功能，不轻描淡写售后响应问题），再针对具体顾虑给出建设性方案（功能差距评估业务影响程度、售后问题给出具体改进措施和保障机制），都避免用不诚实或推卸责任的方式回应。",
     "question_type": "multi_hop"},
]

if __name__ == "__main__":
    from collections import Counter
    print(f"共 {len(EVAL_QUESTIONS)} 个评测问题")
    type_counts = Counter(q["question_type"] for q in EVAL_QUESTIONS)
    print("问题类型分布:", dict(type_counts))
    all_docs = set()
    for q in EVAL_QUESTIONS:
        all_docs.update(q["ground_truth_source"])
    print(f"覆盖 {len(all_docs)} 篇文档")
