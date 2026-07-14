export type Citation = {
  chunk_id: string;
  document_id: string;
  filename: string;
  page_number: number | null;
  chunk_index: number;
  content: string;
};

export type ChatResponse = {
  answer: string;
  model: string;
  latency_ms: number;
  citations: Citation[];
  usage?: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
  };
  conversation_id?: string;
  assistant_message_id?: string;
};

export type ChatHistoryMessage = {
  role: "user" | "assistant";
  content: string;
};

export type HealthResponse = {
  status: string;
  environment: string;
};

export type AuthenticatedUser = {
  id: string;
  email: string;
};

export type AuthSession = {
  access_token: string;
  token_type: "bearer";
  user: AuthenticatedUser;
};

export type KnowledgeBase = {
  id: string;
  owner_id: string | null;
  name: string;
  description: string | null;
  created_at: string;
};

export type Conversation = {
  id: string;
  knowledge_base_id: string;
  title: string;
  created_at: string;
  updated_at: string;
};

export type ConversationMessage = {
  id: string;
  conversation_id: string;
  role: "user" | "assistant";
  content: string;
  citations: Citation[];
  model: string | null;
  latency_ms: number | null;
  created_at: string;
};

export type MessageFeedback = {
  id: string;
  message_id: string;
  rating: 1 | -1;
  comment: string | null;
  created_at: string;
};

export type DocumentRecord = {
  id: string;
  knowledge_base_id: string;
  filename: string;
  mime_type: string;
  status: "pending" | "processing" | "ready" | "failed";
  error_message: string | null;
  created_at: string;
  updated_at: string;
};

export type EvaluationCase = {
  id: string;
  knowledge_base_id: string;
  question: string;
  expected_filenames: string[];
  reference_answer: string | null;
  created_at: string;
};

export type RetrievalEvaluationReport = {
  case_count: number;
  top_k: number;
  recall_at_k: number;
  mean_reciprocal_rank: number;
  mean_latency_ms: number;
  p95_latency_ms: number;
};

export type ReviewVerdict = "pass" | "fail" | "not_applicable";

export type AnswerReview = {
  id: string;
  evaluation_case_id: string;
  answer: string;
  model: string;
  latency_ms: number;
  citation_chunk_ids: string[];
  citation_filenames: string[];
  answer_verdict: ReviewVerdict;
  citation_verdict: ReviewVerdict;
  refusal_verdict: ReviewVerdict;
  notes: string | null;
  created_at: string;
};

export type AnswerReviewSummary = {
  case_count: number;
  review_count: number;
  unreviewed_case_count: number;
  answer_pass_rate: number | null;
  citation_pass_rate: number | null;
  refusal_pass_rate: number | null;
};

export type ModelUsageSummary = {
  call_count: number;
  usage_reported_call_count: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  mean_latency_ms: number | null;
  p95_latency_ms: number | null;
  estimated_cost_call_count: number;
  estimated_cost_currency: string | null;
  total_estimated_cost: number | null;
  mean_estimated_cost: number | null;
};

export class ChatApiError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ChatApiError";
  }
}

const apiBaseUrl = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000").replace(
  /\/$/,
  "",
);
const authStorageKey = "evidence-rag.auth-session";

function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return getStoredSession()?.access_token ?? null;
  } catch {
    return null;
  }
}

async function request(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  const accessToken = getAccessToken();
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  return fetch(`${apiBaseUrl}${path}`, { ...init, headers });
}

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    if (response.status === 503) {
      throw new ChatApiError("本地服务暂不可用，请确认 API、Redis 和 Qdrant 已启动。");
    }
    throw new ChatApiError("本次请求未完成，请稍后重试。");
  }
  return (await response.json()) as T;
}

export async function getApiHealth(): Promise<HealthResponse> {
  try {
    return await readJson<HealthResponse>(await request("/health"));
  } catch (error) {
    if (error instanceof ChatApiError) throw error;
    throw new ChatApiError("API 不可用");
  }
}

