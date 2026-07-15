# 检索评测基线

当前项目已经提供一个可复现的离线检索评测运行器，用于比较同一知识库、同一题集和同一 `top_k` 下的检索配置。

也可以通过 API 将案例持久化到指定知识库：

- `POST /api/knowledge-bases/{kb_id}/evaluation-cases`：保存问题、预期来源文件名和可选参考答案。
- `GET /api/knowledge-bases/{kb_id}/evaluation-cases`：查看该知识库已积累的案例。
- `DELETE /api/knowledge-bases/{kb_id}/evaluation-cases/{case_id}`：删除误录或过期案例。
- `POST /api/knowledge-bases/{kb_id}/evaluations/retrieval?top_k=5`：使用这些案例运行当前检索基线。

API 返回的指标与下方 CLI 一致；它不会调用模型，因此只统计检索延迟。

前端工作台也提供同一组 API 的最小操作入口：选择知识库后，填写问题和预期命中的文件名即可保存案例；一个案例允许用中文或英文逗号填写多个预期文件名。最近案例可删除，再点击“运行评测”查看结果。页面上的小样本结果只用于回归检查，不能当作真实效果结论。

## 答案与引用人工评审

检索命中不等于最终答案正确。工作台支持从一条**已完成的证据问答**中捕获回答、模型名、耗时和服务端已校验的 chunk ID，再由评审者手动标注：

- 答案是否符合参考资料或预期回答；
- 引用是否足以支持答案；
- 在证据不足时，拒答是否恰当；
- 可选的错误类型或改进备注。

保存评审不会再次调用模型，也不会产生 API 费用。回答快照和人工 verdict 按评测案例持久化，因此可以比较后续不同模型或检索配置下的多个回答。汇总接口返回已评审数量、未覆盖案例数，以及每个有适用样本的人工通过率；`not_applicable` 不会进入对应分母。

若已获得模型调用授权，可用批处理器对固定 JSONL 生成一次真实证据问答批次和一张待填写的答案审核表。它会记录成功模型调用的 token/耗时元数据，但不自动判断回答或引用正确性：

```bash
uv run python -m app.evaluation.answer_batch \
  --knowledge-base-id <知识库 UUID> \
  --cases ../../evals/independent/cases.jsonl \
  --output ../../evals/results/formal-answer-batch.json \
  --review-output ../../evals/independent/formal-answer-review.csv \
  --top-k 5
```

输出 JSON 会保存公开题集的问题、模型回答及服务端已校验引用，供评审者复核，并记录检索配置快照；CSV 的答案、引用和拒答 verdict 初始均为 `pending`。运行前应确认本地 API Key 与当日成本单价配置正确，运行后由人工填写评审结论。

若审核表需要从已保存的批次结果重新生成（不调用模型、不会产生费用），可运行：

```bash
uv run python -m app.evaluation.answer_review \
  --report ../../evals/results/formal-answer-batch.json \
  --review ../../evals/independent/formal-answer-review.csv \
  --initialize
```

评审者需要逐行核对回答与引用片段：`answered` 行必须填写答案与引用的 `pass` / `fail`，拒答为 `not_applicable`；`retrieval_guard_*` 行必须填写拒答的 `pass` / `fail`，答案和引用为 `not_applicable`；`provider_error` / `retrieval_error` 三项均为 `not_applicable`。填写 `approved`、`review_method`、评审别名和 UTC 时间后，用同一工具去掉 `--initialize` 校验审核表与该批次报告逐字段一致，并输出可复核的 SHA-256 与通过率。`review_method` 必须如实填写：真实逐题人工判断才可填 `human`；由 DeepSeek、ChatGPT 或其他模型判分只能填 `model_assisted`。后者可作为调试信号，但不能宣称人工评审、独立人工评审或简历质量指标。校验工具同样不能证明评审者身份或独立性，项目记录必须如实说明评审过程。

旧版审核表没有 `review_method` 列时，不应手工改动模型回答、引用、模型名或耗时来“修正” CSV。可先保留原文件，再生成独立的模型辅助版；迁移器只取每行末尾的 verdict/备注，并从不可变批次报告恢复其他字段：

```bash
uv run python -m app.evaluation.answer_review \
  --report ../../evals/results/formal-answer-batch.json \
  --review ../../evals/independent/legacy-answer-review.csv \
  --migrate-legacy-model-assisted \
  --output ../../evals/independent/formal-answer-review-model-assisted.csv
```

输出会明确标为 `model_assisted`；它可以帮助发现检索或引用问题，但验证结果会返回 `is_human_review: false`，不得用于替代真实人工审核。

### 72 条正式题集的点选审核页

