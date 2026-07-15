# 本地验收记录

本文件只记录可复现的本地验收结论，不包含 API Key、数据库密码或其他密钥。

## 2026-07-14：已登录工作台 SSE 问答

- 环境：Docker Compose API/Web 已升级至 Alembic `20260714_0007`；用户在本地工作台完成账户注册并选择既有知识库。
- 结果：浏览器完成知识库、文档、评测、会话与模型用量摘要的已认证读取；真实 `POST /api/chat/stream` 返回 HTTP `200`，随后会话列表和模型调用摘要请求均成功。
- 安全：本次只检查无请求正文的服务访问日志；没有读取账户密码、Bearer token、问题、回答或 API Key。

结论：本地浏览器 -> 已认证 API -> SSE 进度流 -> 知识库问答的实际链路已通过。该记录不包含独立题集人工评分，因此不构成答案正确率、引用正确率、成本或检索质量结论。

## 2026-07-14：已登录工作台回答反馈

- 环境：同一已认证本地工作台会话，对刚完成的知识库回答点击“有帮助”。
- 结果：浏览器对当前会话消息的反馈接口先完成 CORS 预检 `200`，再完成 `POST .../feedback`，返回 `201 Created`。
- 安全：只检查了无请求正文的访问日志；没有记录问题、回答、账户凭据或 API Key。

结论：反馈控件到数据库写入的真实浏览器链路已通过。一次正向反馈不代表模型效果或用户满意度统计。

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

## 2026-07-14：验收文档演示题集检索对比（非简历指标）

- 语料：新建本地“验收演示知识库（非简历指标）”，包含项目自身的 `README.md`、文档处理、检索、评测和本验证记录共 5 份 Markdown 文档。
- 题集：[evals/demo-acceptance.jsonl](../evals/demo-acceptance.jsonl)，20 条人工编写问题；每题的预期文件直接来自上述项目文档。
- 配置：相同语料、`top_k=3`，分别运行 RRF-only 与启用本地 `BAAI/bge-reranker-base` 的配置。

| 配置 | Recall@3 | MRR | 平均本地检索延迟 |
| --- | ---: | ---: | ---: |
| BGE + BM25 + RRF | 0.950 | 0.867 | 19.0 ms |
| BGE + BM25 + RRF + Reranker | 1.000 | 0.858 | 917.0 ms |

结果文件：[demo-rrf-only.json](../evals/results/demo-rrf-only.json) 与 [demo-reranker.json](../evals/results/demo-reranker.json)。两份报告均记录了 `reranker_enabled`，可以复跑。

结论：多文档种子、20 题运行器和两种配置已真实连通；在这套自生成题集上，重排序补回了 1 条 Top-3 命中，但平均首个正确来源排名略低且本地延迟显著增加。题目与语料来自同一项目验收文档，存在明显的自描述偏差，**只用于功能演示与回归检查，不用于简历、公开效果结论或模型选型**。后续应以 60–100 条独立问题、独立标注来源和预热后的固定硬件重新评估。

## 2026-07-14：完整 Docker Compose 栈

- 构建：API 镜像使用 CPU-only PyTorch 锁定依赖；Web 使用 Next.js production build；构建上下文排除了本机 `.venv`、`node_modules` 与上传文件。
- 启动：`docker compose up --build -d --wait` 后，PostgreSQL、Redis、Qdrant、API、ARQ Worker 与 Web 均处于运行状态；API 启动时已应用 Alembic head。
- HTTP 验证：`GET http://localhost:8000/health` 返回 200；`HEAD http://localhost:3000` 返回 200；来自 `http://localhost:3000` 的 API CORS 预检返回对应的 `Access-Control-Allow-Origin`。
- 数据卷：上传文件由 API/Worker 共用 `uploads_data`；本地模型缓存使用 `model_cache`，避免容器重建后重复下载。

结论：完整本地交付栈已真实启动并通过 Web/API/CORS 冒烟验证。本次没有上传文件、执行检索或调用 DeepSeek，因此不构成模型效果、异步处理吞吐或端到端问答质量结论。

## 2026-07-14：验收演示题集真实证据问答批次（非简历指标）

- 题集：[evals/demo-acceptance.jsonl](../evals/demo-acceptance.jsonl)，20 条问题；语料和题目均来自项目自身验收文档。
- 环境：容器化 BGE、BM25、RRF、Reranker 与 DeepSeek `deepseek-v4-flash`；首次本地模型下载完成后执行。
- 结果：20/20 HTTP 200，20/20 返回至少一条服务端校验引用；平均模型调用耗时 `3646.4 ms`，P95 `4377 ms`。逐题非敏感汇总见 [demo-answer-batch.json](../evals/results/demo-answer-batch.json)。