export function getStoredSession(): AuthSession | null {
  if (typeof window === "undefined") return null;
  const rawSession = window.localStorage.getItem(authStorageKey);
  if (!rawSession) return null;
  try {
    return JSON.parse(rawSession) as AuthSession;
  } catch {
    window.localStorage.removeItem(authStorageKey);
    return null;
  }
}

export function saveSession(session: AuthSession): void {
  window.localStorage.setItem(authStorageKey, JSON.stringify(session));
}

export function clearSession(): void {
  window.localStorage.removeItem(authStorageKey);
}

async function authenticate(path: "/api/auth/register" | "/api/auth/login", email: string, password: string): Promise<AuthSession> {
  try {
    return await readJson<AuthSession>(
      await request(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      }),
    );
  } catch (error) {
    if (error instanceof ChatApiError) throw error;
    throw new ChatApiError("无法完成认证。请确认 API 已启动。");
  }
}

export function register(email: string, password: string): Promise<AuthSession> {
  return authenticate("/api/auth/register", email, password);
}

export function login(email: string, password: string): Promise<AuthSession> {
  return authenticate("/api/auth/login", email, password);
}

export async function logout(): Promise<void> {
  try {
    const response = await request("/api/auth/logout", { method: "POST" });
    if (!response.ok && response.status !== 401) throw new ChatApiError("无法退出当前会话。");
  } catch (error) {
    if (error instanceof ChatApiError) throw error;
  } finally {
    clearSession();
  }
}

export async function sendChatMessage(
  message: string,
  knowledgeBaseId?: string,
  history: ChatHistoryMessage[] = [],
  conversationId?: string,
): Promise<ChatResponse> {
  try {
    return await readJson<ChatResponse>(
      await request("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message,
          knowledge_base_id: knowledgeBaseId ?? null,
          history,
          conversation_id: conversationId ?? null,
        }),
      }),
    );
  } catch (error) {
    if (error instanceof ChatApiError) throw error;
    throw new ChatApiError("无法连接 API。请确认 FastAPI 已在 http://localhost:8000 启动。");
  }
}

export async function sendChatMessageStream(
  message: string,
  knowledgeBaseId?: string,
  history: ChatHistoryMessage[] = [],
  conversationId?: string,
  onStatus?: (phase: string) => void,
): Promise<ChatResponse> {
  try {
    const response = await request("/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        knowledge_base_id: knowledgeBaseId ?? null,
        history,
        conversation_id: conversationId ?? null,
      }),
    });
    if (!response.ok) return await readJson<ChatResponse>(response);
    if (!response.body) throw new ChatApiError("浏览器不支持流式响应，请刷新后重试。");

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let result: ChatResponse | null = null;

    function consumeEvent(record: string): void {
      const event = record
        .split("\n")
        .find((line) => line.startsWith("event: "))
        ?.slice("event: ".length);
      const data = record
        .split("\n")
        .filter((line) => line.startsWith("data: "))
        .map((line) => line.slice("data: ".length))
        .join("\n");
      if (!event || !data) return;

      try {
        const payload = JSON.parse(data) as ChatResponse | { phase?: string; detail?: string };
        if (event === "status") onStatus?.((payload as { phase?: string }).phase ?? "working");
        if (event === "error") {
          throw new ChatApiError((payload as { detail?: string }).detail ?? "本次请求未完成，请稍后重试。");
        }
        if (event === "result") result = payload as ChatResponse;
      } catch (error) {
        if (error instanceof ChatApiError) throw error;
        throw new ChatApiError("流式响应格式异常，请稍后重试。");
      }
    }

    while (true) {
      const { done, value } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      let separatorIndex = buffer.indexOf("\n\n");
      while (separatorIndex >= 0) {
        consumeEvent(buffer.slice(0, separatorIndex));
        buffer = buffer.slice(separatorIndex + 2);
        separatorIndex = buffer.indexOf("\n\n");
      }
      if (done) break;
    }

    if (result) return result;
    throw new ChatApiError("流式响应在返回结果前中断，请重试。");
  } catch (error) {
    if (error instanceof ChatApiError) throw error;
    throw new ChatApiError("无法连接 API。请确认 FastAPI 已在 http://localhost:8000 启动。");
  }
}

