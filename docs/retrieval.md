# M3：知识库隔离混合检索

当前检索 API：

```text
POST /api/knowledge-bases/{kb_id}/search
```

请求体：

```json
{
  "query": "上传后如何查看处理状态？",
  "top_k": 5
}
```

响应中的每个结果包含 `chunk_id`、`document_id`、文件名、原文、页码/位置与相似度分数。这些 ID 将是后续问答引用的唯一依据。

## 混合排序基线

当前实现将两条候选列表以 Reciprocal Rank Fusion（RRF，`k=60`）合并：

1. Qdrant 中的本地 BGE 语义向量 Top-N（`max(4 × top_k, 20)`）。
2. 当前知识库所有 `ready` chunk 的内存 BM25 关键词排序。

RRF 只使用各自的**排名**而不是原始分数，因此可以避免直接比较不同检索器的分值尺度。API 返回的 `score` 是 RRF 排序分数，不是概率、置信度或准确率。

## 隔离与可用性规则

1. Qdrant 查询必须带 `knowledge_base_id` payload filter。
2. 查询结果还会回查 PostgreSQL，只返回属于目标知识库且文档状态为 `ready` 的 chunk。
3. 空知识库返回空数组；不存在的知识库返回 404；Qdrant 不可用返回 503。

两层过滤避免了过期向量、失败文档或跨知识库 point 被当成可引用证据。

## 低置信度守卫

启用 Reranker 时，系统会在模型调用前过滤顶部相关性分数低于 `RETRIEVAL_MIN_SCORE` 的候选；过滤后为空即由 `retrieval-guard` 拒答，不调用 DeepSeek。默认值 `0.02` 来自固定 CPU 配置下的离线校准：[报告](../evals/results/fastapi-official-confidence-calibration.json)使用 72 条已有单人声明式审核的支持问题和 24 条开发者声明式、明显超出 FastAPI 语料范围的问题。该阈值保留 `65/72 (90.3%)` 支持问题并拒绝 `22/24 (91.7%)` 越界问题；文件级 Recall@5 从 `64/72 (88.9%)` 降为 `59/72 (81.9%)`。

阈值只应用于当前 `BAAI/bge-reranker-base` 的分数，关闭 Reranker 的 RRF-only 对照不应用它。越界题未经过独立第三方审核，报告只能作为工程校准证据；更换语料、模型或候选数后必须重新校准，不能把 `0.02` 当作通用概率阈值。

## 当前边界

Dense 检索使用本地 `BAAI/bge-small-zh-v1.5` 生成 512 维归一化语义向量；RRF 分数本身不是概率，因此拒答阈值只使用固定 Reranker 配置的已校准分数。BM25 目前在应用进程中遍历当前知识库的 `ready` chunk，适合本地 MVP 和建立效果基线；文档量增长后应替换为 PostgreSQL 全文检索或 Qdrant sparse vector。该检索端点本身不调用 DeepSeek；它已被证据问答链路使用，具体的上下文约束和引用校验见 [grounded-chat.md](grounded-chat.md)。

## 本地重排序

RRF 会先融合 Dense 与 BM25 的候选，再将前 10 个候选交给本地
`BAAI/bge-reranker-base` CrossEncoder，按问题与片段的联合相关性重新排序，最后返回
`top_k`。该模型不写入 Qdrant，也不需要重新索引文档；它只影响每次查询的排序和本地
CPU 延迟。

CrossEncoder 分数不是通用置信度或概率；这里只在固定模型、语料、候选数和已标注校准集内把它作为拒答信号。候选数量通过 `RERANKER_CANDIDATE_COUNT` 配置，默认 10；仍需在固定题集上比较“RRF only”与“RRF + Reranker”的 Recall@K、MRR 和延迟，才能做真实效果结论。
