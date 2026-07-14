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

CLI 结果会记录 `reranker_enabled`，使两个报告的配置可追溯。

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
