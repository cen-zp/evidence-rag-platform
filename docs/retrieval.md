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

1. Qdrant 中的本地哈希向量 Top-N（`max(4 × top_k, 20)`）。
2. 当前知识库所有 `ready` chunk 的内存 BM25 关键词排序。

RRF 只使用各自的**排名**而不是原始分数，因此可以避免直接比较不同检索器的分值尺度。API 返回的 `score` 是 RRF 排序分数，不是概率、置信度或准确率。

## 隔离与可用性规则

1. Qdrant 查询必须带 `knowledge_base_id` payload filter。
2. 查询结果还会回查 PostgreSQL，只返回属于目标知识库且文档状态为 `ready` 的 chunk。
3. 空知识库返回空数组；不存在的知识库返回 404；Qdrant 不可用返回 503。

两层过滤避免了过期向量、失败文档或跨知识库 point 被当成可引用证据。

## 当前边界

Dense 检索使用本地 `BAAI/bge-small-zh-v1.5` 生成 512 维归一化语义向量；RRF 分数本身仍不是概率或可靠置信度，不能直接作为固定拒答阈值。BM25 目前在应用进程中遍历当前知识库的 `ready` chunk，适合本地 MVP 和建立效果基线；文档量增长后应替换为 PostgreSQL 全文检索或 Qdrant sparse vector。该检索端点本身不调用 DeepSeek；它已被证据问答链路使用，具体的上下文约束和引用校验见 [grounded-chat.md](grounded-chat.md)。
