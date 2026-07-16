"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";

import {
  AnswerReviewSummary,
  AuthSession,
  ChatApiError,
  Citation,
  DocumentRecord,
  EndToEndLatencySummary,
  EvaluationCase,
  KnowledgeBase,
  ModelUsageSummary,
  RetrievalEvaluationReport,
  ReviewVerdict,
  createAnswerReview,
  createEvaluationCase,
  deleteEvaluationCase,
  getAnswerReviewSummary,
  getDocuments,
  getEndToEndLatencySummary,
  getEvaluationCases,
  getKnowledgeBases,
  getModelUsageSummary,
  getStoredSession,
  runRetrievalEvaluation,
  saveBrowserLatency,
  sendChatMessageStream,
} from "../../lib/chat";
import { parseExpectedFilenames } from "../../lib/evaluation";

type EvaluationAnswer = {
  evaluationCaseId: string;
  question: string;
  content: string;
  model: string;
  latencyMs: number;
  retrievalLatencyMs?: number;
  endToEndLatencyMs: number;
  citations: Citation[];
};

const verdictOptions: { value: ReviewVerdict; label: string }[] = [
  { value: "pass", label: "通过" },
  { value: "fail", label: "不通过" },
  { value: "not_applicable", label: "不适用" },
];

function rate(value: number | null): string {
  return value === null ? "—" : `${(value * 100).toFixed(1)}%`;
}

function requestErrorMessage(error: unknown, fallback: string): string {
  return error instanceof ChatApiError ? error.message : fallback;
}

function nowMs(): number {
  return globalThis.performance.now();
}

