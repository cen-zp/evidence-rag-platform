"use client";

import { FormEvent, useEffect, useState } from "react";

import { ChatApiError, getApiHealth, sendChatMessage } from "../lib/chat";

type Message = {
  id: number;
  role: "user" | "assistant";
  content: string;
  model?: string;
  latencyMs?: number;
};

const examples = ["这个项目的核心目标是什么？", "如何判断回答是否有依据？"];
type ApiStatus = "checking" | "connected" | "disconnected";

const apiStatusLabel: Record<ApiStatus, string> = {
  checking: "正在检查 API",
  connected: "API 已连接",
  disconnected: "API 未连接",
};

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [apiStatus, setApiStatus] = useState<ApiStatus>("checking");

  useEffect(() => {
    let isActive = true;

    void getApiHealth()
      .then(() => {
        if (isActive) setApiStatus("connected");
      })
      .catch(() => {
        if (isActive) setApiStatus("disconnected");
      });

    return () => {
      isActive = false;
    };
  }, []);

  async function submitMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const message = draft.trim();
    if (!message || isSending) return;

    const userMessage: Message = { id: Date.now(), role: "user", content: message };
    setMessages((current) => [...current, userMessage]);
    setDraft("");
    setError(null);
    setIsSending(true);

    try {
      const result = await sendChatMessage(message);
      setMessages((current) => [
        ...current,
        {
          id: Date.now() + 1,
          role: "assistant",
          content: result.answer,
          model: result.model,
          latencyMs: result.latency_ms,
        },
      ]);
    } catch (requestError) {
      setError(
        requestError instanceof ChatApiError
          ? requestError.message
          : "发生了未知错误，请稍后重试。",
      );
    } finally {
      setIsSending(false);
    }
  }

  return (
    <main className="workbench">
      <header className="topbar">
        <a className="brand" href="#chat" aria-label="Evidence RAG 首页">
          <span className="brand-mark">E</span>
          <span>Evidence RAG</span>
        </a>
        <div className="status" aria-label={apiStatusLabel[apiStatus]}>
          <span className={`status-dot ${apiStatus}`} />
          {apiStatusLabel[apiStatus]}
        </div>
      </header>

      <section className="workspace" aria-label="知识库问答工作台">
        <div className="chat-panel" id="chat">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">CONVERSATION</p>
              <h1>问答工作台</h1>
            </div>
            <span className="scope-badge">当前：直接模型调用</span>
          </div>

          <div className="conversation" aria-live="polite">
            {messages.length === 0 ? (
              <div className="empty-state">
                <p className="empty-kicker">第 1 周里程碑</p>
                <h2>先验证模型调用，再接入检索证据。</h2>
                <p>
                  这里暂时直接请求后端的聊天接口。文档上传、检索和可追溯引用会在后续里程碑接入；现在不会伪造来源。
                </p>
                <div className="example-list">
                  {examples.map((example) => (
                    <button key={example} type="button" onClick={() => setDraft(example)}>
                      {example}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              messages.map((message) => (
                <article className={`message ${message.role}`} key={message.id}>
                  <p className="message-role">{message.role === "user" ? "你" : "模型回答"}</p>
                  <p className="message-content">{message.content}</p>
                  {message.role === "assistant" && (
                    <div className="message-meta">
                      <span>{message.model}</span>
                      <span>{message.latencyMs} ms</span>
                    </div>
                  )}
                </article>
              ))
            )}
            {isSending && <p className="sending">正在向 API 请求回答…</p>}
          </div>

          <form className="composer" onSubmit={submitMessage}>
            <label className="sr-only" htmlFor="message">
              输入问题
            </label>
            <textarea
              id="message"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder="输入一个问题，验证后端模型调用…"
              rows={3}
              disabled={isSending}
            />
            <div className="composer-footer">
              <span>Enter 换行 · 点击发送</span>
              <button type="submit" disabled={!draft.trim() || isSending}>
                {isSending ? "发送中" : "发送"}
              </button>
            </div>
          </form>
          {error && <p className="error" role="alert">{error}</p>}
        </div>

        <aside className="evidence-panel" aria-label="证据检查面板">
          <p className="eyebrow">EVIDENCE INSPECTOR</p>
          <h2>来源证据</h2>
          <div className="evidence-empty">
            <span className="evidence-icon" aria-hidden="true">⌁</span>
            <h3>尚未接入检索链路</h3>
            <p>
              目前接口只返回模型回答、模型名称与耗时。完成文档入库后，这里将只展示服务端校验过的原文片段与位置。
            </p>
          </div>
          <div className="contract">
            <p>证据契约</p>
            <ul>
              <li>来源必须来自当前知识库</li>
              <li>回答与来源编号一一对应</li>
              <li>证据不足时明确拒答</li>
            </ul>
          </div>
        </aside>
      </section>
    </main>
  );
}
