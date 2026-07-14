# M3-A：知识库隔离检索

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

## 隔离与可用性规则

1. Qdrant 查询必须带 `knowledge_base_id` payload filter。
2. 查询结果还会回查 PostgreSQL，只返回属于目标知识库且文档状态为 `ready` 的 chunk。
3. 空知识库返回空数组；不存在的知识库返回 404；Qdrant 不可用返回 503。

两层过滤避免了过期向量、失败文档或跨知识库 point 被当成可引用证据。

## 当前边界

检索向量仍是本地哈希基线，分数只说明字符/词项重合度，不能作为语义质量指标或固定拒答阈值。当前端点也不调用 DeepSeek，不会生成答案；下一阶段会将受检索结果约束的上下文、引用校验和回答生成组合起来。