结论：批量真实模型调用、证据检索和服务端引用校验已连通。该题集与知识库存在同源偏差，且没有对答案或引用做独立人工判分；**不得**用于简历、公开准确率结论、模型选型或成本结论。正式答案级评测必须使用独立题集、人工评审和明确样本量。

## 2026-07-14：模型调用元数据真实验证

- 环境：Docker Compose API 已升级至 Alembic `20260714_0004`；对既有“验收演示知识库（非简历指标）”执行 1 次真实证据问答。
- 结果：HTTP 200；新增 `model_calls` 记录 1 条，模型耗时 `6125 ms`，供应商返回 token 为输入 `2174`、输出 `406`、合计 `2580`。
- 汇总接口：`GET /api/knowledge-bases/{id}/evaluations/model-usage-summary` 返回 `call_count=1`、`usage_reported_call_count=1`，并与上述 token 和耗时一致。

结论：知识库证据问答的模型耗时和供应商 token 用量已可持久化、聚合查询；记录不包含问题、回答、历史、来源正文或 API Key。该 1 条调用仅验证观测链路，不构成成本、延迟或质量指标。

## 2026-07-14：知识库删除生命周期验证

- 环境：Docker Compose API/Web 已重新构建；创建名为“临时删除验收”的空知识库后立即调用删除接口。
- 结果：`DELETE /api/knowledge-bases/{id}` 返回 HTTP `204`；后续读取该知识库文档返回 HTTP `404`。
- 自动化覆盖：后端测试使用临时上传文件与假向量存储，验证删除会清理上传源文件、请求当前知识库的向量删除，并移除数据库记录。

结论：知识库删除的 API、容器链路与数据清理契约已验证。页面删除操作会先要求确认；本次只操作临时验收数据，未删除任何既有知识库。

## 2026-07-15：FastAPI 官方文档正式检索评测

- 语料与题集：9 篇 FastAPI 官方公开教程；72 条中文 AI 协助题目。每条问题、参考答案与预期来源均已按 [fastapi-official-review.csv](../evals/independent/fastapi-official-review.csv) 记录为独立人工复核通过。
- 证据：正式报告包含题集、manifest 和审核表 SHA-256；三份 artifact 的哈希分别为 `5d75df…261ac1`、`c62132…e7ec7` 与 `fa9cf3…f4bde`，并记录 72 条审核覆盖、1 个评审别名。
- 环境：Docker Compose；本地 `BAAI/bge-small-zh-v1.5`、BM25、RRF，重排时使用 `BAAI/bge-reranker-base`；`top_k=3`，每个配置先执行 3 条不计入指标的预热检索。

| 配置 | Recall@3 | MRR | 平均检索耗时 | P95 检索耗时 |
| --- | ---: | ---: | ---: | ---: |
| BGE + BM25 + RRF | 0.847 | 0.743 | 62.7 ms | 67.8 ms |
| BGE + BM25 + RRF + Reranker | 0.847 | 0.819 | 1390.0 ms | 1634.2 ms |

结果文件：[fastapi-official-formal-warm-rrf-only.json](../evals/results/fastapi-official-formal-warm-rrf-only.json) 与 [fastapi-official-formal-warm-reranker.json](../evals/results/fastapi-official-formal-warm-reranker.json)。同次未预热报告也保留为 [RRF-only](../evals/results/fastapi-official-formal-rrf-only.json) 与 [Reranker](../evals/results/fastapi-official-formal-reranker.json)，仅用于区分冷启动成本。

结论：在这套经人工复核的公开文档题集上，Reranker 提升了第一个正确来源的平均排名（MRR），但没有提升 Top-3 命中率，且在 CPU 上显著增加检索耗时。该结果可用于说明检索配置取舍；它只评测来源文件命中，不等同于答案正确率、引用充分性、拒答恰当性、端到端延迟或模型调用成本。

## 2026-07-15：FastAPI 官方文档真实答案批次

- 题集与知识库：使用同一套 72 条已完成问题/参考答案/来源映射人工复核的 FastAPI 官方公开文档题集；启用 `BAAI/bge-small-zh-v1.5`、BM25、RRF 与 `BAAI/bge-reranker-base`，`top_k=5`。
- 结果：72 条均执行检索；49 条得到带服务端校验引用的模型回答，21 条因模型输出了不属于本轮检索结果的引用而被 `retrieval_guard_invalid_citation` 拒答，2 条为上游 provider error。成功回答的模型耗时均值 `4090.7 ms`、P95 `7546 ms`；供应商共返回 `61139` prompt tokens、`18342` completion tokens、`79481` total tokens。
- 产物：[批次报告](../evals/results/fastapi-official-formal-answer-batch.json) 与 [人工审核表](../evals/independent/fastapi-official-formal-answer-review-human.csv)。报告记录当次模型/Embedding/Reranker、设备和 `top_k`；审核工具已将审核表与报告逐字段校验并输出哈希。

