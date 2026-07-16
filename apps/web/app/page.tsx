"use client";

import { ChangeEvent, FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  AuthSession,
  ChatApiError,
  ChatHistoryMessage,
  Citation,
  Conversation,
  DocumentRecord,
  KnowledgeBase,
  createKnowledgeBase,
  deleteKnowledgeBase,
  getApiHealth,
  getConversationMessages,
  getConversations,
  getDocuments,
  getKnowledgeBases,
  getStoredSession,
  login,
  logout,
  retryDocument,
  register,
  saveSession,
  saveMessageFeedback,
  saveBrowserLatency,
  sendChatMessageStream,
  uploadDocument,
} from "../lib/chat";

type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  feedbackRating?: 1 | -1;
};

type ApiStatus = "checking" | "connected" | "disconnected";
type AuthMode = "login" | "register";

const directExamples = ["什么是检索增强生成？", "帮我梳理一个项目计划。"];
const knowledgeBaseExamples = ["上传文档后处于什么状态？", "如何判断回答是否有依据？"];
const apiStatusLabel: Record<ApiStatus, string> = {
  checking: "正在检查 API",
  connected: "API 已连接",
  disconnected: "API 未连接",
};
const documentStatusLabel: Record<string, string> = {
  pending: "等待处理",
  processing: "处理中",
  ready: "可检索",
  failed: "处理失败",
};

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [isCreatingKnowledgeBase, setIsCreatingKnowledgeBase] = useState(false);
  const [isDeletingKnowledgeBase, setIsDeletingKnowledgeBase] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [retryingDocumentId, setRetryingDocumentId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [apiStatus, setApiStatus] = useState<ApiStatus>("checking");
  const [authSession, setAuthSession] = useState<AuthSession | null>(null);
  const [authMode, setAuthMode] = useState<AuthMode>("login");
  const [authEmail, setAuthEmail] = useState("");
  const [authPassword, setAuthPassword] = useState("");
  const [isAuthenticating, setIsAuthenticating] = useState(false);
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [selectedKnowledgeBaseId, setSelectedKnowledgeBaseId] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [isLoadingConversation, setIsLoadingConversation] = useState(false);
  const [savingFeedbackMessageId, setSavingFeedbackMessageId] = useState<string | null>(null);
  const [streamPhase, setStreamPhase] = useState<string | null>(null);
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

  const loadConversations = useCallback(async (knowledgeBaseId: string) => {
    try {
      setConversations(await getConversations(knowledgeBaseId));
    } catch (loadError) {
      setError(loadError instanceof ChatApiError ? loadError.message : "无法读取会话记录。");
    }
  }, []);

  useEffect(() => {
    let isActive = true;

    void getApiHealth()
      .then(() => {
        if (isActive) setApiStatus("connected");
      })
      .catch(() => {
        if (isActive) setApiStatus("disconnected");
      });
    void Promise.resolve().then(() => {
      if (isActive) setAuthSession(getStoredSession());
    });

    return () => {
      isActive = false;
    };
  }, []);

  useEffect(() => {
    if (!authSession) return;

    async function initializeKnowledgeBases() {
      try {
        const bases = await getKnowledgeBases();
        setKnowledgeBases(bases);
        setSelectedKnowledgeBaseId(bases[0]?.id ?? "");
      } catch (loadError) {
        setError(loadError instanceof ChatApiError ? loadError.message : "无法加载知识库。");
      }
    }

    void initializeKnowledgeBases();
  }, [authSession]);

  useEffect(() => {
    if (!selectedKnowledgeBaseId) {
      return;
    }

    async function refreshKnowledgeBaseData() {
      await Promise.all([
        loadDocuments(selectedKnowledgeBaseId),
        loadConversations(selectedKnowledgeBaseId),
      ]);
    }

    void refreshKnowledgeBaseData();
  }, [
    loadDocuments,
    loadConversations,
    selectedKnowledgeBaseId,
  ]);

  useEffect(() => {
    if (!selectedKnowledgeBaseId || !hasPendingDocuments) return;
    const timer = window.setInterval(() => void loadDocuments(selectedKnowledgeBaseId), 3_000);
    return () => window.clearInterval(timer);
  }, [hasPendingDocuments, loadDocuments, selectedKnowledgeBaseId]);

  async function submitMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const message = draft.trim();
    if (!message || isSending) return;

    const userMessage: Message = {
      id: `local-${Date.now()}`,
      role: "user",
      content: message,
    };
    setMessages((current) => [...current, userMessage]);
    setDraft("");
    setError(null);
    setIsSending(true);
    setStreamPhase("retrieving");
    const requestStartedAt = performance.now();

    try {
      const history: ChatHistoryMessage[] = messages.slice(-6).map((item) => ({
        role: item.role,
        content: item.content.slice(0, 2_000),
      }));
      const result = await sendChatMessageStream(
        message,
        selectedKnowledgeBaseId || undefined,
        history,
        conversationId ?? undefined,
        setStreamPhase,
      );
      const endToEndLatencyMs = Math.round(performance.now() - requestStartedAt);
      setConversationId(result.conversation_id ?? null);
      setMessages((current) => [
        ...current,
        {
          id: result.assistant_message_id ?? `local-${Date.now() + 1}`,
          role: "assistant",
          content: result.answer,
          citations: result.citations,
        },
      ]);
      if (
        selectedKnowledgeBaseId &&
        result.conversation_id &&
        result.assistant_message_id
      ) {
        await saveBrowserLatency(
          selectedKnowledgeBaseId,
          result.conversation_id,
          result.assistant_message_id,
          endToEndLatencyMs,
        );
      }
      if (selectedKnowledgeBaseId) {
        await loadConversations(selectedKnowledgeBaseId);
      }
    } catch (requestError) {
      setError(
        requestError instanceof ChatApiError
          ? requestError.message
          : "发生了未知错误，请稍后重试。",
      );
    } finally {
      setIsSending(false);
      setStreamPhase(null);
    }
  }

  async function openConversation(nextConversationId: string) {
    if (!selectedKnowledgeBaseId || isLoadingConversation) return;
    setIsLoadingConversation(true);
    setError(null);
    try {
      const storedMessages = await getConversationMessages(
        selectedKnowledgeBaseId,
        nextConversationId,
      );
      setMessages(
        storedMessages.map((message) => ({
          id: message.id,
          role: message.role,
          content: message.content,
          citations: message.citations,
        })),
      );
      setConversationId(nextConversationId);
    } catch (loadError) {
      setError(loadError instanceof ChatApiError ? loadError.message : "无法加载该会话。");
    } finally {
      setIsLoadingConversation(false);
    }
  }

  async function submitMessageFeedback(messageId: string, rating: 1 | -1) {
    if (!selectedKnowledgeBaseId || !conversationId || savingFeedbackMessageId) return;
    setSavingFeedbackMessageId(messageId);
    setError(null);
    try {
      await saveMessageFeedback(selectedKnowledgeBaseId, conversationId, messageId, rating);
      setMessages((current) =>
        current.map((message) => (message.id === messageId ? { ...message, feedbackRating: rating } : message)),
      );
    } catch (requestError) {
      setError(requestError instanceof ChatApiError ? requestError.message : "无法保存反馈。");
    } finally {
      setSavingFeedbackMessageId(null);
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
      setConversationId(null);
      setNewKnowledgeBaseName("");
    } catch (requestError) {
      setError(requestError instanceof ChatApiError ? requestError.message : "无法创建知识库。");
    } finally {
      setIsCreatingKnowledgeBase(false);
    }
  }

  async function submitAuthentication(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!authEmail.trim() || authPassword.length < 12 || isAuthenticating) return;

    setIsAuthenticating(true);
    setError(null);
    try {
      const session = authMode === "register"
        ? await register(authEmail.trim(), authPassword)
        : await login(authEmail.trim(), authPassword);
      saveSession(session);
      setAuthSession(session);
      setAuthPassword("");
    } catch (requestError) {
      setError(requestError instanceof ChatApiError ? requestError.message : "无法完成认证。");
    } finally {
      setIsAuthenticating(false);
    }
  }

  async function signOut() {
    await logout();
    setAuthSession(null);
    setKnowledgeBases([]);
    setSelectedKnowledgeBaseId("");
    setConversationId(null);
    setConversations([]);
    setDocuments([]);
    setMessages([]);
  }

  async function removeKnowledgeBase() {
    if (!selectedKnowledgeBase || isDeletingKnowledgeBase) return;
    if (!window.confirm(`删除“${selectedKnowledgeBase.name}”及其所有资料、评测记录和向量？此操作无法撤销。`)) {
      return;
    }

    setIsDeletingKnowledgeBase(true);
    setError(null);
    try {
      await deleteKnowledgeBase(selectedKnowledgeBase.id);
      const remainingKnowledgeBases = knowledgeBases.filter(
        (knowledgeBase) => knowledgeBase.id !== selectedKnowledgeBase.id,
      );
      setKnowledgeBases(remainingKnowledgeBases);
      setSelectedKnowledgeBaseId(remainingKnowledgeBases[0]?.id ?? "");
      setConversationId(null);
      setConversations([]);
      setMessages([]);
      setDocuments([]);
    } catch (requestError) {
      setError(requestError instanceof ChatApiError ? requestError.message : "无法删除知识库。");
    } finally {
      setIsDeletingKnowledgeBase(false);
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

  async function retryFailedDocument(documentId: string) {
    if (!selectedKnowledgeBaseId || retryingDocumentId) return;

    setRetryingDocumentId(documentId);
    setError(null);
    try {
      const document = await retryDocument(selectedKnowledgeBaseId, documentId);
      setDocuments((current) => current.map((item) => (item.id === document.id ? document : item)));
    } catch (requestError) {
      setError(requestError instanceof ChatApiError ? requestError.message : "无法重新处理文档。");
    } finally {
      setRetryingDocumentId(null);
    }
  }

  const scopeLabel = selectedKnowledgeBase ? "当前：知识库问答" : "当前：通用问答";
  const activeExamples = selectedKnowledgeBase ? knowledgeBaseExamples : directExamples;

  if (!authSession) {
    return (
      <main className="auth-shell">
        <section className="auth-card" aria-labelledby="auth-title">
          <span className="brand-mark">E</span>
          <p className="eyebrow">EVIDENCE RAG</p>
          <h1 id="auth-title">{authMode === "login" ? "登录工作台" : "创建本地账户"}</h1>
          <p className="auth-copy">
            {authMode === "login"
              ? "登录后仅能访问属于当前账户的知识库与评测记录。"
              : "首位注册用户会接管本机已有的旧知识库；后续账户彼此隔离。"}
          </p>
          <form className="auth-form" onSubmit={submitAuthentication}>
            <label htmlFor="auth-email">邮箱</label>
            <input
              id="auth-email"
              type="email"
              value={authEmail}
              onChange={(event) => setAuthEmail(event.target.value)}
              autoComplete="email"
              required
            />
            <label htmlFor="auth-password">密码</label>
            <input
              id="auth-password"
              type="password"
              value={authPassword}
              onChange={(event) => setAuthPassword(event.target.value)}
              autoComplete={authMode === "login" ? "current-password" : "new-password"}
              minLength={12}
              required
            />
            <button type="submit" disabled={isAuthenticating}>
              {isAuthenticating ? "处理中" : authMode === "login" ? "登录" : "注册并登录"}
            </button>
          </form>
          <button
            className="auth-switch"
            type="button"
            onClick={() => setAuthMode((mode) => (mode === "login" ? "register" : "login"))}
          >
            {authMode === "login" ? "还没有账户？创建本地账户" : "已有账户？返回登录"}
          </button>
          {error && <p className="error auth-error" role="alert">{error}</p>}
        </section>
      </main>
    );
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
        <nav className="primary-nav" aria-label="主导航">
          <a className="active" href="#chat">知识问答</a>
          <a className="management-link" href="/evaluation">评测管理</a>
        </nav>
        <div className="account-menu">
          <span>{authSession.user.email}</span>
          <button type="button" onClick={() => void signOut()}>退出</button>
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
                setMessages([]);
                setConversationId(null);
                setConversations([]);
                setDocuments([]);
                setSelectedKnowledgeBaseId(event.target.value);
              }}
            >
              <option value="">不使用知识库（通用问答）</option>
              {knowledgeBases.map((knowledgeBase) => (
                <option key={knowledgeBase.id} value={knowledgeBase.id}>
                  {knowledgeBase.name}
                </option>
              ))}
            </select>
            {selectedKnowledgeBase && (
              <>
                <span className="document-count">
                  {documents.filter((document) => document.status === "ready").length} 个可检索文档
                </span>
                <button
                  type="button"
                  className="delete-knowledge-base"
                  disabled={isDeletingKnowledgeBase}
                  onClick={() => void removeKnowledgeBase()}
                >
                  {isDeletingKnowledgeBase ? "删除中" : "删除知识库"}
                </button>
              </>
            )}
          </section>

          {selectedKnowledgeBase && (
            <section className="conversation-history" aria-label="当前知识库会话记录">
              <div className="conversation-history-heading">
                <span>会话记录</span>
                <button
                  type="button"
                  onClick={() => {
                    setConversationId(null);
                    setMessages([]);
                  }}
                >
                  新建对话
                </button>
              </div>
              {conversations.length ? (
                <div className="conversation-history-list">
                  {conversations.slice(0, 5).map((conversation) => (
                    <button
                      key={conversation.id}
                      type="button"
                      className={conversation.id === conversationId ? "active" : ""}
                      disabled={isLoadingConversation}
                      onClick={() => void openConversation(conversation.id)}
                    >
                      {conversation.title}
                    </button>
                  ))}
                </div>
              ) : (
                <span className="conversation-history-empty">还没有已保存的问答；在下方输入第一个问题即可开始。</span>
              )}
            </section>
          )}

          <div className="conversation" aria-live="polite">
            {messages.length === 0 ? (
              <div className="empty-state">
                <p className="empty-kicker">{selectedKnowledgeBase ? "知识库问答" : "通用问答"}</p>
                <h2>
                  {selectedKnowledgeBase
                    ? "基于当前资料回答，并展示证据。"
                    : "直接提问，不检索资料，也不提供证据。"}
                </h2>
                <p>
                  {selectedKnowledgeBase
                    ? "系统只会使用已完成处理的文档。没有检索到证据时，后端会拒答而不是编造。"
                    : "适合通用问题。若希望回答基于你的资料，请选择知识库后再提问。"}
                </p>
                {!selectedKnowledgeBase && (
                  <p className="empty-next-step">需要资料依据？在右侧新建知识库、上传资料后切换到知识库问答。</p>
                )}
                <div className="example-list">
                  {activeExamples.map((example) => (
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
                  {message.role === "assistant" && selectedKnowledgeBaseId && !message.id.startsWith("local-") && (
                    <div className="message-feedback" aria-label="回答反馈">
                      <span>这条回答有帮助吗？</span>
                      <button
                        type="button"
                        aria-pressed={message.feedbackRating === 1}
                        disabled={savingFeedbackMessageId === message.id}
                        onClick={() => void submitMessageFeedback(message.id, 1)}
                      >
                        有帮助
                      </button>
                      <button
                        type="button"
                        aria-pressed={message.feedbackRating === -1}
                        disabled={savingFeedbackMessageId === message.id}
                        onClick={() => void submitMessageFeedback(message.id, -1)}
                      >
                        不支持
                      </button>
                    </div>
                  )}
                </article>
              ))
            )}
            {isSending && (
              <p className="sending">
                {streamPhase === "retrieving" ? "正在检索证据并生成回答…" : "正在请求回答…"}
              </p>
            )}
          </div>

          <form className="composer" onSubmit={submitMessage}>
            <label className="sr-only" htmlFor="message">
              输入问题
            </label>
            <textarea
              id="message"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder={selectedKnowledgeBase ? "基于当前知识库提问…" : "输入通用问题…"}
              rows={3}
              disabled={isSending}
            />
            <div className="composer-footer">
              <span>
                {selectedKnowledgeBase
                  ? "只展示服务端校验过的证据；最多携带最近 6 条对话"
                  : "通用问答：不检索资料，不提供证据；最多携带最近 6 条对话"}
              </span>
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
                      <div className="document-details">
                        <span className="document-name">{document.filename}</span>
                        {document.status === "failed" && document.error_message && (
                          <span className="document-error">{document.error_message}</span>
                        )}
                      </div>
                      <div className="document-actions">
                        <span className={`document-status ${document.status}`}>
                          {documentStatusLabel[document.status] ?? document.status}
                        </span>
                        {document.status === "failed" && (
                          <button
                            type="button"
                            className="document-retry"
                            disabled={retryingDocumentId !== null}
                            onClick={() => void retryFailedDocument(document.id)}
                          >
                            {retryingDocumentId === document.id ? "重试中" : "重试"}
                          </button>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="panel-empty">点击上方“上传资料”，选择 Markdown、PDF 或 DOCX 后即可开始处理。</p>
              )
            ) : (
              <p className="panel-empty">新建或选择知识库后即可上传资料并启用证据问答。</p>
            )}
            {selectedKnowledgeBase && hasPendingDocuments && (
              <p className="document-progress">资料正在处理，会每 3 秒自动刷新状态。</p>
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
