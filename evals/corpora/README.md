# 公开评测语料

`fastapi-official-2026-07-14/` 由 `scripts/fetch_official_fastapi_corpus.py` 从 FastAPI 官方 GitHub 仓库的官方教程路径下载。每次下载都会生成来源 URL、时间、字节数和 SHA-256 的 `source-manifest.json`；评测应以已提交版本的哈希为准，不能假定日后重新下载的分支内容完全相同。

该语料用于本地 RAG 工程和独立题集验证；内容版权仍归 FastAPI 项目所有。它与本仓库的验收演示文档分离。

仓库附带的 `../independent/fastapi-official-cases.jsonl` 是 72 条中文 **AI 协助草案**，不是已完成的人工题集；每条问题、标准答案和预期来源都需要独立人工复核后，才可将 manifest 的 `human_review_status` 改为 `approved` 并用于正式评测或简历结论。