结论：正式公开语料上的真实检索、模型调用与服务端引用守卫已完成一次批处理记录。模型耗时不包含完整 HTTP/前端交互链路，不能称为端到端延迟；当次未设置可复核单价快照，不能据此得出成本结论。

## 2026-07-15：FastAPI 官方答案批次的单人声明式人工审核

- 审核范围：固定批次中 49 条 `answered`、21 条 `retrieval_guard_invalid_citation` 和 2 条 `provider_error`；后两条 provider error 按规则不进入任一质量分母。
- 校验：审核表覆盖全部 72 条，`review_method` 均为 `human`，`reviewer_count=1`；工具将每行的问题、回答、引用、模型、耗时和 outcome 与不可变批次报告逐字段比对通过。批次 SHA-256 为 `07f49a9a7c818fb04dc32ddb5cf9eee5a50f613d087eca9f84a9731131383f18`，审核表 SHA-256 为 `3a4551400d7d3a34aa79b722340e3633f306236f934a3b8e2b4ffabd1c4da8b3`。
- 结果：答案 `47/49 (95.9%)`，引用 `45/49 (91.8%)`，拒答 `0/21 (0.0%)`。

结论：这是对一次真实模型批次的单人逐题人工判断，可作为带样本量和审核限定的项目事实；校验程序不能证明评审者的真实身份或独立性，故不得夸大为多评审一致性结论。21 条拒答发生在模型产生非法引用后，不能解释为“没有检索命中”。该批次在短 `S1/S2` 引用键修复前生成，后续需以同一题集新跑真实批次，才能判断拒答是否改善。

## 2026-07-15：FastAPI 官方答案批次的模型辅助复核（非人工验收）

- 输入：上节的不可变 72 题真实批次报告；原始旧版 CSV 在 3 条含英文逗号的回答处发生列错位，且部分可编辑回答字段被改写，因此不能直接作为审计证据。
- 修复：迁移器从批次报告恢复问题、回答、引用、模型、耗时与 outcome，仅保留旧表末尾的 verdict/备注；新表明确标记全部 72 条为 `model_assisted`，并通过逐字段完整性校验。报告哈希为 `07f49a…3f18`，模型辅助审核表哈希为 `5d82e5…5b54`。
- 模型辅助诊断：答案 `46/49`、引用 `47/49`、拒答 `0/21`。这三项由 DeepSeek 评审，`is_human_review=false`，只能用于定位问题，**不能**写成独立人工评审、正式质量通过率或简历指标。
- 解释边界：21 条的系统 outcome 是 `retrieval_guard_invalid_citation`，表示模型返回了不属于本轮检索结果的引用；它发生在检索命中之后，不能仅凭该 outcome 断言“检索没有命中”。长 UUID 引用协议后续已改为短 `S1/S2` 标签并完成真实复测，见下一节；旧人审结果仍只对应旧批次。

产物：[模型辅助审核表](../evals/independent/fastapi-official-formal-answer-review-model-assisted.csv)。

## 2026-07-15：短引用键现存真实批次与成本快照

- 可审计产物：[短引用键批次报告](../evals/results/fastapi-official-formal-answer-compact-s1-20260715.json)，batch ID `02dbf511-6853-4dac-b420-779d74befa9c`，报告 SHA-256 `0050e4ed89e394a278a955da240d6545a24419286fe777e96cd2f5542db55fef`。
- 固定配置：同一 72 题公开 FastAPI 题集，`top_k=5`，CPU `BAAI/bge-small-zh-v1.5` + BM25 + RRF + `BAAI/bge-reranker-base`；Reranker 未关闭。
- 系统 outcome：56 条 `answered`、16 条 `retrieval_guard_invalid_citation`、0 条上游失败。相比旧 UUID 批次的 49/21/2，这是短键改善信号；新一轮人工审核完成前，不能写成答案、引用或拒答通过率。
- 模型与成本观测：72/72 次模型完成调用均有 usage 与成本快照，共 `83202` prompt、`22042` completion、`105244` total tokens；模型完成耗时均值 `3532.1 ms`、P95 `7274 ms`。
- 成本边界：报告记录 2026-07-15 核对的 DeepSeek 缓存未命中单价，输入 `1 CNY/百万 tokens`、输出 `2 CNY/百万 tokens`；保守估算总成本 `0.127286 CNY`、平均每次模型完成 `0.00176786 CNY`。该估算不是账单，也不含本地 CPU、基础设施或人工成本。
- 串批边界：数据库中还存在其他批次的调用元数据，但没有同时保留下来可逐题核验的不可变报告；本节只接受上述 batch ID 与报告哈希，不用其他批次摘要替代产物证据。
- 交付验证：审核接口同时校验 batch ID、报告 SHA-256 与 72 题覆盖；后端隔离环境全量测试 59/59、Ruff、前端 ESLint/production build、Docker Web 重建和浏览器实际加载均通过。测试副本不含项目 `.env`，本轮未调用模型。

