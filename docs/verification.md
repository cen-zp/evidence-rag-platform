# 本地验收记录

本文件只记录可复现的本地验收结论，不包含 API Key、数据库密码或其他密钥。

## 2026-07-14：证据问答闭环

环境：本地 Docker Compose 的 PostgreSQL、Redis、Qdrant；本地 FastAPI；DeepSeek `deepseek-v4-flash`。

- 知识库：`兼容性复测知识库`，其中已有已处理完成的 Markdown 文档。
- 问题：`根据资料，上传文档后处于什么状态？`
- 结果：HTTP 200；答案为 `pending`；后端测得模型耗时 `3612 ms`。
- 引用：服务端返回 1 个 `document-intake.md` chunk，且其 chunk ID 属于同一次、同一知识库的检索结果。

结论：真实链路已验证为“Qdrant 检索 -> DeepSeek 生成结构化引用 -> 服务端引用校验 -> 返回来源片段”。该次验证只说明工程链路和引用约束有效；本地哈希向量仍不是语义检索质量结论，不能据此宣称准确率或固定拒答阈值。

## 2026-07-14：检索评测运行器烟雾验证

- 题集：[evals/smoke.jsonl](../evals/smoke.jsonl)，共 1 条案例；目标知识库为本地 `兼容性复测知识库`。
- 配置：混合检索，`top_k=3`。
- 结果：`recall_at_k=1.0`、`mean_reciprocal_rank=1.0`、本地检索延迟约 `47.4 ms`。

结论：JSONL 题集、运行器、PostgreSQL/Qdrant 检索和指标输出已真实连通。样本量只有 1，**不得**作为检索效果宣传；需积累 60–100 条独立案例后才记录正式指标。
