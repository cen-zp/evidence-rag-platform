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
};

export type ChatHistoryMessage = {
  role: "user" | "assistant";
  content: string;
};

export type HealthResponse = {
  status: string;
  environment: string;
};

export type KnowledgeBase = {
  id: string;
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
    return await readJson<HealthResponse>(await fetch(`${apiBaseUrl}/health`));
  } catch (error) {
    if (error instanceof ChatApiError) throw error;
    throw new ChatApiError("API 不可用");
  }
}

export async function sendChatMessage(
  message: string,
  knowledgeBaseId?: string,
  history: ChatHistoryMessage[] = [],
): Promise<ChatResponse> {
  try {
    return await readJson<ChatResponse>(
      await fetch(`${apiBaseUrl}/api/chat`, {
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
    return await readJson<KnowledgeBase[]>(await fetch(`${apiBaseUrl}/api/knowledge-bases`));
  } catch (error) {
    if (error instanceof ChatApiError) throw error;
    throw new ChatApiError("无法加载知识库。请确认 API 已启动。");
  }
}

export async function createKnowledgeBase(name: string): Promise<KnowledgeBase> {
  try {
    return await readJson<KnowledgeBase>(
      await fetch(`${apiBaseUrl}/api/knowledge-bases`, {
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

export async function getDocuments(knowledgeBaseId: string): Promise<DocumentRecord[]> {
  try {
    return await readJson<DocumentRecord[]>(
      await fetch(`${apiBaseUrl}/api/knowledge-bases/${knowledgeBaseId}/documents`),
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
      await fetch(`${apiBaseUrl}/api/knowledge-bases/${knowledgeBaseId}/documents`, {
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
      await fetch(
        `${apiBaseUrl}/api/knowledge-bases/${knowledgeBaseId}/documents/${documentId}/retry`,
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
      await fetch(`${apiBaseUrl}/api/knowledge-bases/${knowledgeBaseId}/evaluation-cases`),
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
      await fetch(`${apiBaseUrl}/api/knowledge-bases/${knowledgeBaseId}/evaluation-cases`, {
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
    const response = await fetch(
      `${apiBaseUrl}/api/knowledge-bases/${knowledgeBaseId}/evaluation-cases/${evaluationCaseId}`,
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
      await fetch(
        `${apiBaseUrl}/api/knowledge-bases/${knowledgeBaseId}/evaluations/retrieval?top_k=${topK}`,
        { method: "POST" },
      ),
    );
  } catch (error) {
    if (error instanceof ChatApiError) throw error;
    throw new ChatApiError("无法运行评测。请确认 API 与 Qdrant 已启动。");
  }
}
