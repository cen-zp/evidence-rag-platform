export type ChatResponse = {
  answer: string;
  model: string;
  latency_ms: number;
};

export type HealthResponse = {
  status: string;
  environment: string;
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

export async function getApiHealth(): Promise<HealthResponse> {
  try {
    const response = await fetch(`${apiBaseUrl}/health`);
    if (!response.ok) throw new Error("Health check failed");
    return (await response.json()) as HealthResponse;
  } catch {
    throw new ChatApiError("API 不可用");
  }
}

export async function sendChatMessage(message: string): Promise<ChatResponse> {
  let response: Response;

  try {
    response = await fetch(`${apiBaseUrl}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });
  } catch {
    throw new ChatApiError("无法连接 API。请确认 FastAPI 已在 http://localhost:8000 启动。");
  }

  if (!response.ok) {
    throw new ChatApiError(
      response.status === 503
        ? "模型服务尚未配置。请只在项目根目录的 .env 中填写新的密钥。"
        : "本次请求未完成，请稍后重试。",
    );
  }

  return (await response.json()) as ChatResponse;
}
