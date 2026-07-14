# M2-B：异步文档处理与本地索引基线

上传接口在成功保存文件后，会向 Redis 中的 ARQ 队列提交 `process_document` 任务。Worker 按以下状态转换处理每个任务：

```text
pending -> processing -> ready
                     -> failed（保留错误原因）
```

Worker 当前能够：

1. 提取 UTF-8 Markdown 或 PDF 的可读文本；PDF chunk 保留页码。
2. 按 800 字符、120 字符重叠切分文本。
3. 将 chunk 元数据写入 PostgreSQL，并以同一 chunk UUID 写入 Qdrant。
4. 使用 `knowledge_base_id` 与 `document_id` 作为 Qdrant payload，供后续强制隔离过滤。

## 运行方式

先启动 Compose 基础设施和 API，再在一个单独终端启动 Worker：

```bash
cd apps/api
uv run arq app.workers.document.WorkerSettings
```

上传成功后，轮询 `GET /api/knowledge-bases/{kb_id}/documents`，直到状态从 `pending` 变为 `ready` 或 `failed`。

## 向量基线的真实边界

当前使用 `LocalHashEmbedding`：它把英文词和中文字符稳定映射为 384 维归一化向量，因此可完全离线地验证 Qdrant 写入、ID 契约和后续检索链路。

它是**词项/字符匹配基线，不是语义 Embedding 模型**。不能据此宣称语义检索效果；正式评测前必须替换为可配置的真实 Embedding 提供方，并在同一评测集上记录效果、延迟与成本。