export async function getKnowledgeBases(): Promise<KnowledgeBase[]> {
  try {
    return await readJson<KnowledgeBase[]>(await request("/api/knowledge-bases"));
  } catch (error) {
    if (error instanceof ChatApiError) throw error;
    throw new ChatApiError("无法加载知识库。请确认 API 已启动。");
  }
}

export async function createKnowledgeBase(name: string): Promise<KnowledgeBase> {
  try {
    return await readJson<KnowledgeBase>(
      await request("/api/knowledge-bases", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      }),
    );
  } catch (error) {
    if (error instanceof ChatApiError) throw error;
    throw new ChatApiError("无法创建知识库。请确认 API 已启动。");
  }
}

export async function deleteKnowledgeBase(knowledgeBaseId: string): Promise<void> {
  try {
    const response = await request(`/api/knowledge-bases/${knowledgeBaseId}`, {
      method: "DELETE",
    });
    if (!response.ok) {
      throw new ChatApiError("无法删除知识库。");
    }
  } catch (error) {
    if (error instanceof ChatApiError) throw error;
    throw new ChatApiError("无法删除知识库。请确认 API 与 Qdrant 已启动。");
  }
}

export async function getConversations(knowledgeBaseId: string): Promise<Conversation[]> {
  try {
    return await readJson<Conversation[]>(
      await request(`/api/knowledge-bases/${knowledgeBaseId}/conversations`),
    );
  } catch (error) {
    if (error instanceof ChatApiError) throw error;
    throw new ChatApiError("无法加载会话记录。请确认 API 已启动。");
  }
}

export async function getConversationMessages(
  knowledgeBaseId: string,
  conversationId: string,
): Promise<ConversationMessage[]> {
  try {
    return await readJson<ConversationMessage[]>(
      await request(`/api/knowledge-bases/${knowledgeBaseId}/conversations/${conversationId}/messages`),
    );
  } catch (error) {
    if (error instanceof ChatApiError) throw error;
    throw new ChatApiError("无法加载会话消息。请确认 API 已启动。");
  }
}

export async function saveMessageFeedback(
  knowledgeBaseId: string,
  conversationId: string,
  messageId: string,
  rating: 1 | -1,
): Promise<MessageFeedback> {
  try {
    return await readJson<MessageFeedback>(
      await request(
        `/api/knowledge-bases/${knowledgeBaseId}/conversations/${conversationId}/messages/${messageId}/feedback`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ rating }),
        },
      ),
    );
  } catch (error) {
    if (error instanceof ChatApiError) throw error;
    throw new ChatApiError("无法保存反馈。请确认 API 已启动。");
  }
}

export async function getDocuments(knowledgeBaseId: string): Promise<DocumentRecord[]> {
  try {
    return await readJson<DocumentRecord[]>(
      await request(`/api/knowledge-bases/${knowledgeBaseId}/documents`),
    );
  } catch (error) {
    if (error instanceof ChatApiError) throw error;
    throw new ChatApiError("无法读取文档状态。请确认 API 已启动。");
  }
}

export async function uploadDocument(
  knowledgeBaseId: string,
  file: File,
): Promise<DocumentRecord> {
  const body = new FormData();
  body.append("file", file);

  try {
    return await readJson<DocumentRecord>(
      await request(`/api/knowledge-bases/${knowledgeBaseId}/documents`, {
        method: "POST",
        body,
      }),
    );
  } catch (error) {
    if (error instanceof ChatApiError) throw error;
    throw new ChatApiError("无法上传文档。请确认 API、Redis 已启动后重试。");
  }
}

