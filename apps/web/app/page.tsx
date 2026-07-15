"use client";

import { ChangeEvent, FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  AnswerReviewSummary,
  AuthSession,
  ChatApiError,
  ChatHistoryMessage,
  ChatResponse,
  Citation,
  Conversation,
  DocumentRecord,
  EndToEndLatencySummary,
  EvaluationCase,
  KnowledgeBase,
  ModelUsageSummary,
  RetrievalEvaluationReport,
  ReviewVerdict,
  createAnswerReview,
  createEvaluationCase,
  createKnowledgeBase,
  deleteEvaluationCase,
  deleteKnowledgeBase,
  getAnswerReviewSummary,
  getApiHealth,
  getConversationMessages,
  getConversations,
  getDocuments,
  getEndToEndLatencySummary,
  getEvaluationCases,
  getKnowledgeBases,
  getModelUsageSummary,
  getStoredSession,
  login,
  logout,
  retryDocument,
  runRetrievalEvaluation,
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
  model?: string;
  latencyMs?: number;
  retrievalLatencyMs?: number;
  serviceLatencyMs?: number;
  endToEndLatencyMs?: number;
  usage?: ChatResponse["usage"];
  citations?: Citation[];
  evaluationCaseId?: string;
  feedbackRating?: 1 | -1;
};

type ApiStatus = "checking" | "connected" | "disconnected";
type AuthMode = "login" | "register";