本地 Docker Web 启动后，打开 `http://localhost:3000/review`，或从工作台顶部进入“72 题真人审核”。页面只加载 batch ID `02dbf511…`、报告 SHA-256 `0050e4ed…55fef` 的短引用键固定批次；服务端会同时校验 batch ID、哈希与 72 题覆盖，任一不符即停止加载以避免串批。回答题分别点答案/引用通过或不通过，守卫拒答题只点拒答合理或不当；进度和备注仅保存在当前浏览器的批次专属本地草稿中，不会把判断发送给模型或写进后端数据库。

完成全部 72 条可评审案例并填写评审别名后，点击“下载真人审核 CSV”。导出的文件已经包含 `review_method=human`、每行 verdict 与固定批次内容；将下载文件保存为 `evals/independent/fastapi-official-formal-answer-compact-s1-02dbf511-review-human.csv` 后，运行：

```bash
cd apps/api
uv run python -m app.evaluation.answer_review \
  --report ../../evals/results/fastapi-official-formal-answer-compact-s1-20260715.json \
  --review ../../evals/independent/fastapi-official-formal-answer-compact-s1-02dbf511-review-human.csv
```

该校验不调用模型。页面也不会替使用者决定 verdict；若由模型辅助判断，应改用 `model_assisted`，不能把导出的 `human` 标签当作事实。

## 模型调用元数据

从 M4 起，每次成功完成的知识库证据问答都会记录模型名、模型调用耗时和供应商返回的 token 用量（若返回）。记录中**不保存**问题、回答、对话历史、来源片段或 API Key。可通过以下接口按知识库查看累计调用数、已报告 token 的调用数、token 总量和延迟分位数：

```text
GET /api/knowledge-bases/{knowledge_base_id}/evaluations/model-usage-summary
```

这是成本和延迟评测的观测基础，不包含检索耗时，也不会把模型未返回 token 的调用估算成 token 或费用。若要计算单次成本，先在本地 `.env` 同时设置当次模型适用的 `DEEPSEEK_INPUT_COST_PER_MILLION_TOKENS`、`DEEPSEEK_OUTPUT_COST_PER_MILLION_TOKENS` 和可选的 `DEEPSEEK_COST_CURRENCY`。系统会把单价和估算成本写入**该次**模型调用记录，避免日后价格变化回写历史；未配置单价和历史记录会显示为未估算。

价格应在正式运行当天从供应商价格页人工核对，并在评测报告中写明模型、币种、输入/输出单价与生效时间。汇总只在所有可估算调用使用同一币种时返回总成本和平均单次成本；它仍不等同于质量结论。

这不是自动判分器。只有来自独立问题、独立人工标注，并写明样本量和评审规则的结果，才能作为项目效果证据；项目验收文档演示题集不得使用这些指标。

## 题集格式

题集是 UTF-8 JSONL：每一行一个案例，最少填写唯一 ID、问题和至少一个预期来源文件名。模板见 [../evals/template.jsonl](../evals/template.jsonl)。

```json
{"id":"release-001","question":"发布流程在哪里？","expected_filenames":["team-handbook.md"]}
```

当前按文件名判断命中，便于在文档重新分块后保持评测稳定。一个案例可包含多个允许来源文件名。

仓库还提供 [../evals/smoke.jsonl](../evals/smoke.jsonl) 作为一条本地链路烟雾测试；它不能用于对外宣称检索效果。

## 运行

先启动 PostgreSQL 与 Qdrant，确保目标知识库的文件已经为 `ready`。在 `apps/api` 下运行：

```bash
uv run python -m app.evaluation.runner \
  --knowledge-base-id <知识库 UUID> \
  --cases ../../evals/my-cases.jsonl \
  --top-k 5 \
  --output ../../evals/results/baseline.json
```

对比重排序前后时，先运行默认配置（`reranker_enabled=true`），再添加
`--disable-reranker` 运行 RRF-only 基线，并保存为不同结果文件：

```bash
uv run python -m app.evaluation.runner \
  --knowledge-base-id <知识库 UUID> \
  --cases ../../evals/my-cases.jsonl \
  --top-k 5 \
  --disable-reranker \
  --output ../../evals/results/rrf-only.json
```

本地 BGE/CrossEncoder 首次调用会加载模型。若报告需要比较稳态检索延迟，可对两个配置使用相同的预热数量；预热查询会执行检索但**不进入** Recall、MRR 和延迟统计，输出的 `run_metadata.warmup_queries_excluded` 会记录该数量：

```bash
uv run python -m app.evaluation.runner \
  --knowledge-base-id <知识库 UUID> \
  --cases ../../evals/my-cases.jsonl \
  --top-k 5 \
  --warmup-queries 3 \
  --output ../../evals/results/warm-reranker.json
```

## 正式独立题集模式

仓库的 [../evals/independent/](../evals/independent/) 只提供 JSONL 和来源说明模板，**不是题集本身**。完成独立题集和人工来源标注后，复制模板为未提交或已脱敏的实际文件，并使用 `--formal-manifest` 运行：

