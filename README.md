# Evidence RAG Platform

一个面向团队内部资料的可评测知识库问答平台。用户上传资料后，系统基于可追溯的证据回答问题；当证据不足时，明确拒答而不是编造答案。

## 项目目标

这是一个用于求职展示的全栈 AI 应用项目。重点不在“接入聊天模型”，而在于完成可解释检索、效果评测、工程化交付与成本/延迟取舍。

## MVP 范围

- 上传并解析 PDF、DOCX、Markdown 文件
- 异步分块、向量化并写入知识库
- 支持多轮问答，并在回答中展示可点击的来源片段
- 基于语义检索、关键词检索与重排序生成上下文
- 无证据或低置信度时拒答
- 显示本次请求的耗时、模型调用和基础日志
- 以 Docker Compose 在本地一键启动

## 技术栈

| 层级 | 选择 |
| --- | --- |
| Web | Next.js、TypeScript、Tailwind CSS |
| API | Python、FastAPI、Pydantic、SQLAlchemy、Alembic |
| 数据 | PostgreSQL、Redis、Qdrant |
| 异步任务 | ARQ（Redis 队列） |
| AI | DeepSeek API（OpenAI 兼容 SDK）、Embedding、结构化输出 |
| 检索 | Dense + BM25 混合检索、RRF、Rerank |
| 质量 | pytest、评测集、Langfuse（第二阶段） |
| 交付 | Docker Compose、GitHub Actions |

详细规格见 [docs/PRD.md](docs/PRD.md) 与 [docs/week-1-plan.md](docs/week-1-plan.md)。

## 本地密钥配置

1. 将 `.env.example` 复制为项目根目录的 `.env`。
2. 在 `.env` 中填写新生成的 `DEEPSEEK_API_KEY`；不要将 `.env` 提交到 Git，也不要在聊天中发送密钥。
3. 后端通过 OpenAI 兼容 SDK 调用 `https://api.deepseek.com`；默认聊天模型为 `deepseek-v4-flash`。

## 基础设施（Docker Compose）

当前 Compose 负责启动 PostgreSQL、Redis 和 Qdrant；API、Web 和后续 Worker 仍在本地进程中运行。首次启动并等待健康检查：

```bash
docker compose up -d --wait
docker compose ps
```

停止基础设施但保留数据卷：

```bash
docker compose down
```

## 前端聊天界面（当前里程碑）

`apps/web` 是一个 Next.js 聊天工作台：它调用 `POST /api/chat`，显示真实的模型名和后端测得的响应耗时。文档检索与引用尚未接入时，页面会明确标示为“直接模型调用”，不会模拟来源证据。

```bash
# Terminal 1: start the API
cd apps/api
uv run python -m uvicorn app.main:app --reload --port 8000

# Terminal 2: start the web app
cd apps/web
cp .env.local.example .env.local
pnpm install
pnpm dev
```

在浏览器打开 `http://localhost:3000`。前端只读取 `NEXT_PUBLIC_API_BASE_URL`；DeepSeek 密钥仍只允许放在项目根目录的 `.env`。

页面顶部会请求 `GET /health` 显示 API 已连接或未连接；它只表示 API 服务可达，不表示模型密钥已经配置成功。

## 当前数据层里程碑

后端已定义 `KnowledgeBase`、`Document`、`DocumentChunk` 最小数据模型和 Alembic 初始迁移。当前仍是本地单用户模式；尚未实现文件上传、解析、Embedding 或检索。数据隔离与 PostgreSQL/Qdrant ID 规则见 [docs/data-model.md](docs/data-model.md)。
