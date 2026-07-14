# M2-A：文档接收契约

当前 API 支持创建知识库、上传 Markdown/PDF 文件并查询文档状态。

## 当前端点

- `POST /api/knowledge-bases`：创建本地单用户知识库。
- `GET /api/knowledge-bases`：列出知识库。
- `POST /api/knowledge-bases/{kb_id}/documents`：上传单个 `.md` 或 `.pdf` 文件。
- `GET /api/knowledge-bases/{kb_id}/documents`：查看该知识库的文档状态。

上传接受 `text/markdown`、`text/plain`（仅 `.md`）和 `application/pdf`，单个文件上限 10 MB。文件以 `uploads/<document_id>/<filename>` 保存；`uploads/` 被 Git 忽略。

## 状态边界

上传成功时文档只能是 `pending`：它说明文件已保存、数据库记录已建立，尚未代表内容已经解析、向量化或可检索。下一阶段的 Worker 将负责 `pending -> processing -> ready/failed` 转换。