结论：短引用键真实批次、Reranker 配置、token 覆盖和保守成本快照已有可复核产物；旧 UUID 批次已经提供当前 MVP 所需的单人声明式人工质量记录，不要求重复评审。短键批次的人审仅是发布优化后新质量指标的可选复核。

## 2026-07-15：低置信度阈值工程校准与计时链路

- 可审计产物：[校准报告](../evals/results/fastapi-official-confidence-calibration.json)，报告 SHA-256 `d6f8f2d56d7d2e4f16b84f56d1d912d2f4ee3d17976bed6632022b95659a8c59`。
- 固定配置：9 篇 FastAPI 公开语料生成 129 个 chunk；CPU `BAAI/bge-small-zh-v1.5` + BM25 + RRF + `BAAI/bge-reranker-base`，候选 10、`top_k=5`，Reranker 未关闭。
- 标签边界：72 条支持题沿用现有单人声明式审核，24 条越界题由开发者从语料明确未覆盖的主题中声明式编写，不是独立第三方评审。
- 选择规则：阈值网格步长 `0.01`，支持题保留率不得低于 `90%`，在约束内优先提高越界拒绝率；得到 `RETRIEVAL_MIN_SCORE=0.02`。
- 实测取舍：支持题保留 `65/72 (90.3%)`，越界题拒绝 `22/24 (91.7%)`，平衡准确率 `91.0%`；文件级 Recall@5 从阈值前 `64/72 (88.9%)` 降到阈值后 `59/72 (81.9%)`。
- 输入绑定：语料聚合 SHA-256 `234fcfa8…07f7`，支持题 SHA-256 `5d75df7b…ac1`，越界题 SHA-256 `c9cd446a…d343`。报告保存 96 条逐题顶部得分与命中文件。
- 实现验证：低分候选会在模型调用前过滤，空结果走 `retrieval-guard`；RRF-only 对照不套用不同量纲的阈值。后端响应新增模型、检索和服务端全链路耗时，前端新增浏览器实际端到端耗时显示。
- 回归与运行：不含 `.env` 的隔离副本全量测试 64/64、Ruff、前端 ESLint/production build 均通过；API/Worker/Web 已用新镜像重建，API 健康且 OpenAPI 已暴露三类服务端耗时字段。本轮校准未调用 DeepSeek。

结论：低置信度规则已从“无命中才拒答”提升为有固定报告约束的 Reranker 分数守卫；严格浏览器完整请求的实测记录和演示视频仍待完成。

## 2026-07-15：FastAPI 官方语料与 AI 协助题集草案基线

- 语料：9 篇公开 FastAPI 官方教程，来源清单和 SHA-256 见 [fastapi-official-2026-07-14/source-manifest.json](../evals/corpora/fastapi-official-2026-07-14/source-manifest.json)。
- 导入：本地单账号环境中已创建明确标注“题集待人工复核”的知识库；9/9 Markdown 文档状态均为 `ready`，72/72 条草案题目已保存。
- 配置：同一知识库、同一 72 条题目、`top_k=3`；分别运行 BGE + BM25 + RRF 与启用本地 `BAAI/bge-reranker-base` 的配置。

| 配置 | Recall@3 | MRR | 平均检索耗时 | P95 检索耗时 |
| --- | ---: | ---: | ---: | ---: |
| BGE + BM25 + RRF | 0.847 | 0.743 | 65.2 ms | 79.6 ms |
| BGE + BM25 + RRF + Reranker | 0.847 | 0.819 | 1547.0 ms | 2071.7 ms |

结果文件：[fastapi-official-draft-rrf-only.json](../evals/results/fastapi-official-draft-rrf-only.json) 与 [fastapi-official-draft-reranker.json](../evals/results/fastapi-official-draft-reranker.json)。当前 CLI 的第一次检索会惰性加载本地 BGE/CrossEncoder，因此这些耗时包含冷启动，不能当作稳态用户延迟；后续正式运行应先预热并另行记录端到端延迟。

结论：公开语料导入、72 条题集读取与两套检索配置均已真实运行。Reranker 在这套**AI 协助、待人工复核**草案上改善了第一个正确来源的平均排名，但没有改善 Top-3 命中率。该题集 manifest 仍为 `needs_human_review`，正式模式已按设计拒绝运行；这些数字仅用于调试与后续人工复核，不得用于简历、公开效果结论或模型选型。
