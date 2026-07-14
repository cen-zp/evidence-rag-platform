"use client";

import { ChangeEvent, FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  ChatApiError,
  ChatHistoryMessage,
  Citation,
  DocumentRecord,
  EvaluationCase,
  KnowledgeBase,
  RetrievalEvaluationReport,
  createEvaluationCase,
  createKnowledgeBase,
  deleteEvaluationCase,
  getApiHealth,
  getDocuments,
  getEvaluationCases,
  getKnowledgeBases,
  retryDocument,
  runRetrievalEvaluation,
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
  const [retryingDocumentId, setRetryingDocumentId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [apiStatus, setApiStatus] = useState<ApiStatus>("checking");
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [selectedKnowledgeBaseId, setSelectedKnowledgeBaseId] = useState("");
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [evaluationCases, setEvaluationCases] = useState<EvaluationCase[]>([]);
  const [evaluationReport, setEvaluationReport] = useState<RetrievalEvaluationReport | null>(null);
  const [newKnowledgeBaseName, setNewKnowledgeBaseName] = useState("");
  const [evaluationQuestion, setEvaluationQuestion] = useState("");
  const [expectedFilename, setExpectedFilename] = useState("");
  const [isSavingEvaluationCase, setIsSavingEvaluationCase] = useState(false);
  const [deletingEvaluationCaseId, setDeletingEvaluationCaseId] = useState<string | null>(null);
  const [isRunningEvaluation, setIsRunningEvaluation] = useState(false);
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

  const loadEvaluationCases = useCallback(async (knowledgeBaseId: string) => {
    try {
      setEvaluationCases(await getEvaluationCases(knowledgeBaseId));
    } catch (loadError) {
      setError(loadError instanceof ChatApiError ? loadError.message : "无法读取评测案例。");
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

    async function refreshKnowledgeBaseData() {
      await Promise.all([
        loadDocuments(selectedKnowledgeBaseId),
        loadEvaluationCases(selectedKnowledgeBaseId),
      ]);
    }

    void refreshKnowledgeBaseData();
  }, [loadDocuments, loadEvaluationCases, selectedKnowledgeBaseId]);

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
      const history: ChatHistoryMessage[] = messages.slice(-6).map((item) => ({
        role: item.role,
        content: item.content.slice(0, 2_000),
      }));
      const result = await sendChatMessage(message, selectedKnowledgeBaseId || undefined, history);
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

  async function submitEvaluationCase(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const question = evaluationQuestion.trim();
    const filename = expectedFilename.trim();
    if (!question || !filename || !selectedKnowledgeBaseId || isSavingEvaluationCase) return;

    setIsSavingEvaluationCase(true);
    setError(null);
    try {
      const evaluationCase = await createEvaluationCase(selectedKnowledgeBaseId, question, filename);
      setEvaluationCases((current) => [evaluationCase, ...current]);
      setEvaluationQuestion("");
      setExpectedFilename("");
      setEvaluationReport(null);
    } catch (requestError) {
      setError(requestError instanceof ChatApiError ? requestError.message : "无法保存评测案例。");
    } finally {
      setIsSavingEvaluationCase(false);
    }
  }

  async function runEvaluation() {
    if (!selectedKnowledgeBaseId || !evaluationCases.length || isRunningEvaluation) return;

    setIsRunningEvaluation(true);
    setError(null);
    try {
      setEvaluationReport(await runRetrievalEvaluation(selectedKnowledgeBaseId));
    } catch (requestError) {
      setError(requestError instanceof ChatApiError ? requestError.message : "无法运行评测。");
    } finally {
      setIsRunningEvaluation(false);
    }
  }

  async function removeEvaluationCase(evaluationCaseId: string) {
    if (!selectedKnowledgeBaseId || deletingEvaluationCaseId) return;

    setDeletingEvaluationCaseId(evaluationCaseId);
    setError(null);
    try {
      await deleteEvaluationCase(selectedKnowledgeBaseId, evaluationCaseId);
      setEvaluationCases((current) => current.filter((item) => item.id !== evaluationCaseId));
      setEvaluationReport(null);
    } catch (requestError) {
      setError(requestError instanceof ChatApiError ? requestError.message : "无法删除评测案例。");
    } finally {
      setDeletingEvaluationCaseId(null);
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
                setMessages([]);
                setDocuments([]);
                setEvaluationCases([]);
                setEvaluationReport(null);
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
              <span>
                {selectedKnowledgeBase
                  ? "只展示服务端校验过的证据；最多携带最近 6 条对话"
                  : "未选择知识库：直接模型调用；最多携带最近 6 条对话"}
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
                        <span className={`document-status ${document.status}`}>{document.status}</span>
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
                <p className="panel-empty">上传 Markdown、PDF 或 DOCX 后，Worker 会在此更新处理状态。</p>
              )
            ) : (
              <p className="panel-empty">新建或选择知识库后即可上传资料并启用证据问答。</p>
            )}
          </section>

          <section className="evaluation-section" aria-label="检索评测">
            <p className="eyebrow">RETRIEVAL EVALUATION</p>
            <div className="section-heading">
              <h3>检索评测</h3>
              <button
                type="button"
                className="text-button"
                disabled={!selectedKnowledgeBase || !evaluationCases.length || isRunningEvaluation}
                onClick={runEvaluation}
              >
                {isRunningEvaluation ? "评测中" : "运行评测"}
              </button>
            </div>
            {selectedKnowledgeBase ? (
              <>
                <form className="evaluation-form" onSubmit={submitEvaluationCase}>
                  <label className="sr-only" htmlFor="evaluation-question">
                    评测问题
                  </label>
                  <input
                    id="evaluation-question"
                    value={evaluationQuestion}
                    onChange={(event) => setEvaluationQuestion(event.target.value)}
                    placeholder="评测问题"
                    maxLength={2_000}
                  />
                  <label className="sr-only" htmlFor="expected-filename">
                    预期命中文件名
                  </label>
                  <input
                    id="expected-filename"
                    value={expectedFilename}
                    onChange={(event) => setExpectedFilename(event.target.value)}
                    placeholder="预期命中的文件名"
                    list="ready-document-filenames"
                    maxLength={512}
                  />
                  <datalist id="ready-document-filenames">
                    {documents
                      .filter((document) => document.status === "ready")
                      .map((document) => <option key={document.id} value={document.filename} />)}
                  </datalist>
                  <button
                    type="submit"
                    disabled={!evaluationQuestion.trim() || !expectedFilename.trim() || isSavingEvaluationCase}
                  >
                    {isSavingEvaluationCase ? "保存中" : "新增案例"}
                  </button>
                </form>
                <p className="evaluation-summary">
                  已保存 {evaluationCases.length} 条案例。指标只反映当前题集和当前检索配置。
                </p>
                {evaluationCases.length > 0 && (
                  <ul className="evaluation-case-list" aria-label="最近评测案例">
                    {evaluationCases.slice(0, 3).map((evaluationCase) => (
                      <li key={evaluationCase.id}>
                        <div>
                          <p>{evaluationCase.question}</p>
                          <span>预期：{evaluationCase.expected_filenames.join("、")}</span>
                        </div>
                        <button
                          type="button"
                          aria-label={`删除案例：${evaluationCase.question}`}
                          disabled={deletingEvaluationCaseId !== null}
                          onClick={() => void removeEvaluationCase(evaluationCase.id)}
                        >
                          {deletingEvaluationCaseId === evaluationCase.id ? "删除中" : "删除"}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
                {evaluationReport && (
                  <dl className="evaluation-report">
                    <div>
                      <dt>Recall@{evaluationReport.top_k}</dt>
                      <dd>{(evaluationReport.recall_at_k * 100).toFixed(1)}%</dd>
                    </div>
                    <div>
                      <dt>MRR</dt>
                      <dd>{evaluationReport.mean_reciprocal_rank.toFixed(3)}</dd>
                    </div>
                    <div>
                      <dt>平均检索</dt>
                      <dd>{evaluationReport.mean_latency_ms.toFixed(1)} ms</dd>
                    </div>
                    <div>
                      <dt>P95 检索</dt>
                      <dd>{evaluationReport.p95_latency_ms.toFixed(1)} ms</dd>
                    </div>
                  </dl>
                )}
              </>
            ) : (
              <p className="panel-empty">选择知识库后，可积累题集并运行本地检索评测。</p>
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
