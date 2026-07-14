# 第 1 周：项目基础与最小可运行链路

本周投入 35 小时。目标不是学完所有框架，而是建立可持续开发的工程骨架，并跑通“网页 -> 后端 -> 模型 API -> 网页”的最小链路。

## 每日安排

### Day 1（5 小时）：仓库与开发环境

- 创建 GitHub 仓库 `evidence-rag-platform`（先保持私有也可以）
- 初始化 monorepo 目录：`apps/web`、`apps/api`、`infra`、`docs`
- 安装并验证 Python、Node.js、Docker、Git
- 配置 `.gitignore` 与 `.env.example`；确认密钥不会进入 Git
- 完成一次有意义的初始提交：`chore: initialize project structure`

**验收：** 新电脑按 README 能知道项目如何启动；仓库中不含 API Key。

### Day 2（5 小时）：FastAPI 最小后端

- 建立 FastAPI 服务与 `/health` 接口
- 了解请求/响应模型，定义 `ChatRequest`、`ChatResponse`
- 配置 CORS、环境变量读取、统一错误格式
- 写第一个 pytest：健康检查返回成功

**验收：** 浏览器或 curl 请求 `/health` 得到健康状态；测试通过。

### Day 3（5 小时）：Next.js 最小前端

- 创建 TypeScript 前端工程
- 制作简单的聊天输入和消息列表界面
- 调用后端 `/health` 并显示连接状态
- 处理 loading 与错误状态

**验收：** 前端能明确显示“后端已连接/未连接”。

### Day 4（5 小时）：模型 API 最小闭环

- 在后端接入 DeepSeek API，不在浏览器中暴露密钥
- 实现 `/api/chat`，先用固定系统提示词返回纯文本
- 前端调用该接口并展示消息
- 记录请求耗时、输入/输出 token（若 API 返回）

**验收：** 从网页提问能获得模型回复；密钥仍只存在服务端。

### Day 5（5 小时）：Docker 与数据服务

- 用 Docker Compose 启动 PostgreSQL、Redis、Qdrant
- 为每个服务设置健康检查和本地端口
- 阅读并记录三类存储各自负责什么
- 将启动步骤写入 README

**验收：** `docker compose up` 后三项基础服务健康；API 仍可运行。

### Day 6（5 小时）：数据与代码质量

- 用 SQLAlchemy 建立最小 User、KnowledgeBase、Document 模型
- 使用 Alembic 生成第一份迁移
- 添加 ruff 格式/静态检查和 pytest
- 练习将一个小功能用独立分支和 PR 合并

**验收：** 迁移可在空数据库执行；检查与测试可重复通过。

### Day 7（5 小时）：复盘与下周准备

- 整理本周所有提交，补齐 README
- 录制 30–60 秒演示：前端调用后端并得到模型回复
- 写一篇 `docs/week-1-retrospective.md`：完成项、问题、下周调整
- 建立 10 个真实问题，作为未来评测集的种子

**验收：** 能在 3 分钟内向别人演示项目骨架和解释各服务职责。

## 推荐目录

```text
evidence-rag-platform/
├── apps/
│   ├── api/                 # FastAPI 服务
│   │   ├── app/
│   │   │   ├── api/         # 路由
│   │   │   ├── core/        # 配置、日志、安全
│   │   │   ├── models/      # 数据库模型
│   │   │   ├── schemas/     # Pydantic 请求/响应模型
│   │   │   ├── services/    # LLM、检索、文档服务
│   │   │   └── workers/     # ARQ 异步任务
│   │   │
│   │   └── tests/
│   └── web/                 # Next.js 前端
├── docs/                    # 设计、评测、复盘
├── infra/                   # Docker、部署配置
├── docker-compose.yml
├── .env.example
└── README.md
```

## 本周学习边界

- 只学习当前任务所需的 FastAPI、TypeScript、Docker 和 API 调用。
- 不在本周引入 LangGraph、Rerank、认证、文件解析、向量数据库写入。
- 碰到不懂的概念，先记录问题并实现最小版本；下周按项目需要补足。
