"use client";

import { ChangeEvent, FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  ChatApiError,
  Citation,
  DocumentRecord,
  KnowledgeBase,
  createKnowledgeBase,
  getApiHealth,
  getDocuments,
  getKnowledgeBases,
  sendChatMessage,
  uploadDocument,
} from "../lib/chat";

type Message = {
  id: number;
  role: "user" | "assistant";
  content: string;
  model?: string;
  latencyMs?: number;
  citations?: Citation[];
};

type ApiStatus = "checking" | "connected" | "disconnected";

const examples = ["上传文档后处于什么状态？", "如何判断回答是否有依据？"];
const apiStatusLabel: Record<ApiStatus, string> = {
  checking: "正在检查 API",
  connected: "API 已连接",
  disconnected: "API 未连接",
};

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [isCreatingKnowledgeBase, setIsCreatingKnowledgeBase] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [apiStatus, setApiStatus] = useState<ApiStatus>("checking");
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [selectedKnowledgeBaseId, setSelectedKnowledgeBaseId] = useState("");
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [newKnowledgeBaseName, setNewKnowledgeBaseName] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const selectedKnowledgeBase = knowledgeBases.find(
    (knowledgeBase) => knowledgeBase.id === selectedKnowledgeBaseId,
  );
  const latestCitations = useMemo(
    () => [...messages].reverse().find((message) => message.role === "assistant")?.citations ?? [],
    [messages],
  );
  const hasPendingDocuments = documents.some(
    (document) => document.status === "pending" || document.status === "processing",
  );

  const loadDocuments = useCallback(async (knowledgeBaseId: string) => {
    try {
      setDocuments(await getDocuments(knowledgeBaseId));
    } catch (loadError) {
      setError(loadError instanceof ChatApiError ? loadError.message : "无法读取文档状态。");
    }
  }, []);

  useEffect(() => {
    let isActive = true;

    async function initializeKnowledgeBases() {
      try {
        const bases = await getKnowledgeBases();
        if (!isActive) return;
        setKnowledgeBases(bases);
        setSelectedKnowledgeBaseId(bases[0]?.id ?? "");
      } catch (loadError) {
        if (!isActive) return;
        setError(loadError instanceof ChatApiError ? loadError.message : "无法加载知识库。");
      }
    }

    void getApiHealth()
      .then(() => {
        if (isActive) setApiStatus("connected");
      })
      .catch(() => {
        if (isActive) setApiStatus("disconnected");
      });
    void initializeKnowledgeBases();

    return () => {
      isActive = false;
    };
  }, []);

  useEffect(() => {
    if (!selectedKnowledgeBaseId) {
      return;
    }

    async function refreshDocuments() {
      await loadDocuments(selectedKnowledgeBaseId);
    }

    void refreshDocuments();
  }, [loadDocuments, selectedKnowledgeBaseId]);

  useEffect(() => {
    if (!selectedKnowledgeBaseId || !hasPendingDocuments) return;
    const timer = window.setInterval(() => void loadDocuments(selectedKnowledgeBaseId), 3_000);
    return () => window.clearInterval(timer);
  }, [hasPendingDocuments, loadDocuments, selectedKnowledgeBaseId]);

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
      const result = await sendChatMessage(message, selectedKnowledgeBaseId || undefined);
      setMessages((current) => [
        ...current,
        {
          id: Date.now() + 1,
          role: "assistant",
          content: result.answer,
          model: result.model,
          latencyMs: result.latency_ms,
          citations: result.citations,
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

  async function submitKnowledgeBase(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const name = newKnowledgeBaseName.trim();
    if (!name || isCreatingKnowledgeBase) return;

    setIsCreatingKnowledgeBase(true);
    setError(null);
    try {
      const knowledgeBase = await createKnowledgeBase(name);
      setKnowledgeBases((current) => [knowledgeBase, ...current]);
      setSelectedKnowledgeBaseId(knowledgeBase.id);
      setNewKnowledgeBaseName("");
    } catch (requestError) {
      setError(requestError instanceof ChatApiError ? requestError.message : "无法创建知识库。");
    } finally {
      setIsCreatingKnowledgeBase(false);
    }
  }

  async function handleUpload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file || !selectedKnowledgeBaseId || isUploading) return;

    setIsUploading(true);
    setError(null);
    try {
      await uploadDocument(selectedKnowledgeBaseId, file);
      await loadDocuments(selectedKnowledgeBaseId);
    } catch (requestError) {
      setError(requestError instanceof ChatApiError ? requestError.message : "无法上传文档。");
    } finally {
      setIsUploading(false);
    }
  }

  const scopeLabel = selectedKnowledgeBase ? "当前：证据问答" : "当前：直接模型调用";

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
            <span className="scope-badge">{scopeLabel}</span>
          </div>

          <section className="knowledge-context" aria-label="当前知识库">
            <label htmlFor="knowledge-base">知识库</label>
            <select
              id="knowledge-base"
              value={selectedKnowledgeBaseId}
              onChange={(event) => {
                setDocuments([]);
                setSelectedKnowledgeBaseId(event.target.value);
              }}
            >
              <option value="">不使用知识库（直接模型调用）</option>
              {knowledgeBases.map((knowledgeBase) => (
                <option key={knowledgeBase.id} value={knowledgeBase.id}>
                  {knowledgeBase.name}
                </option>
              ))}
            </select>
            {selectedKnowledgeBase && (
              <span className="document-count">
                {documents.filter((document) => document.status === "ready").length} 个可检索文档
              </span>
            )}
          </section>

          <div className="conversation" aria-live="polite">
            {messages.length === 0 ? (
              <div className="empty-state">
                <p className="empty-kicker">第 3 周里程碑</p>
                <h2>{selectedKnowledgeBase ? "基于当前资料回答，并展示证据。" : "选择知识库后开始证据问答。"}</h2>
                <p>
                  {selectedKnowledgeBase
                    ? "系统只会使用已完成处理的文档。没有检索到证据时，后端会拒答而不是编造。"
                    : "未选择知识库时仍是直接模型调用，不会伪造来源。"}
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
                      {message.citations && <span>{message.citations.length} 条已校验证据</span>}
                    </div>
                  )}
                </article>
              ))
            )}
            {isSending && <p className="sending">正在检索证据并请求回答…</p>}
          </div>

          <form className="composer" onSubmit={submitMessage}>
            <label className="sr-only" htmlFor="message">
              输入问题
            </label>
            <textarea
              id="message"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder={selectedKnowledgeBase ? "基于当前知识库提问…" : "输入问题，直接请求模型…"}
              rows={3}
              disabled={isSending}
            />
            <div className="composer-footer">
              <span>{selectedKnowledgeBase ? "只展示服务端校验过的证据" : "未选择知识库：直接模型调用"}</span>
              <button type="submit" disabled={!draft.trim() || isSending}>
                {isSending ? "发送中" : "发送"}
              </button>
            </div>
          </form>
          {error && <p className="error" role="alert">{error}</p>}
        </div>

        <aside className="evidence-panel" aria-label="知识库与证据检查面板">
          <p className="eyebrow">KNOWLEDGE BASE</p>
          <h2>资料与证据</h2>

          <form className="create-knowledge-base" onSubmit={submitKnowledgeBase}>
            <label className="sr-only" htmlFor="knowledge-base-name">
              新知识库名称
            </label>
            <input
              id="knowledge-base-name"
              value={newKnowledgeBaseName}
              onChange={(event) => setNewKnowledgeBaseName(event.target.value)}
              placeholder="新知识库名称"
              maxLength={120}
            />
            <button type="submit" disabled={!newKnowledgeBaseName.trim() || isCreatingKnowledgeBase}>
              {isCreatingKnowledgeBase ? "创建中" : "新建"}
            </button>
          </form>

          <section className="document-section" aria-label="文档处理状态">
            <div className="section-heading">
              <h3>{selectedKnowledgeBase?.name ?? "尚未选择知识库"}</h3>
              <button
                type="button"
                className="text-button"
                disabled={!selectedKnowledgeBase || isUploading}
                onClick={() => fileInputRef.current?.click()}
              >
                {isUploading ? "上传中" : "上传资料"}
              </button>
            </div>
            <input
              ref={fileInputRef}
              className="sr-only"
              type="file"
              accept=".md,.pdf,.docx,text/markdown,text/plain,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
              onChange={handleUpload}
            />
            {selectedKnowledgeBase ? (
              documents.length ? (
                <ul className="document-list">
                  {documents.slice(0, 5).map((document) => (
                    <li key={document.id}>
                      <span className="document-name">{document.filename}</span>
                      <span className={`document-status ${document.status}`}>{document.status}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="panel-empty">上传 Markdown 或 PDF 后，Worker 会在此更新处理状态。</p>
              )
            ) : (
              <p className="panel-empty">新建或选择知识库后即可上传资料并启用证据问答。</p>
            )}
          </section>

          <section className="evidence-section" aria-label="来源证据">
            <p className="eyebrow">EVIDENCE INSPECTOR</p>
            <h3>来源证据</h3>
            {latestCitations.length ? (
              <ol className="citation-list">
                {latestCitations.map((citation) => (
                  <li key={citation.chunk_id}>
                    <p className="citation-title">
                      {citation.filename}
                      {citation.page_number ? ` · 第 ${citation.page_number} 页` : ` · 片段 ${citation.chunk_index + 1}`}
                    </p>
                    <p>{citation.content}</p>
                  </li>
                ))}
              </ol>
            ) : (
              <div className="evidence-empty">
                <span className="evidence-icon" aria-hidden="true">⌁</span>
                <h3>尚无已校验证据</h3>
                <p>选择知识库并完成一次证据问答后，这里只显示服务端验证过的来源片段。</p>
              </div>
            )}
          </section>

          <div className="contract">
            <p>证据契约</p>
            <ul>
              <li>来源必须来自当前知识库</li>
              <li>模型引用必须属于本次检索结果</li>
              <li>证据不足时明确拒答</li>
            </ul>
          </div>
        </aside>
      </section>
    </main>
  );
}
