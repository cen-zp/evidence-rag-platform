# M2-B：异步文档处理与本地索引基线

上传接口在成功保存文件后，会向 Redis 中的 ARQ 队列提交 `process_document` 任务。Worker 按以下状态转换处理每个任务：

```text
pending -> processing -> ready
                     -> failed（保留错误原因）
```

Worker 当前能够：

1. 提取 UTF-8 Markdown、PDF 或 DOCX 的可读文本；PDF chunk 保留页码。
2. 按 800 字符、120 字符重叠切分文本。
3. 将 chunk 元数据写入 PostgreSQL，并以同一 chunk UUID 写入 Qdrant。
4. 使用 `knowledge_base_id` 与 `document_id` 作为 Qdrant payload，供后续强制隔离过滤。

DOCX 当前提取普通段落和标题文本，不保留 Word 的页码、表格、批注或图片内容；这些内容不能被当作已支持的证据来源。

## 运行方式

先启动 Compose 基础设施和 API，再在一个单独终端启动 Worker：

```bash
cd apps/api
uv run arq app.workers.document.WorkerSettings
```

上传成功后，轮询 `GET /api/knowledge-bases/{kb_id}/documents`，直到状态从 `pending` 变为 `ready` 或 `failed`。

如果 Redis 暂时不可用或解析失败，保留的源文件可通过
`POST /api/knowledge-bases/{kb_id}/documents/{document_id}/retry` 重新入队。该接口只接受
`failed` 状态，避免为仍在排队或处理中任务重复投递；源文件缺失时会明确拒绝重试。

## 本地语义 Embedding

当前使用本地 `BAAI/bge-small-zh-v1.5` 模型生成 512 维归一化向量，默认在 CPU 上运行。模型首次启动会下载到本机 Hugging Face 缓存；之后不需要为向量调用支付 API 费用。

模型或向量维度变更会使用新的 Qdrant collection，防止不同维度的向量混用。现有 `ready` 文档不会自动改写；确认模型可用后，使用以下命令显式重建某个知识库：

```bash
cd apps/api
uv run python -m app.reindex --knowledge-base-id <知识库 UUID>
```

该命令会重新解析该知识库内所有 `ready` 文档并写入当前 collection。正式效果仍需在独立题集上记录 Recall@K、MRR、延迟和模型下载/推理资源取舍，不能凭单个演示问题宣称准确率。