export default function EvaluationPage() {
  const [isSessionReady, setIsSessionReady] = useState(false);
  const [authSession, setAuthSession] = useState<AuthSession | null>(null);
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [selectedKnowledgeBaseId, setSelectedKnowledgeBaseId] = useState("");
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [evaluationCases, setEvaluationCases] = useState<EvaluationCase[]>([]);
  const [evaluationReport, setEvaluationReport] = useState<RetrievalEvaluationReport | null>(null);
  const [reviewSummary, setReviewSummary] = useState<AnswerReviewSummary | null>(null);
  const [modelUsage, setModelUsage] = useState<ModelUsageSummary | null>(null);
  const [latencySummary, setLatencySummary] = useState<EndToEndLatencySummary | null>(null);
  const [evaluationQuestion, setEvaluationQuestion] = useState("");
  const [expectedFilename, setExpectedFilename] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isSavingCase, setIsSavingCase] = useState(false);
  const [deletingCaseId, setDeletingCaseId] = useState<string | null>(null);
  const [isRunningEvaluation, setIsRunningEvaluation] = useState(false);
  const [answeringCaseId, setAnsweringCaseId] = useState<string | null>(null);
  const [streamPhase, setStreamPhase] = useState<string | null>(null);
  const [latestAnswer, setLatestAnswer] = useState<EvaluationAnswer | null>(null);
  const [answerVerdict, setAnswerVerdict] = useState<ReviewVerdict | "">("");
  const [citationVerdict, setCitationVerdict] = useState<ReviewVerdict | "">("");
  const [refusalVerdict, setRefusalVerdict] = useState<ReviewVerdict | "">("");
  const [reviewNotes, setReviewNotes] = useState("");
  const [isSavingReview, setIsSavingReview] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isActive = true;
    void Promise.resolve().then(async () => {
      const session = getStoredSession();
      if (!isActive) return;
      setAuthSession(session);
      setIsSessionReady(true);
      if (!session) return;

      try {
        const bases = await getKnowledgeBases();
        if (!isActive) return;
        setKnowledgeBases(bases);
        setSelectedKnowledgeBaseId(bases[0]?.id ?? "");
      } catch (loadError) {
        if (isActive) setError(requestErrorMessage(loadError, "无法加载知识库。"));
      }
    });

    return () => {
      isActive = false;
    };
  }, []);

  useEffect(() => {
    if (!selectedKnowledgeBaseId) {
      return;
    }

    let isActive = true;
    void Promise.resolve().then(async () => {
      if (!isActive) return;
      setIsLoading(true);
      setError(null);
      try {
        const [nextDocuments, nextCases, nextReview, nextUsage, nextLatency] = await Promise.all([
          getDocuments(selectedKnowledgeBaseId),
          getEvaluationCases(selectedKnowledgeBaseId),
          getAnswerReviewSummary(selectedKnowledgeBaseId),
          getModelUsageSummary(selectedKnowledgeBaseId),
          getEndToEndLatencySummary(selectedKnowledgeBaseId),
        ]);
        if (!isActive) return;
        setDocuments(nextDocuments);
        setEvaluationCases(nextCases);
        setReviewSummary(nextReview);
        setModelUsage(nextUsage);
        setLatencySummary(nextLatency);
      } catch (loadError) {
        if (isActive) setError(requestErrorMessage(loadError, "无法读取当前知识库的评测数据。"));
      } finally {
        if (isActive) setIsLoading(false);
      }
    });

    return () => {
      isActive = false;
    };
  }, [selectedKnowledgeBaseId]);

  async function submitEvaluationCase(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const question = evaluationQuestion.trim();
    const filenames = parseExpectedFilenames(expectedFilename);
    if (!selectedKnowledgeBaseId || !question || !filenames.length || isSavingCase) return;
    if (filenames.length > 10) {
      setError("每条评测案例最多填写 10 个预期来源文件名。");
      return;
    }

    setIsSavingCase(true);
    setError(null);
    try {
      const evaluationCase = await createEvaluationCase(selectedKnowledgeBaseId, question, filenames);
      setEvaluationCases((current) => [evaluationCase, ...current]);
      setEvaluationQuestion("");
      setExpectedFilename("");
      setEvaluationReport(null);
    } catch (requestError) {
      setError(requestErrorMessage(requestError, "无法保存评测案例。"));
    } finally {
      setIsSavingCase(false);
    }
  }

  async function runEvaluation() {
    if (!selectedKnowledgeBaseId || !evaluationCases.length || isRunningEvaluation) return;
    setIsRunningEvaluation(true);
    setError(null);
    try {
      setEvaluationReport(await runRetrievalEvaluation(selectedKnowledgeBaseId));
    } catch (requestError) {
      setError(requestErrorMessage(requestError, "无法运行检索评测。"));
    } finally {
      setIsRunningEvaluation(false);
    }
  }

  async function removeEvaluationCase(evaluationCase: EvaluationCase) {
    if (!selectedKnowledgeBaseId || deletingCaseId) return;
    if (!window.confirm(`删除评测案例“${evaluationCase.question}”？`)) return;
    setDeletingCaseId(evaluationCase.id);
    setError(null);
    try {
      await deleteEvaluationCase(selectedKnowledgeBaseId, evaluationCase.id);
      setEvaluationCases((current) => current.filter((item) => item.id !== evaluationCase.id));
      setEvaluationReport(null);
      if (latestAnswer?.evaluationCaseId === evaluationCase.id) setLatestAnswer(null);
    } catch (requestError) {
      setError(requestErrorMessage(requestError, "无法删除评测案例。"));
    } finally {
      setDeletingCaseId(null);
    }
  }

  async function answerEvaluationCase(evaluationCase: EvaluationCase) {
    if (!selectedKnowledgeBaseId || answeringCaseId) return;
    setAnsweringCaseId(evaluationCase.id);
    setStreamPhase("retrieving");
    setLatestAnswer(null);
    setAnswerVerdict("");
    setCitationVerdict("");
    setRefusalVerdict("");
    setReviewNotes("");
    setError(null);
    const startedAt = nowMs();

    try {
      const result = await sendChatMessageStream(
        evaluationCase.question,
        selectedKnowledgeBaseId,
        [],
        undefined,
        setStreamPhase,
      );
      const endToEndLatencyMs = Math.round(nowMs() - startedAt);
      setLatestAnswer({
        evaluationCaseId: evaluationCase.id,
        question: evaluationCase.question,
        content: result.answer,
        model: result.model,
        latencyMs: result.latency_ms,
        retrievalLatencyMs: result.retrieval_latency_ms,
        endToEndLatencyMs,
        citations: result.citations,
      });
      if (result.conversation_id && result.assistant_message_id) {
        await saveBrowserLatency(
          selectedKnowledgeBaseId,
          result.conversation_id,
          result.assistant_message_id,
          endToEndLatencyMs,
        );
      }
      const [nextUsage, nextLatency] = await Promise.all([
        getModelUsageSummary(selectedKnowledgeBaseId),
        getEndToEndLatencySummary(selectedKnowledgeBaseId),
      ]);
      setModelUsage(nextUsage);
      setLatencySummary(nextLatency);
    } catch (requestError) {
      setError(requestErrorMessage(requestError, "无法生成评测回答。"));
    } finally {
      setAnsweringCaseId(null);
      setStreamPhase(null);
    }
  }

  async function submitAnswerReview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (
      !selectedKnowledgeBaseId ||
      !latestAnswer ||
      !answerVerdict ||
      !citationVerdict ||
      !refusalVerdict ||
      isSavingReview
    ) return;

    setIsSavingReview(true);
    setError(null);
    try {
      await createAnswerReview(selectedKnowledgeBaseId, latestAnswer.evaluationCaseId, {
        answer: latestAnswer.content,
        model: latestAnswer.model,
        latency_ms: latestAnswer.latencyMs,
        citation_chunk_ids: latestAnswer.citations.map((citation) => citation.chunk_id),
        answer_verdict: answerVerdict,
        citation_verdict: citationVerdict,
        refusal_verdict: refusalVerdict,
        notes: reviewNotes.trim() || null,
      });
      setReviewSummary(await getAnswerReviewSummary(selectedKnowledgeBaseId));
      setLatestAnswer(null);
    } catch (requestError) {
      setError(requestErrorMessage(requestError, "无法保存答案评审。"));
    } finally {
      setIsSavingReview(false);
    }
  }

  if (!isSessionReady) {
    return <main className="evaluation-state">正在读取本地会话…</main>;
  }

  if (!authSession) {
    return (
      <main className="evaluation-state">
        <span className="brand-mark">E</span>
        <h1>请先登录工作台</h1>
        <p>评测管理只对已登录的本地账户开放。</p>
        <Link className="evaluation-primary-link" href="/">返回登录</Link>
      </main>
    );
  }

  return (
    <main className="evaluation-page">
      <header className="topbar">
        <Link className="brand" href="/" aria-label="返回 Evidence RAG 问答工作台">
          <span className="brand-mark">E</span>
          <span>Evidence RAG</span>
        </Link>
        <nav className="primary-nav" aria-label="主导航">
          <Link href="/">知识问答</Link>
          <Link className="active management-link" href="/evaluation">评测管理</Link>
        </nav>
        <span className="evaluation-mode">内部工具</span>
      </header>

      <section className="evaluation-shell">
        <div className="evaluation-heading">
          <div>
            <p className="eyebrow">INTERNAL QUALITY</p>
            <h1>评测管理</h1>
            <p>管理检索题集、生成待评审回答，并查看模型用量、成本与端到端耗时。</p>
          </div>
          <div className="evaluation-heading-actions">
            <label htmlFor="evaluation-knowledge-base">评测知识库</label>
            <select
              id="evaluation-knowledge-base"
              value={selectedKnowledgeBaseId}
              onChange={(event) => {
                setDocuments([]);
                setEvaluationCases([]);
                setEvaluationReport(null);
                setReviewSummary(null);
                setModelUsage(null);
                setLatencySummary(null);
                setLatestAnswer(null);
                setSelectedKnowledgeBaseId(event.target.value);
              }}
            >
              {knowledgeBases.length === 0 && <option value="">暂无知识库</option>}
              {knowledgeBases.map((knowledgeBase) => (
                <option key={knowledgeBase.id} value={knowledgeBase.id}>{knowledgeBase.name}</option>
              ))}
            </select>
            <Link className="formal-review-link" href="/review">进入 72 题人工审核</Link>
          </div>
        </div>

        {error && <p className="evaluation-error" role="alert">{error}</p>}

        {!selectedKnowledgeBaseId ? (
          <section className="evaluation-empty">
            <h2>先在知识问答工作台创建知识库</h2>
            <p>评测案例和运行记录始终绑定到一个知识库，不能在通用问答模式下创建。</p>
            <Link className="evaluation-primary-link" href="/">返回知识问答</Link>
          </section>
        ) : (
          <div className="evaluation-layout">
            <div className="evaluation-main">
              <section className="evaluation-card" aria-labelledby="retrieval-evaluation-title">
                <div className="section-heading">
                  <div>
                    <p className="eyebrow">RETRIEVAL EVALUATION</p>
                    <h2 id="retrieval-evaluation-title">检索题集</h2>
                  </div>
                  <button
                    type="button"
                    className="text-button"
                    disabled={!evaluationCases.length || isRunningEvaluation || isLoading}
                    onClick={() => void runEvaluation()}
                  >
                    {isRunningEvaluation ? "评测中" : "运行检索评测"}
                  </button>
                </div>
                <form className="evaluation-form" onSubmit={submitEvaluationCase}>
                  <label className="sr-only" htmlFor="evaluation-question">评测问题</label>
                  <input
                    id="evaluation-question"
                    value={evaluationQuestion}
                    onChange={(event) => setEvaluationQuestion(event.target.value)}
                    placeholder="评测问题"
                    maxLength={2_000}
                  />
                  <label className="sr-only" htmlFor="expected-filename">预期命中文件名</label>
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
                    disabled={!evaluationQuestion.trim() || !expectedFilename.trim() || isSavingCase}
                  >
                    {isSavingCase ? "保存中" : "新增案例"}
                  </button>
                </form>
                <p className="evaluation-summary">
                  已保存 {evaluationCases.length} 条案例。结果仅适用于当前知识库、当前题集与当前检索配置。
                </p>
                {isLoading ? (
                  <p className="panel-empty">正在读取评测数据…</p>
                ) : evaluationCases.length ? (
                  <ul className="evaluation-case-list" aria-label="评测案例">
                    {evaluationCases.map((evaluationCase) => (
                      <li key={evaluationCase.id}>
                        <div>
                          <p>{evaluationCase.question}</p>
                          <span>预期：{evaluationCase.expected_filenames.join("、")}</span>
                        </div>
                        <div className="evaluation-case-actions">
                          <button
                            type="button"
                            disabled={answeringCaseId !== null}
                            onClick={() => void answerEvaluationCase(evaluationCase)}
                          >
                            {answeringCaseId === evaluationCase.id
                              ? streamPhase === "retrieving" ? "检索中" : "生成中"
                              : "生成并评审"}
                          </button>
                          <button
                            type="button"
                            className="delete-evaluation-case"
                            disabled={deletingCaseId !== null}
                            onClick={() => void removeEvaluationCase(evaluationCase)}
                          >
                            {deletingCaseId === evaluationCase.id ? "删除中" : "删除"}
                          </button>
                        </div>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="panel-empty">添加问题和预期来源后，才能运行检索评测。</p>
                )}
              </section>

              {latestAnswer && (
                <section className="evaluation-card" aria-labelledby="answer-review-title">
                  <p className="eyebrow">ANSWER REVIEW</p>
                  <h2 id="answer-review-title">本次回答与人工判断</h2>
                  <p className="evaluation-question">{latestAnswer.question}</p>
                  <p className="evaluation-answer">{latestAnswer.content}</p>
                  <p className="answer-review-meta">
                    {latestAnswer.model} · 模型 {latestAnswer.latencyMs} ms
                    {latestAnswer.retrievalLatencyMs === undefined ? "" : ` · 检索 ${latestAnswer.retrievalLatencyMs} ms`}
                    {` · 浏览器端到端 ${latestAnswer.endToEndLatencyMs} ms`}
                  </p>
                  {latestAnswer.citations.length ? (
                    <ol className="evaluation-citations">
                      {latestAnswer.citations.map((citation) => (
                        <li key={citation.chunk_id}>
                          <strong>{citation.filename}</strong>
                          <p>{citation.content}</p>
                        </li>
                      ))}
                    </ol>
                  ) : (
                    <p className="panel-empty">本次回答没有返回已校验证据。</p>
                  )}
                  <form className="answer-review-form" onSubmit={submitAnswerReview}>
                    {[
                      ["answer", "答案是否符合参考资料或预期回答？", answerVerdict, setAnswerVerdict],
                      ["citation", "引用是否足以支持本次回答？", citationVerdict, setCitationVerdict],
                      ["refusal", "证据不足时，拒答是否恰当？", refusalVerdict, setRefusalVerdict],
                    ].map(([name, legend, value, setter]) => (
                      <fieldset key={name as string}>
                        <legend>{legend as string}</legend>
                        {verdictOptions.map((option) => (
                          <label key={`${name}-${option.value}`}>
                            <input
                              type="radio"
                              name={`${name}-verdict`}
                              checked={value === option.value}
                              onChange={() => (setter as (next: ReviewVerdict) => void)(option.value)}
                            />
                            {option.label}
                          </label>
                        ))}
                      </fieldset>
                    ))}
                    <label className="sr-only" htmlFor="answer-review-notes">评审备注</label>
                    <textarea
                      id="answer-review-notes"
                      value={reviewNotes}
                      onChange={(event) => setReviewNotes(event.target.value)}
                      placeholder="可选：记录错误类型、遗漏证据或改进建议"
                      maxLength={2_000}
                      rows={3}
                    />
                    <div className="answer-review-actions">
                      <button type="button" onClick={() => setLatestAnswer(null)}>取消</button>
                      <button
                        type="submit"
                        disabled={isSavingReview || !answerVerdict || !citationVerdict || !refusalVerdict}
                      >
                        {isSavingReview ? "保存中" : "保存人工评审"}
                      </button>
                    </div>
                  </form>
                </section>
              )}
            </div>

            <aside className="evaluation-insights" aria-label="评测结果与运行记录">
              <section className="evaluation-card">
                <p className="eyebrow">RETRIEVAL RESULT</p>
                <h2>最近一次检索评测</h2>
                {evaluationReport ? (
                  <dl className="evaluation-report">
                    <div><dt>案例数</dt><dd>{evaluationReport.case_count}</dd></div>
                    <div><dt>Recall@{evaluationReport.top_k}</dt><dd>{rate(evaluationReport.recall_at_k)}</dd></div>
                    <div><dt>MRR</dt><dd>{evaluationReport.mean_reciprocal_rank.toFixed(3)}</dd></div>
                    <div><dt>平均 / P95</dt><dd>{evaluationReport.mean_latency_ms.toFixed(1)} / {evaluationReport.p95_latency_ms.toFixed(1)} ms</dd></div>
                  </dl>
                ) : <p className="panel-empty">本页尚未运行检索评测。</p>}
              </section>

              <section className="evaluation-card">
                <p className="eyebrow">HUMAN REVIEW</p>
                <h2>人工评审覆盖</h2>
                {reviewSummary && (
                  <dl className="answer-review-summary">
                    <div><dt>已评 / 未覆盖</dt><dd>{reviewSummary.review_count} / {reviewSummary.unreviewed_case_count}</dd></div>
                    <div><dt>答案通过</dt><dd>{rate(reviewSummary.answer_pass_rate)}</dd></div>
                    <div><dt>引用支持</dt><dd>{rate(reviewSummary.citation_pass_rate)}</dd></div>
                    <div><dt>拒答恰当</dt><dd>{rate(reviewSummary.refusal_pass_rate)}</dd></div>
                  </dl>
                )}
                <Link className="evaluation-secondary-link" href="/review">打开 72 题人工审核工具</Link>
              </section>

              <section className="evaluation-card">
                <p className="eyebrow">MODEL USAGE</p>
                <h2>模型用量与成本</h2>
                {modelUsage && (
                  <dl className="model-usage-summary">
                    <div><dt>已记录调用</dt><dd>{modelUsage.call_count} 次</dd></div>
                    <div><dt>累计 token</dt><dd>{modelUsage.total_tokens}</dd></div>
                    <div><dt>平均模型耗时</dt><dd>{modelUsage.mean_latency_ms === null ? "—" : `${modelUsage.mean_latency_ms.toFixed(1)} ms`}</dd></div>
                    <div><dt>累计估算成本</dt><dd>{modelUsage.total_estimated_cost === null ? "未配置" : `${modelUsage.total_estimated_cost.toFixed(6)} ${modelUsage.estimated_cost_currency}`}</dd></div>
                  </dl>
                )}
                <p className="model-usage-note">仅统计成功的知识库问答调用。成本来自调用时保存的本地单价快照，不代表回答质量。</p>
              </section>

              <section className="evaluation-card">
                <p className="eyebrow">END-TO-END LATENCY</p>
                <h2>回答耗时</h2>
                {latencySummary && (
                  <dl className="model-usage-summary">
                    <div><dt>回答 / 拒答</dt><dd>{latencySummary.answered_count} / {latencySummary.guarded_count}</dd></div>
                    <div><dt>平均检索</dt><dd>{latencySummary.mean_retrieval_latency_ms === null ? "—" : `${latencySummary.mean_retrieval_latency_ms.toFixed(1)} ms`}</dd></div>
                    <div><dt>平均服务端全链路</dt><dd>{latencySummary.mean_server_total_latency_ms === null ? "—" : `${latencySummary.mean_server_total_latency_ms.toFixed(1)} ms`}</dd></div>
                    <div><dt>平均浏览器端到端</dt><dd>{latencySummary.mean_browser_end_to_end_latency_ms === null ? "—" : `${latencySummary.mean_browser_end_to_end_latency_ms.toFixed(1)} ms`}</dd></div>
                  </dl>
                )}
                <p className="model-usage-note">浏览器端到端耗时从发起 SSE 到收到并解析最终结果；旧消息可能没有该字段。</p>
              </section>
            </aside>
          </div>
        )}
      </section>
    </main>
  );
}
