# 持久化会话与反馈

已选知识库的证据问答会创建或续接服务端会话。后续请求携带 `conversation_id` 后，API 从该会话读取最近 6 条已持久化消息作为模型上下文；不会把浏览器传入的历史当作会话事实。

每个会话都绑定知识库和账户，所有读取、续接、耗时上报与反馈操作都会同时校验两者。数据库保存用户提问、回答、服务端校验后的引用快照、模型名、模型耗时、检索耗时和服务端处理耗时；模型调用 token 仍单独保存在不含正文的 `model_calls` 表。

工作台会显示当前知识库最近的会话标题，可加载已保存消息继续追问。新完成的知识库回答会返回 `assistant_message_id`，前端据此调用反馈接口；直接模型调用不会创建会话或显示反馈控件。

反馈接口：

```text
POST /api/knowledge-bases/{knowledge_base_id}/conversations/{conversation_id}/messages/{message_id}/feedback
```

请求体的 `rating` 只能为 `1`（有帮助）或 `-1`（无帮助），可带最多 2000 字的备注。每条回答只保留一份反馈，重复提交会覆盖之前的反馈。

浏览器在收到并解析 SSE 最终结果后，会把本地单调时钟测得的端到端耗时写回同一条助手消息：

```text
POST /api/knowledge-bases/{knowledge_base_id}/conversations/{conversation_id}/messages/{message_id}/browser-latency
```

知识库级汇总接口分别统计检索、服务端处理和浏览器端到端耗时的样本量、均值与 P95，并区分正常回答和守卫拒答：

```text
GET /api/knowledge-bases/{knowledge_base_id}/evaluations/end-to-end-latency-summary
```

旧消息没有新增字段，汇总不会用模型耗时替代缺失的浏览器耗时。浏览器上报是本地客户端观测值，不是供应商计费时长；正式报告应同时写明样本量、回答/拒答构成和运行环境。

直接模型调用不会创建持久化会话或伪造引用。会话与反馈功能必须在账户迁移完成后使用。