const examples = ["上传文档后处于什么状态？", "如何判断回答是否有依据？"];
const reviewVerdictOptions: { value: ReviewVerdict; label: string }[] = [
  { value: "pass", label: "通过" },
  { value: "fail", label: "不通过" },
  { value: "not_applicable", label: "不适用" },
];
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
  const [evaluationCases, setEvaluationCases] = useState<EvaluationCase[]>([]);
  const [evaluationReport, setEvaluationReport] = useState<RetrievalEvaluationReport | null>(null);
  const [answerReviewSummary, setAnswerReviewSummary] = useState<AnswerReviewSummary | null>(null);
  const [modelUsageSummary, setModelUsageSummary] = useState<ModelUsageSummary | null>(null);
  const [latencySummary, setLatencySummary] = useState<EndToEndLatencySummary | null>(null);
  const [newKnowledgeBaseName, setNewKnowledgeBaseName] = useState("");
  const [evaluationQuestion, setEvaluationQuestion] = useState("");
  const [expectedFilename, setExpectedFilename] = useState("");
  const [isSavingEvaluationCase, setIsSavingEvaluationCase] = useState(false);
  const [deletingEvaluationCaseId, setDeletingEvaluationCaseId] = useState<string | null>(null);
  const [isRunningEvaluation, setIsRunningEvaluation] = useState(false);
  const [draftEvaluationCaseId, setDraftEvaluationCaseId] = useState<string | null>(null);
  const [reviewingEvaluationCaseId, setReviewingEvaluationCaseId] = useState<string | null>(null);
  const [answerVerdict, setAnswerVerdict] = useState<ReviewVerdict | "">("");
  const [citationVerdict, setCitationVerdict] = useState<ReviewVerdict | "">("");
  const [refusalVerdict, setRefusalVerdict] = useState<ReviewVerdict | "">("");
  const [reviewNotes, setReviewNotes] = useState("");
  const [isSavingAnswerReview, setIsSavingAnswerReview] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const selectedKnowledgeBase = knowledgeBases.find(
    (knowledgeBase) => knowledgeBase.id === selectedKnowledgeBaseId,
  );
  const latestCitations = useMemo(
    () => [...messages].reverse().find((message) => message.role === "assistant")?.citations ?? [],
    [messages],
  );
  const latestReviewableAnswer = useMemo(
    () =>
      [...messages]
        .reverse()
        .find((message) => message.role === "assistant" && message.evaluationCaseId),
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

  const loadAnswerReviewSummary = useCallback(async (knowledgeBaseId: string) => {
    try {
      setAnswerReviewSummary(await getAnswerReviewSummary(knowledgeBaseId));
    } catch (loadError) {
      setError(loadError instanceof ChatApiError ? loadError.message : "无法读取答案评审汇总。");
    }
  }, []);

  const loadModelUsageSummary = useCallback(async (knowledgeBaseId: string) => {
    try {
      setModelUsageSummary(await getModelUsageSummary(knowledgeBaseId));
    } catch (loadError) {
      setError(loadError instanceof ChatApiError ? loadError.message : "无法读取模型调用摘要。");
    }
  }, []);

  const loadLatencySummary = useCallback(async (knowledgeBaseId: string) => {
    try {
      setLatencySummary(await getEndToEndLatencySummary(knowledgeBaseId));
    } catch (loadError) {
      setError(loadError instanceof ChatApiError ? loadError.message : "无法读取端到端耗时摘要。");
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
        loadEvaluationCases(selectedKnowledgeBaseId),
        loadAnswerReviewSummary(selectedKnowledgeBaseId),
        loadModelUsageSummary(selectedKnowledgeBaseId),
        loadLatencySummary(selectedKnowledgeBaseId),
        loadConversations(selectedKnowledgeBaseId),
      ]);
    }

    void refreshKnowledgeBaseData();
  }, [
    loadAnswerReviewSummary,
    loadDocuments,
    loadEvaluationCases,
    loadConversations,
    loadLatencySummary,
    loadModelUsageSummary,
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

    const evaluationCaseId = evaluationCases.some(
      (evaluationCase) =>
        evaluationCase.id === draftEvaluationCaseId && evaluationCase.question === message,
    )
      ? draftEvaluationCaseId ?? undefined
      : undefined;
    const userMessage: Message = {
      id: `local-${Date.now()}`,
      role: "user",
      content: message,
      evaluationCaseId,
    };
    setMessages((current) => [...current, userMessage]);
    setDraft("");
    setDraftEvaluationCaseId(null);
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
          model: result.model,
          latencyMs: result.latency_ms,
          retrievalLatencyMs: result.retrieval_latency_ms,
          serviceLatencyMs: result.total_latency_ms,
          endToEndLatencyMs,
          citations: result.citations,
          usage: result.usage,
          evaluationCaseId,
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
        await Promise.all([
          loadModelUsageSummary(selectedKnowledgeBaseId),
          loadLatencySummary(selectedKnowledgeBaseId),
          loadConversations(selectedKnowledgeBaseId),
        ]);
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
          model: message.model ?? undefined,
          latencyMs: message.latency_ms ?? undefined,
          retrievalLatencyMs: message.retrieval_latency_ms ?? undefined,
          serviceLatencyMs: message.total_latency_ms ?? undefined,
          endToEndLatencyMs: message.browser_end_to_end_latency_ms ?? undefined,
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
      setModelUsageSummary(null);
      setLatencySummary(null);
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
    setEvaluationCases([]);
    setEvaluationReport(null);
    setAnswerReviewSummary(null);
    setModelUsageSummary(null);
    setLatencySummary(null);
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
      setEvaluationCases([]);
      setEvaluationReport(null);
      setAnswerReviewSummary(null);
      setModelUsageSummary(null);
      setLatencySummary(null);
      setDraftEvaluationCaseId(null);
      setReviewingEvaluationCaseId(null);
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

  async function submitEvaluationCase(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const question = evaluationQuestion.trim();
    const filenames = [
      ...new Set(
        expectedFilename
          .split(/[，,]/)
          .map((filename) => filename.trim())
          .filter(Boolean),
      ),
    ];
    if (!question || !filenames.length || !selectedKnowledgeBaseId || isSavingEvaluationCase) return;
    if (filenames.length > 10) {
      setError("每条评测案例最多填写 10 个预期来源文件名。");
      return;
    }

    setIsSavingEvaluationCase(true);
    setError(null);
    try {
      const evaluationCase = await createEvaluationCase(selectedKnowledgeBaseId, question, filenames);
      setEvaluationCases((current) => [evaluationCase, ...current]);
      setEvaluationQuestion("");
      setExpectedFilename("");
      setEvaluationReport(null);
      setAnswerReviewSummary(null);
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
      setAnswerReviewSummary(null);
      if (reviewingEvaluationCaseId === evaluationCaseId) setReviewingEvaluationCaseId(null);
    } catch (requestError) {
      setError(requestError instanceof ChatApiError ? requestError.message : "无法删除评测案例。");
    } finally {
      setDeletingEvaluationCaseId(null);
    }
  }

  function askEvaluationCase(evaluationCase: EvaluationCase) {
    setDraft(evaluationCase.question);
    setDraftEvaluationCaseId(evaluationCase.id);
    setReviewingEvaluationCaseId(null);
  }

  function startAnswerReview(evaluationCaseId: string) {
    setReviewingEvaluationCaseId(evaluationCaseId);
    setAnswerVerdict("");
    setCitationVerdict("");
    setRefusalVerdict("");
    setReviewNotes("");
  }

  async function submitAnswerReview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (
      !selectedKnowledgeBaseId ||
      !reviewingEvaluationCaseId ||
      !latestReviewableAnswer ||
      latestReviewableAnswer.evaluationCaseId !== reviewingEvaluationCaseId ||
      !answerVerdict ||
      !citationVerdict ||
      !refusalVerdict ||
      isSavingAnswerReview
    ) {
      return;
    }

    setIsSavingAnswerReview(true);
    setError(null);
    try {
      await createAnswerReview(selectedKnowledgeBaseId, reviewingEvaluationCaseId, {
        answer: latestReviewableAnswer.content,
        model: latestReviewableAnswer.model ?? "unknown",
        latency_ms: latestReviewableAnswer.latencyMs ?? 0,
        citation_chunk_ids: (latestReviewableAnswer.citations ?? []).map(
          (citation) => citation.chunk_id,
        ),
        answer_verdict: answerVerdict,
        citation_verdict: citationVerdict,
        refusal_verdict: refusalVerdict,
        notes: reviewNotes.trim() || null,
      });
      await loadAnswerReviewSummary(selectedKnowledgeBaseId);
      setReviewingEvaluationCaseId(null);
      setAnswerVerdict("");
      setCitationVerdict("");
      setRefusalVerdict("");
      setReviewNotes("");
    } catch (requestError) {
      setError(requestError instanceof ChatApiError ? requestError.message : "无法保存答案评审。");
    } finally {
      setIsSavingAnswerReview(false);
    }
  }

  const scopeLabel = selectedKnowledgeBase ? "当前：证据问答" : "当前：直接模型调用";

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
        <a className="formal-review-nav" href="/review">72 题真人审核</a>
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
                setEvaluationCases([]);
                setEvaluationReport(null);
                setAnswerReviewSummary(null);
                setModelUsageSummary(null);
                setLatencySummary(null);
                setDraftEvaluationCaseId(null);
                setReviewingEvaluationCaseId(null);
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
                <span className="conversation-history-empty">当前资料库还没有已保存的问答。</span>
              )}
            </section>
          )}

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
                    <>
                      <div className="message-meta">
                        <span>{message.model ?? "retrieval-guard"}</span>
                        <span>模型 {message.latencyMs ?? 0} ms</span>
                        {message.retrievalLatencyMs !== undefined && (
                          <span>检索 {message.retrievalLatencyMs} ms</span>
                        )}
                        {message.serviceLatencyMs !== undefined && (
                          <span>服务端全链路 {message.serviceLatencyMs} ms</span>
                        )}
                        {message.endToEndLatencyMs !== undefined && (
                          <span>浏览器端到端 {message.endToEndLatencyMs} ms</span>
                        )}
                        {message.usage && <span>{message.usage.total_tokens} tokens</span>}
                        {message.citations && <span>{message.citations.length} 条已校验证据</span>}
                      </div>
                      {selectedKnowledgeBaseId && !message.id.startsWith("local-") && (
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
                    </>
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
              onChange={(event) => {
                setDraft(event.target.value);
                setDraftEvaluationCaseId(null);
              }}
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
                    placeholder="预期命中文件名（逗号分隔）"
                    list="ready-document-filenames"
                    maxLength={2_000}
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
                  文件名可用中英文逗号分隔。已保存 {evaluationCases.length} 条案例；指标只反映当前题集和当前检索配置。
                </p>
                {evaluationCases.length > 0 && (
                  <ul className="evaluation-case-list" aria-label="最近评测案例">
                    {evaluationCases.slice(0, 3).map((evaluationCase) => (
                      <li key={evaluationCase.id}>
                        <div>
                          <p>{evaluationCase.question}</p>
                          <span>预期：{evaluationCase.expected_filenames.join("、")}</span>
                        </div>
                        <div className="evaluation-case-actions">
                          <button
                            type="button"
                            onClick={() => askEvaluationCase(evaluationCase)}
                          >
                            用此题提问
                          </button>
                          {latestReviewableAnswer?.evaluationCaseId === evaluationCase.id && (
                            <button
                              type="button"
                              onClick={() => startAnswerReview(evaluationCase.id)}
                            >
                              评审回答
                            </button>
                          )}
                          <button
                            type="button"
                            className="delete-evaluation-case"
                            aria-label={`删除案例：${evaluationCase.question}`}
                            disabled={deletingEvaluationCaseId !== null}
                            onClick={() => void removeEvaluationCase(evaluationCase.id)}
                          >
                            {deletingEvaluationCaseId === evaluationCase.id ? "删除中" : "删除"}
                          </button>
                        </div>
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
                {answerReviewSummary && (
                  <dl className="answer-review-summary">
                    <div>
                      <dt>已人工评审</dt>
                      <dd>{answerReviewSummary.review_count} 条</dd>
                    </div>
                    <div>
                      <dt>未覆盖案例</dt>
                      <dd>{answerReviewSummary.unreviewed_case_count} 条</dd>
                    </div>
                    <div>
                      <dt>答案通过</dt>
                      <dd>
                        {answerReviewSummary.answer_pass_rate === null
                          ? "—"
                          : `${(answerReviewSummary.answer_pass_rate * 100).toFixed(1)}%`}
                      </dd>
                    </div>
                    <div>
                      <dt>引用支持</dt>
                      <dd>
                        {answerReviewSummary.citation_pass_rate === null
                          ? "—"
                          : `${(answerReviewSummary.citation_pass_rate * 100).toFixed(1)}%`}
                      </dd>
                    </div>
                    <div>
                      <dt>拒答恰当</dt>
                      <dd>
                        {answerReviewSummary.refusal_pass_rate === null
                          ? "—"
                          : `${(answerReviewSummary.refusal_pass_rate * 100).toFixed(1)}%`}
                      </dd>
                    </div>
                  </dl>
                )}
                {modelUsageSummary && (
                  <>
                    <dl className="model-usage-summary">
                      <div>
                        <dt>已记录调用</dt>
                        <dd>{modelUsageSummary.call_count} 次</dd>
                      </div>
                      <div>
                        <dt>返回 token</dt>
                        <dd>{modelUsageSummary.usage_reported_call_count} 次</dd>
                      </div>
                      <div>
                        <dt>累计 token</dt>
                        <dd>{modelUsageSummary.total_tokens}</dd>
                      </div>
                      <div>
                        <dt>平均模型耗时</dt>
                        <dd>
                          {modelUsageSummary.mean_latency_ms === null
                            ? "—"
                            : `${modelUsageSummary.mean_latency_ms.toFixed(1)} ms`}
                        </dd>
                      </div>
                      <div>
                        <dt>已估算成本</dt>
                        <dd>{modelUsageSummary.estimated_cost_call_count} 次</dd>
                      </div>
                      <div>
                        <dt>平均单次成本</dt>
                        <dd>
                          {modelUsageSummary.mean_estimated_cost === null
                            ? "未配置"
                            : `${modelUsageSummary.mean_estimated_cost.toFixed(6)} ${modelUsageSummary.estimated_cost_currency}`}
                        </dd>
                      </div>
                    </dl>
                    <p className="model-usage-note">
                      单价在调用时从本地配置保存为快照；未配置单价或未返回 token 的调用不会估算成本。
                    </p>
                  </>
                )}
                {latencySummary && (
                  <>
                    <dl className="model-usage-summary">
                      <div>
                        <dt>已记录回答</dt>
                        <dd>{latencySummary.message_count} 条</dd>
                      </div>
                      <div>
                        <dt>回答 / 拒答</dt>
                        <dd>{latencySummary.answered_count} / {latencySummary.guarded_count}</dd>
                      </div>
                      <div>
                        <dt>平均检索耗时</dt>
                        <dd>
                          {latencySummary.mean_retrieval_latency_ms === null
                            ? "—"
                            : `${latencySummary.mean_retrieval_latency_ms.toFixed(1)} ms`}
                        </dd>
                      </div>
                      <div>
                        <dt>P95 检索耗时</dt>
                        <dd>
                          {latencySummary.p95_retrieval_latency_ms === null
                            ? "—"
                            : `${latencySummary.p95_retrieval_latency_ms} ms`}
                        </dd>
                      </div>
                      <div>
                        <dt>平均服务端全链路</dt>
                        <dd>
                          {latencySummary.mean_server_total_latency_ms === null
                            ? "—"
                            : `${latencySummary.mean_server_total_latency_ms.toFixed(1)} ms`}
                        </dd>
                      </div>
                      <div>
                        <dt>P95 服务端全链路</dt>
                        <dd>
                          {latencySummary.p95_server_total_latency_ms === null
                            ? "—"
                            : `${latencySummary.p95_server_total_latency_ms} ms`}
                        </dd>
                      </div>
                      <div>
                        <dt>平均浏览器端到端</dt>
                        <dd>
                          {latencySummary.mean_browser_end_to_end_latency_ms === null
                            ? "—"
                            : `${latencySummary.mean_browser_end_to_end_latency_ms.toFixed(1)} ms`}
                        </dd>
                      </div>
                      <div>
                        <dt>P95 浏览器端到端</dt>
                        <dd>
                          {latencySummary.p95_browser_end_to_end_latency_ms === null
                            ? "—"
                            : `${latencySummary.p95_browser_end_to_end_latency_ms} ms`}
                        </dd>
                      </div>
                    </dl>
                    <p className="model-usage-note">
                      浏览器端到端耗时从发起 SSE 到收到并解析最终结果；历史旧消息没有该字段。
                    </p>
                  </>
                )}
                {reviewingEvaluationCaseId &&
                  latestReviewableAnswer?.evaluationCaseId === reviewingEvaluationCaseId && (
                    <form className="answer-review-form" onSubmit={submitAnswerReview}>
                      <p className="answer-review-title">人工评审当前回答</p>
                      <p className="answer-review-answer">{latestReviewableAnswer.content}</p>
                      <p className="answer-review-meta">
                        {latestReviewableAnswer.model} · {latestReviewableAnswer.latencyMs} ms ·{" "}
                        {latestReviewableAnswer.citations?.length ?? 0} 条已校验证据
                      </p>
                      <fieldset>
                        <legend>答案是否符合参考资料或预期回答？</legend>
                        {reviewVerdictOptions.map((option) => (
                          <label key={`answer-${option.value}`}>
                            <input
                              type="radio"
                              name="answer-verdict"
                              checked={answerVerdict === option.value}
                              onChange={() => setAnswerVerdict(option.value)}
                            />
                            {option.label}
                          </label>
                        ))}
                      </fieldset>
                      <fieldset>
                        <legend>引用是否足以支持本次回答？</legend>
                        {reviewVerdictOptions.map((option) => (
                          <label key={`citation-${option.value}`}>
                            <input
                              type="radio"
                              name="citation-verdict"
                              checked={citationVerdict === option.value}
                              onChange={() => setCitationVerdict(option.value)}
                            />
                            {option.label}
                          </label>
                        ))}
                      </fieldset>
                      <fieldset>
                        <legend>面对证据不足时，拒答是否恰当？</legend>
                        {reviewVerdictOptions.map((option) => (
                          <label key={`refusal-${option.value}`}>
                            <input
                              type="radio"
                              name="refusal-verdict"
                              checked={refusalVerdict === option.value}
                              onChange={() => setRefusalVerdict(option.value)}
                            />
                            {option.label}
                          </label>
                        ))}
                      </fieldset>
                      <label className="sr-only" htmlFor="answer-review-notes">
                        评审备注
                      </label>
                      <textarea
                        id="answer-review-notes"
                        value={reviewNotes}
                        onChange={(event) => setReviewNotes(event.target.value)}
                        placeholder="可选：记录错误类型、遗漏证据或改进建议"
                        maxLength={2_000}
                        rows={3}
                      />
                      <div className="answer-review-actions">
                        <button type="button" onClick={() => setReviewingEvaluationCaseId(null)}>
                          取消
                        </button>
                        <button
                          type="submit"
                          disabled={
                            isSavingAnswerReview ||
                            !answerVerdict ||
                            !citationVerdict ||
                            !refusalVerdict
                          }
                        >
                          {isSavingAnswerReview ? "保存中" : "保存人工评审"}
                        </button>
                      </div>
                    </form>
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
