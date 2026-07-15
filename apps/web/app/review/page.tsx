"use client";

import Link from "next/link";
import { startTransition, useEffect, useMemo, useState } from "react";

import styles from "./review.module.css";

type Verdict = "pass" | "fail";
type ReviewOutcome = "answered" | "guarded";

type ReviewCase = {
  case_id: string;
  question: string;
  reference_answer: string | null;
  expected_filenames: string[];
  outcome: string;
  answer: string;
  citations: { chunk_id: string; filename: string; content: string }[];
  model: string | null;
  model_latency_ms: number | null;
  retrieval_latency_ms: number;
};

type ReviewDraft = {
  answerVerdict?: Verdict;
  citationVerdict?: Verdict;
  refusalVerdict?: Verdict;
  notes?: string;
  reviewedAt?: string;
};

type StoredReview = {
  reviewerAlias: string;
  drafts: Record<string, ReviewDraft>;
};

type ReviewBatch = {
  id: string;
  label: string;
  reportSha256: string;
  downloadFilename: string;
};

const storageKey = "evidence-rag:formal-answer-review:02dbf511:v1";
const requiredHeaders = [
  "case_id",
  "question",
  "reference_answer",
  "answer",
  "citation_filenames",
  "citation_chunk_ids",
  "model",
  "model_latency_ms",
  "retrieval_latency_ms",
  "outcome",
  "review_status",
  "review_method",
  "answer_verdict",
  "citation_verdict",
  "refusal_verdict",
  "reviewer_alias",
  "reviewed_at_utc",
  "notes",
];

function isExcluded(item: ReviewCase): boolean {
  return item.outcome === "provider_error" || item.outcome === "retrieval_error";
}

function reviewOutcome(item: ReviewCase): ReviewOutcome {
  return item.outcome === "answered" ? "answered" : "guarded";
}

function isComplete(item: ReviewCase, draft?: ReviewDraft): boolean {
  if (isExcluded(item)) return true;
  if (!draft) return false;
  return reviewOutcome(item) === "answered"
    ? Boolean(draft.answerVerdict && draft.citationVerdict)
    : Boolean(draft.refusalVerdict);
}

