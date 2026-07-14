# M1 数据模型与 ID 契约

当前阶段采用本地单用户模式，只持久化完成文档入库与检索闭环所需的三个实体：

- `KnowledgeBase`：资料集合。
- `Document`：上传文件及其处理状态。
- `DocumentChunk`：可检索的原文片段及位置元数据。

## 隔离规则

`DocumentChunk` 同时保存 `document_id` 和 `knowledge_base_id`，数据库使用复合外键保证它不能引用其他知识库中的文档。后续检索必须始终携带 `knowledge_base_id` 过滤条件。

## PostgreSQL 与 Qdrant ID 规则

`DocumentChunk.id` 是 UUID，也是对应 Qdrant point 的唯一 ID。Qdrant payload 只重复保存检索所需的 `knowledge_base_id`、`document_id`、位置与文本元数据，不再生成第二套 point ID。

这样可以直接从向量检索结果回查 PostgreSQL chunk，并降低删除、重建索引时产生孤儿数据的风险。

## 当前边界

当前已实现本地单用户的文件上传、Markdown/PDF 解析、分块、Qdrant 写入、知识库隔离检索和服务端引用校验。Qdrant 向量目前由本地哈希向量器生成，只用于验证索引工程链路，并不代表语义检索效果。`User`、`Conversation`、`Message` 与评测会在真实产品流程需要时再加入，避免一次性建立尚未验证的数据结构。
