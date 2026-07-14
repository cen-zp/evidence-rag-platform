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

## 2026-07-14：DOCX 处理链路

- 使用本地临时生成的 Word 文档，不含用户资料。
- 结果：上传后进入 `pending`，ARQ Worker 成功完成解析与索引，文档状态更新为 `ready`。
- PostgreSQL 验证：该文档生成 1 个 chunk。

结论：DOCX 已覆盖上传、异步解析、分块、向量写入和状态更新链路；当前只提取段落/标题文本，不支持表格、批注、图片或精确页码。

## 2026-07-14：持久化评测案例 API

- 数据库迁移：`20260714_0002` 已应用到本地 PostgreSQL。
- 在本地验收知识库保存 1 条问题、预期来源文件名和参考答案。
- 通过 `POST /evaluations/retrieval?top_k=3` 运行，结果为 Recall@3=`1.0`、MRR=`1.0`、检索延迟约 `27.3 ms`。

结论：评测案例的创建、持久化和 API 运行链路已验证。样本量为 1，仅是功能烟雾测试；正式报告必须使用独立的 60–100 条案例。

## 2026-07-14：本地 BGE 语义向量迁移

- 模型：本地 `BAAI/bge-small-zh-v1.5`，实际加载并返回归一化的 512 维向量。
- 迁移策略：新建 `document_chunks_bge_small_zh_v1_5` collection，不覆盖旧的 384 维哈希向量 collection。
- 重建对象：3 个本地验收知识库的全部 3 份 `ready` 文档；源文件预检均存在。
- 结果：新 collection 共写入 5 个点；分别对 Markdown、文档处理说明和 DOCX 知识库进行本地检索，均返回当前知识库内的来源文件。

结论：本地语义 Embedding、重新解析、Qdrant 写入和按知识库检索已真实连通。本次只验证工程迁移与隔离，不比较旧/新模型效果；正式结论仍需在独立 60–100 条题集上对比 Recall@K、MRR、延迟与资源开销。

## 2026-07-14：BGE 检索烟雾评测

- 题集：[evals/smoke.jsonl](../evals/smoke.jsonl)，仅 1 条案例；结果文件：[evals/results/bge-smoke.json](../evals/results/bge-smoke.json)。
- 配置：本地 `BAAI/bge-small-zh-v1.5` + BM25 + RRF，`top_k=3`。
- 结果：Recall@3=`1.0`、MRR=`1.0`、本地检索延迟 `160.6 ms`。

结论：BGE 迁移后的评测运行器已真实连通。案例数为 1，不能比较模型优劣或作为简历指标；延迟包含本地模型推理，需在固定硬件、预热策略和 60–100 条独立题集下重新测量。

## 2026-07-14：本地 Reranker 验证

- 模型：本地 `BAAI/bge-reranker-base` CrossEncoder；RRF 前 10 个候选参与二次排序。
- 两候选烟雾验证：与“上传后状态”相关的片段排在无关会议记录之前，最高分约 `0.951`。
- 真实链路：对 `兼容性复测知识库` 的“上传文件后如何查看状态？”查询，返回当前知识库内的 `document-intake.md`；本地混合检索加重排测得约 `316.5 ms`。

结论：Dense、BM25、RRF 与本地 CrossEncoder 重排序已经真实串联。该知识库只有 1 个来源文件，不能从本次结果推断重排序效果；需扩充独立题集和多文档候选后进行 A/B 对比。

## 2026-07-14：RRF-only 与 Reranker 对比烟雾评测

同一条案例、同一知识库、`top_k=3` 下的可追溯结果：

| 配置 | Recall@3 | MRR | 本地检索延迟 |
| --- | ---: | ---: | ---: |
| BGE + BM25 + RRF | 1.0 | 1.0 | 170.6 ms |
| BGE + BM25 + RRF + Reranker | 1.0 | 1.0 | 1290.4 ms |

结果文件分别为 [bge-rrf-only-smoke.json](../evals/results/bge-rrf-only-smoke.json) 与 [bge-reranker-smoke.json](../evals/results/bge-reranker-smoke.json)，其中包含 `reranker_enabled` 配置标记。

结论：对比工具和配置记录可复现；只有 1 个来源文件时重排序没有改变排名，首次本地 CrossEncoder 推理增加了明显延迟。后续必须使用多文档、60–100 条独立题集并预热模型后，才能判断是否值得保留该延迟开销。

## 2026-07-14：BGE + Reranker 真实证据问答复测

- 知识库：`兼容性复测知识库`，使用重建后的 BGE collection 与本地 CrossEncoder 重排序。
- 问题：`上传文件后文档处于什么状态？`
- 结果：HTTP 200；模型为 `deepseek-v4-flash`；模型调用耗时 `2735 ms`。
- 引用：返回 1 条 `document-intake.md` 来源，且包含服务端返回的 chunk ID。
- 请求总耗时：`38569.9 ms`，其中包含独立进程内 BGE 与 Reranker 的冷启动加载，不可作为稳态用户延迟。

结论：BGE 检索、BM25、RRF、CrossEncoder Reranker、DeepSeek 结构化回答与服务端引用校验已真实端到端连通。该次仅验证工程链路与引用约束；没有用来评估答案正确率或重排序质量。