function csvCell(value: string | number | null | undefined): string {
  const text = value == null ? "" : String(value);
  return /[",\n\r]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

function createCsv(cases: ReviewCase[], drafts: Record<string, ReviewDraft>, reviewerAlias: string) {
  const reviewedAt = new Date().toISOString();
  const rows = cases.map((item) => {
    const draft = drafts[item.case_id];
    const excluded = isExcluded(item);
    const columns = [
      item.case_id,
      item.question,
      item.reference_answer ?? "",
      item.answer,
      item.citations.map((citation) => citation.filename).join("; "),
      item.citations.map((citation) => citation.chunk_id).join("; "),
      item.model ?? "",
      item.model_latency_ms ?? "",
      item.retrieval_latency_ms,
      item.outcome,
      "approved",
      "human",
      excluded ? "not_applicable" : reviewOutcome(item) === "answered" ? draft?.answerVerdict : "not_applicable",
      excluded ? "not_applicable" : reviewOutcome(item) === "answered" ? draft?.citationVerdict : "not_applicable",
      excluded ? "not_applicable" : reviewOutcome(item) === "guarded" ? draft?.refusalVerdict : "not_applicable",
      reviewerAlias,
      draft?.reviewedAt ?? reviewedAt,
      excluded ? "Excluded: provider or retrieval error; no answer to review." : draft?.notes ?? "",
    ].map(csvCell);
    return columns.join(",");
  });
  return `\uFEFF${requiredHeaders.join(",")}\n${rows.join("\n")}\n`;
}

export default function FormalReviewPage() {
  const [cases, setCases] = useState<ReviewCase[]>([]);
  const [drafts, setDrafts] = useState<Record<string, ReviewDraft>>({});
  const [reviewerAlias, setReviewerAlias] = useState("");
  const [currentIndex, setCurrentIndex] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [batch, setBatch] = useState<ReviewBatch | null>(null);

  useEffect(() => {
    try {
      const saved = localStorage.getItem(storageKey);
      if (saved) {
        const parsed = JSON.parse(saved) as StoredReview;
        startTransition(() => {
          setReviewerAlias(parsed.reviewerAlias ?? "");
          setDrafts(parsed.drafts ?? {});
        });
      }
    } catch {
      localStorage.removeItem(storageKey);
    }
    void fetch("/api/formal-answer-review")
      .then(async (response) => {
        const payload = (await response.json()) as {
          cases?: ReviewCase[];
          batch?: ReviewBatch;
          detail?: string;
        };
        if (!response.ok || !payload.cases || !payload.batch) {
          throw new Error(payload.detail ?? "无法加载审核题集。");
        }
        setCases(payload.cases);
        setBatch(payload.batch);
      })
      .catch((loadError: unknown) => {
        setError(loadError instanceof Error ? loadError.message : "无法加载审核题集。");
      })
      .finally(() => setIsLoading(false));
  }, []);

  useEffect(() => {
    localStorage.setItem(storageKey, JSON.stringify({ reviewerAlias, drafts }));
  }, [drafts, reviewerAlias]);

  const reviewableCases = useMemo(() => cases.filter((item) => !isExcluded(item)), [cases]);
  const completedCount = useMemo(
    () => reviewableCases.filter((item) => isComplete(item, drafts[item.case_id])).length,
    [drafts, reviewableCases],
  );
  const currentCase = reviewableCases[currentIndex];
  const currentDraft = currentCase ? drafts[currentCase.case_id] : undefined;

  function updateDraft(caseId: string, update: Partial<ReviewDraft>) {
    setDrafts((current) => ({
      ...current,
      [caseId]: { ...current[caseId], ...update, reviewedAt: new Date().toISOString() },
    }));
  }

  function move(offset: number) {
    setCurrentIndex((index) => Math.max(0, Math.min(reviewableCases.length - 1, index + offset)));
  }

  function goToNextPending() {
    const nextIndex = reviewableCases.findIndex((item, index) =>
      index > currentIndex && !isComplete(item, drafts[item.case_id]),
    );
    move(nextIndex === -1 ? 1 : nextIndex - currentIndex);
  }

  function exportReview() {
    if (!reviewerAlias.trim()) {
      setError("请先填写你的评审别名，例如 reviewer-zhang。");
      return;
    }
    if (completedCount !== reviewableCases.length) {
      setError(`还有 ${reviewableCases.length - completedCount} 条需要判断。`);
      return;
    }
    const blob = new Blob([createCsv(cases, drafts, reviewerAlias.trim())], {
      type: "text/csv;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = batch?.downloadFilename ?? "formal-answer-review-human.csv";
    anchor.click();
    URL.revokeObjectURL(url);
    setError(null);
  }

  if (isLoading) {
    return <main className={styles.state}>正在加载真人审核题集…</main>;
  }
  if (error && !currentCase) {
    return <main className={styles.state}>{error}</main>;
  }
  if (!currentCase) {
    return <main className={styles.state}>审核题集为空。</main>;
  }

  const guarded = reviewOutcome(currentCase) === "guarded";
  const progress = Math.round((completedCount / reviewableCases.length) * 100);

  return (
    <main className={styles.page}>
      <header className={styles.topbar}>
        <Link className={styles.brand} href="/">
          <span className={styles.brandMark}>E</span>
          Evidence RAG Platform
        </Link>
        <span className={styles.mode}>{batch?.label ?? "真人审核"} · 本地草稿</span>
      </header>

      <section className={styles.shell}>
        <aside className={styles.sidebar}>
          <p className={styles.eyebrow}>FORMAL REVIEW · SHORT KEYS</p>
          <h1>短引用键批次逐题审核</h1>
          <p className={styles.muted}>只判断，不改写模型回答。浏览器会按批次自动保存草稿。</p>
          {batch && (
            <p className={styles.rule}>
              批次 {batch.id.slice(0, 8)} · 报告 {batch.reportSha256.slice(0, 8)}
            </p>
          )}
          <label className={styles.aliasLabel} htmlFor="reviewer-alias">评审别名</label>
          <input
            id="reviewer-alias"
            value={reviewerAlias}
            onChange={(event) => setReviewerAlias(event.target.value)}
            placeholder="例如 reviewer-zhang"
          />
          <div className={styles.progressText}>
            <strong>{completedCount}</strong> / {reviewableCases.length} 已完成
          </div>
          <div className={styles.progressTrack} aria-label={`已完成 ${progress}%`}>
            <span style={{ width: `${progress}%` }} />
          </div>
          <p className={styles.rule}>回答题：判断答案和引用。拒答题：只判断拒答是否合理。</p>
          <button className={styles.export} onClick={exportReview}>下载真人审核 CSV</button>
          {error && <p className={styles.error}>{error}</p>}
        </aside>

        <section className={styles.card} aria-live="polite">
          <div className={styles.cardHeader}>
            <div>
              <p className={styles.eyebrow}>CASE {currentIndex + 1} / {reviewableCases.length}</p>
              <span className={guarded ? styles.guardTag : styles.answerTag}>
                {guarded ? "系统拒答" : "模型已回答"}
              </span>
            </div>
            <span className={styles.caseId}>{currentCase.case_id}</span>
          </div>

          <section className={styles.block}>
            <h2>问题</h2>
            <p>{currentCase.question}</p>
          </section>
          <section className={styles.block}>
            <h2>参考要点</h2>
            <p>{currentCase.reference_answer ?? "本题没有参考答案。"}</p>
            <p className={styles.sourceHint}>预期资料：{currentCase.expected_filenames.join("、") || "未标注"}</p>
          </section>
          <section className={styles.block}>
            <h2>{guarded ? "系统返回" : "模型回答"}</h2>
            <p className={styles.answer}>{currentCase.answer || "（无回答）"}</p>
            <p className={styles.meta}>{currentCase.model ?? "无模型输出"} · {currentCase.model_latency_ms ?? "—"} ms</p>
          </section>

          {!guarded && (
            <section className={styles.block}>
              <h2>服务端校验后的引用</h2>
              {currentCase.citations.map((citation) => (
                <article className={styles.citation} key={citation.chunk_id}>
                  <strong>{citation.filename}</strong>
                  <p>{citation.content}</p>
                </article>
              ))}
            </section>
          )}

          <section className={styles.decision}>
            {guarded ? (
              <>
                <p>资料确实不足时选“合理”；若预期资料足以回答，选“不当”。</p>
                <div className={styles.buttons}>
                  <button
                    className={currentDraft?.refusalVerdict === "pass" ? styles.selectedPass : ""}
                    onClick={() => updateDraft(currentCase.case_id, { refusalVerdict: "pass" })}
                  >拒答合理</button>
                  <button
                    className={currentDraft?.refusalVerdict === "fail" ? styles.selectedFail : ""}
                    onClick={() => updateDraft(currentCase.case_id, { refusalVerdict: "fail" })}
                  >拒答不当</button>
                </div>
              </>
            ) : (
              <>
                <p>先判断回答是否符合参考要点，再判断引用是否足够支持回答。</p>
                <div className={styles.quickDecision}>
                  <button
                    className={
                      currentDraft?.answerVerdict === "pass" && currentDraft.citationVerdict === "pass"
                        ? styles.selectedPass
                        : ""
                    }
                    onClick={() => updateDraft(currentCase.case_id, {
                      answerVerdict: "pass",
                      citationVerdict: "pass",
                    })}
                  >答案与引用均通过</button>
                  <span>若任一项有问题，再在下方单独标记。</span>
                </div>
                <div className={styles.row}><span>答案</span><div className={styles.buttons}>
                  <button className={currentDraft?.answerVerdict === "pass" ? styles.selectedPass : ""} onClick={() => updateDraft(currentCase.case_id, { answerVerdict: "pass" })}>通过</button>
                  <button className={currentDraft?.answerVerdict === "fail" ? styles.selectedFail : ""} onClick={() => updateDraft(currentCase.case_id, { answerVerdict: "fail" })}>不通过</button>
                </div></div>
                <div className={styles.row}><span>引用</span><div className={styles.buttons}>
                  <button className={currentDraft?.citationVerdict === "pass" ? styles.selectedPass : ""} onClick={() => updateDraft(currentCase.case_id, { citationVerdict: "pass" })}>通过</button>
                  <button className={currentDraft?.citationVerdict === "fail" ? styles.selectedFail : ""} onClick={() => updateDraft(currentCase.case_id, { citationVerdict: "fail" })}>不通过</button>
                </div></div>
              </>
            )}
            <textarea
              value={currentDraft?.notes ?? ""}
              onChange={(event) => updateDraft(currentCase.case_id, { notes: event.target.value })}
              placeholder="可选：失败原因或依据位置"
              aria-label="评审备注"
            />
          </section>

          <footer className={styles.navigation}>
            <button onClick={() => move(-1)} disabled={currentIndex === 0}>上一题</button>
            <button onClick={goToNextPending} disabled={currentIndex === reviewableCases.length - 1}>下一题 / 下一个待审</button>
          </footer>
        </section>
      </section>
    </main>
  );
}
