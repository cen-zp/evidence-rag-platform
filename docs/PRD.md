# Evidence RAG Platform — 产品与工程规格

## 1. 问题与用户

目标用户是需要查询内部资料的学生团队、小型组织或技术团队。普通聊天机器人无法说明答案来自哪里，也无法保证回答只依据已上传资料。本系统提供来源可追溯、可评测的资料问答体验。

## 2. 成功标准

到第 6 周，项目必须满足：

1. 一名新用户能在 5 分钟内完成注册、建库、上传文件和提问。
2. 每个正常回答至少展示一个对应来源片段与页码/位置。
3. 在自建的 60–100 条评测问题中，记录检索命中率、引用正确率、端到端延迟和平均单次成本。
4. 对没有依据的问题拒答，不把模型猜测伪装成资料结论。
5. README 提供架构图、启动方式、评测方法、已知限制及 3–5 分钟演示视频。

不在第一阶段承诺虚构的准确率或并发量；所有结果都由实际评测产生。

## 3. 用户流程

```text
注册/登录 -> 创建知识库 -> 上传资料 -> 后台解析与索引
                                      -> 查看处理状态/失败原因
进入问答页 -> 输入问题 -> 混合检索与重排序 -> 模型生成
          -> 查看答案、来源片段、耗时 -> 点赞/踩与反馈
```

## 4. 功能边界

### 第 1 阶段：必须完成（MVP）

- 用户认证；知识库、文档、会话的隔离
- PDF、DOCX、Markdown 上传；文件大小和类型校验
- ARQ 后台任务：提取文本、切分、生成向量、更新处理状态
- 文档状态：`pending`、`processing`、`ready`、`failed`
- 问答接口与流式输出
- Dense 检索 + 关键词检索结果融合；Top-K 重排序
- 答案中的来源编号、原文片段与页码/段落位置
- 低置信度拒答规则：检索分数不足、上下文为空、模型未返回引用
- 基础聊天历史、请求日志与用户反馈

### 第 2 阶段：用于拉开差距

- 文档版本、删除与重新索引
- 按标题、文件、日期等元数据过滤
- 评测管理页：基线与优化版本的指标对比
- Token/成本统计、调用链追踪与错误告警
- 角色权限、公开知识库分享、限流

### 明确不做

- 多模态 OCR、复杂组织权限、在线协作文档编辑
- 自行训练大模型
- 为“看起来高级”强行拆成微服务或引入多 Agent

## 5. 核心数据模型

| 实体 | 关键字段 |
| --- | --- |
| User | id、email、password_hash、created_at |
| KnowledgeBase | id、owner_id、name、description、created_at |
| Document | id、kb_id、filename、mime_type、status、version、error_message |
| DocumentChunk | id、document_id、content、page_no、chunk_index、metadata |
| Conversation | id、kb_id、user_id、title |
| Message | id、conversation_id、role、content、citations、latency_ms、cost |
| Feedback | id、message_id、rating、comment |
| EvaluationCase | id、kb_id、question、expected_sources、reference_answer |

PostgreSQL 存业务数据和审计信息；Qdrant 只存 chunk 向量及必要检索元数据，二者通过 `chunk_id` 关联。

## 6. 服务架构

```text
Next.js Web
    |
FastAPI API ---- PostgreSQL
    |      \
    |       ---- Redis <---- ARQ Worker ---- 文件解析/向量化
    |
    +---- Qdrant（向量与关键词检索）
    |
    +---- DeepSeek Chat API / Embedding API
```

检索链路：Query 改写（可选） -> Dense Top-20 + BM25 Top-20 -> RRF 融合 -> Rerank Top-8 -> 组装可引用上下文 -> 生成带来源编号的回答。

## 7. 关键工程决策

- **先做单体应用**：前后端、Worker 虽分进程但同一仓库；这一规模更利于交付和面试讲解。
- **API 密钥只放后端环境变量**：前端永不保存真实密钥；提交 `.env.example`，绝不提交 `.env`。
- **用结构化引用而非文本匹配**：让模型返回 `answer` 与 `citation_ids`，由服务端校验引用是否来自检索结果。
- **评测早于炫技**：第 2 周就收集真实问题，第 5 周用同一题集评估不同检索配置。
- **异步入库**：上传接口只创建任务；避免大文件解析阻塞请求。

## 8. 面试可讲的技术取舍

1. 为什么需要混合检索与重排序，而不是只做向量检索？
2. 如何把“模型回答正确”拆为检索命中、引用正确和生成质量？
3. 如何在检索效果、响应延迟与模型费用之间取舍？
4. 如何防止回答没有依据或越权读取其他知识库的资料？
5. 为什么用异步任务，失败后如何重试和向用户展示状态？

## 9. 简历素材（完成后才使用）

完成后按真实结果填写：

> 独立开发可评测知识库问答平台，基于 FastAPI、Next.js、Qdrant 与大模型 API 实现文档异步解析、混合检索、重排序及可追溯引用；构建 N 条评测集，对比优化前后检索命中率、引用正确率、延迟与单次成本，并以 Docker Compose 完成部署。

其中 N 和所有指标必须替换为真实测试数据。