export async function retryDocument(
  knowledgeBaseId: string,
  documentId: string,
): Promise<DocumentRecord> {
  try {
    return await readJson<DocumentRecord>(
      await request(
        `/api/knowledge-bases/${knowledgeBaseId}/documents/${documentId}/retry`,
        { method: "POST" },
      ),
    );
  } catch (error) {
    if (error instanceof ChatApiError) throw error;
    throw new ChatApiError("无法重新处理文档。请确认 Redis 与 API 已启动。");
  }
}

export async function getEvaluationCases(knowledgeBaseId: string): Promise<EvaluationCase[]> {
  try {
    return await readJson<EvaluationCase[]>(
      await request(`/api/knowledge-bases/${knowledgeBaseId}/evaluation-cases`),
    );
  } catch (error) {
    if (error instanceof ChatApiError) throw error;
    throw new ChatApiError("无法加载评测案例。请确认 API 已启动。");
  }
}

export async function createEvaluationCase(
  knowledgeBaseId: string,
  question: string,
  expectedFilenames: string[],
): Promise<EvaluationCase> {
  try {
    return await readJson<EvaluationCase>(
      await request(`/api/knowledge-bases/${knowledgeBaseId}/evaluation-cases`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, expected_filenames: expectedFilenames }),
      }),
    );
  } catch (error) {
    if (error instanceof ChatApiError) throw error;
    throw new ChatApiError("无法保存评测案例。请确认 API 已启动。");
  }
}

export async function deleteEvaluationCase(
  knowledgeBaseId: string,
  evaluationCaseId: string,
): Promise<void> {
  try {
    const response = await request(
      `/api/knowledge-bases/${knowledgeBaseId}/evaluation-cases/${evaluationCaseId}`,
      { method: "DELETE" },
    );
    if (!response.ok) {
      throw new ChatApiError("无法删除评测案例。");
    }
  } catch (error) {
    if (error instanceof ChatApiError) throw error;
    throw new ChatApiError("无法删除评测案例。请确认 API 已启动。");
  }
}

export async function runRetrievalEvaluation(
  knowledgeBaseId: string,
  topK = 5,
): Promise<RetrievalEvaluationReport> {
  try {
    return await readJson<RetrievalEvaluationReport>(
      await request(
        `/api/knowledge-bases/${knowledgeBaseId}/evaluations/retrieval?top_k=${topK}`,
        { method: "POST" },
      ),
    );
  } catch (error) {
    if (error instanceof ChatApiError) throw error;
    throw new ChatApiError("无法运行评测。请确认 API 与 Qdrant 已启动。");
  }
}

export async function getAnswerReviewSummary(
  knowledgeBaseId: string,
): Promise<AnswerReviewSummary> {
  try {
    return await readJson<AnswerReviewSummary>(
      await request(`/api/knowledge-bases/${knowledgeBaseId}/evaluations/answer-review-summary`),
    );
  } catch (error) {
    if (error instanceof ChatApiError) throw error;
    throw new ChatApiError("无法读取答案评审汇总。请确认 API 已启动。");
  }
}

export async function getModelUsageSummary(
  knowledgeBaseId: string,
): Promise<ModelUsageSummary> {
  try {
    return await readJson<ModelUsageSummary>(
      await request(
        `/api/knowledge-bases/${knowledgeBaseId}/evaluations/model-usage-summary`,
      ),
    );
  } catch (error) {
    if (error instanceof ChatApiError) throw error;
    throw new ChatApiError("无法读取模型调用摘要。请确认 API 已启动。");
  }
}

export async function createAnswerReview(
  knowledgeBaseId: string,
  evaluationCaseId: string,
  review: Omit<AnswerReview, "id" | "evaluation_case_id" | "citation_filenames" | "created_at">,
): Promise<AnswerReview> {
  try {
    return await readJson<AnswerReview>(
      await request(
        `/api/knowledge-bases/${knowledgeBaseId}/evaluation-cases/${evaluationCaseId}/answer-reviews`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(review),
        },
      ),
    );
  } catch (error) {
    if (error instanceof ChatApiError) throw error;
    throw new ChatApiError("无法保存答案评审。请确认 API 已启动。");
  }
}
