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
): Promise<ChatResponse> {
  try {
    return await readJson<ChatResponse>(
      await request("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, knowledge_base_id: knowledgeBaseId ?? null, history }),
      }),
    );
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