```bash
uv run python -m app.evaluation.runner \
  --knowledge-base-id <知识库 UUID> \
  --cases ../../evals/independent/cases.jsonl \
  --formal-manifest ../../evals/independent/manifest.json \
  --top-k 5 \
  --output ../../evals/results/formal-reranker.json
```

正式模式会拒绝少于 60 或多于 100 条的题集、重复案例 ID、重复问题，以及缺少 `dataset_origin: "independent"`、来源说明、`human_review_status: "approved"` 和完整审核表的 manifest。输出会附加题集、manifest 与审核表的 SHA-256，便于在答辩或简历复核时证明报告使用了哪一版数据；它不能自动证明题目真的独立，题目来源和人工标注方法仍必须如实填写。

先从 JSONL 生成 CSV 审核表：

```bash
cd apps/api
uv run python -m app.evaluation.review_sheet \
  --cases ../../evals/independent/cases.jsonl \
  --output ../../evals/independent/case-review.csv
```

由与题集生成者独立的人工评审者逐行核对问题、参考答案和预期来源，并填写 `approved` / `pass`、评审别名和 UTC 时间。审核表是声明式审计证据，不会、也不能自动证明评审者的真实身份；使用者必须如实保留评审过程。每个题目恰好一行且所有 verdict 通过后，才可将 manifest 的 `human_review_status` 改为 `approved`。正式报告会记录审核表 SHA-256、覆盖案例数和评审别名数量。

`fastapi-official-cases.jsonl` 是基于公开 FastAPI 官方文档建立的 72 条中文 AI 协助题目。其问题、参考答案和预期来源已按 `fastapi-official-review.csv` 完成声明式独立人工逐题复核，因此可进入正式**检索**评测。固定真实模型批次的答案审核已保存在 `fastapi-official-formal-answer-review-human.csv`，并通过完整性校验；该表是单人声明式人工审核，不应夸大为独立多评审结论。旧版 `fastapi-official-formal-answer-review.csv` 保留为原始待审核文件，不作为结果证据。

## 公开 FastAPI 语料导入

仓库已提交 9 篇 FastAPI 官方公开教程及其来源哈希，位于 [../evals/corpora/fastapi-official-2026-07-14/](../evals/corpora/fastapi-official-2026-07-14/)。在 Docker 环境只有一个本地账号时，以下命令会创建一个明确标为“题集待人工复核”的知识库，导入文档并同步处理，同时导入 72 条评测草案：

```bash
docker compose exec api uv run --no-sync python -m app.public_fastapi_seed
```

命令不会读取账号邮箱、不会删除既有数据；如果本机有多个账号会停止，避免把语料写进错误账户。重复运行只补充缺失文件或题目。

2026-07-15 的首次草案基线结果保存于 [../evals/results/fastapi-official-draft-rrf-only.json](../evals/results/fastapi-official-draft-rrf-only.json) 与 [../evals/results/fastapi-official-draft-reranker.json](../evals/results/fastapi-official-draft-reranker.json)，仅保留为人工复核前的调试记录。已审核后的正式预热检索报告见 [../evals/results/fastapi-official-formal-warm-rrf-only.json](../evals/results/fastapi-official-formal-warm-rrf-only.json) 与 [../evals/results/fastapi-official-formal-warm-reranker.json](../evals/results/fastapi-official-formal-warm-reranker.json)；完整限制见 [verification.md](verification.md)。

CLI 结果会记录 `reranker_enabled`，以及不含密钥的 `run_metadata`（运行 UTC 时间、Embedding 模型/维度/设备、Qdrant collection 与启用时的 Reranker 配置），使两个报告的配置可追溯。

## 仅演示题集

仓库中的 [../evals/demo-acceptance.jsonl](../evals/demo-acceptance.jsonl) 由项目自身的验收文档人工编写，目的是验证多文档检索、RRF-only 与 Reranker 对比流程。它不是独立用户问题，**不得**用于简历或公开效果结论。

可在本地创建对应的演示知识库后运行：

```bash
cd apps/api
uv run python -m app.demo_seed
```

命令会创建名为“验收演示知识库（非简历指标）”的本地资料库，重复执行不会重复创建。使用命令输出的知识库 UUID 运行本节的评测 CLI。

运行器输出：

- `recall_at_k`：至少一个预期来源出现在 Top-K 的案例比例。
- `mean_reciprocal_rank`：第一个正确来源排名的倒数均值。
- `mean_latency_ms` / `p95_latency_ms`：仅覆盖本地检索调用的延迟，不包含模型生成。

## 当前边界

该运行器评估的是**检索**而非最终答案正确性。引用正确率、拒答正确率、模型生成延迟和成本需要在后续的答案级评测中单独记录。只有积累真实题集并运行后，才可以在 README 或简历填写真实指标。
