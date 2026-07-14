# 数据模型与 ID 契约

当前本地工作台持久化以下核心实体：

- `User` 与 `UserSession`：scrypt 密码哈希和可撤销 Bearer 会话；不保存明文密码。
- `KnowledgeBase`：资料集合，必须归属一个账户。
- `Document`：上传文件及其处理状态。
- `DocumentChunk`：可检索的原文片段及位置元数据。
- `Conversation`、`ConversationMessage` 与 `MessageFeedback`：知识库内的会话、服务端校验后的回答快照与点赞/踩。
- `EvaluationCase`、`AnswerReview` 与 `ModelCall`：检索案例、人工答案/引用评审及不含正文的模型调用元数据。

## 隔离规则

`KnowledgeBase.owner_id` 是 API 所有读写的第一层过滤条件；不能列出、读取或修改其他账户的知识库、文档、检索、评测、会话或模型调用记录。`DocumentChunk` 同时保存 `document_id` 和 `knowledge_base_id`，数据库使用复合外键保证它不能引用其他知识库中的文档。后续检索必须始终携带 `knowledge_base_id` 过滤条件。

## PostgreSQL 与 Qdrant ID 规则

`DocumentChunk.id` 是 UUID，也是对应 Qdrant point 的唯一 ID。Qdrant payload 只重复保存检索所需的 `knowledge_base_id`、`document_id`、位置与文本元数据，不再生成第二套 point ID。

这样可以直接从向量检索结果回查 PostgreSQL chunk，并降低删除、重建索引时产生孤儿数据的风险。

## 当前边界

当前已实现本地账户隔离、Markdown/PDF/DOCX 上传、异步解析、分块、BGE 向量写入、知识库隔离检索、服务端引用校验、持久化会话和回答反馈。该模式仍是本地演示交付：没有邮箱验证、找回密码、管理员能力或生产级身份提供商集成。BGE、BM25、RRF 和重排序的工程链路已验证，但效果结论仍必须来自独立题集和人工标注。
