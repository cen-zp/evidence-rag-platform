import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import path from "node:path";

import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

type SourceCase = {
  id: string;
  expected_filenames: string[];
};

type BatchCase = {
  case_id: string;
  question: string;
  reference_answer: string | null;
  outcome: string;
  answer: string;
  citations: { chunk_id: string; filename: string; content: string }[];
  model: string | null;
  model_latency_ms: number | null;
  retrieval_latency_ms: number;
};

const reportFilename = "fastapi-official-formal-answer-compact-s1-20260715.json";
const casesFilename = "fastapi-official-cases.jsonl";
const expectedBatchId = "02dbf511-6853-4dac-b420-779d74befa9c";
const expectedReportSha256 = "0050e4ed89e394a278a955da240d6545a24419286fe777e96cd2f5542db55fef";
const reviewBatch = {
  id: expectedBatchId,
  label: "短引用键批次 · 现存可审计报告",
  reportSha256: expectedReportSha256,
  downloadFilename: "fastapi-official-formal-answer-compact-s1-02dbf511-review-human.csv",
};

async function readReviewData(filename: string, sourcePath: string): Promise<string> {
  const candidates = [
    path.join(process.cwd(), "review-data", filename),
    path.resolve(process.cwd(), sourcePath),
  ];
  let lastError: unknown;
  for (const candidate of candidates) {
    try {
      return await readFile(candidate, "utf8");
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError;
}

export async function GET() {
  try {
    const [rawReport, rawCases] = await Promise.all([
      readReviewData(reportFilename, `../../evals/results/${reportFilename}`),
      readReviewData(casesFilename, `../../evals/independent/${casesFilename}`),
    ]);
    const report = JSON.parse(rawReport) as {
      batch_id: string;
      case_count: number;
      cases: BatchCase[];
      run_metadata: object;
    };
    const reportSha256 = createHash("sha256").update(rawReport).digest("hex");
    if (
      report.batch_id !== expectedBatchId ||
      reportSha256 !== expectedReportSha256 ||
      report.case_count !== 72 ||
      report.cases.length !== report.case_count
    ) {
      return NextResponse.json(
        { detail: "审核批次完整性校验失败，已停止加载以避免串批。" },
        { status: 409 },
      );
    }
    const sources = new Map(
      rawCases
        .trim()
        .split("\n")
        .map((line) => JSON.parse(line) as SourceCase)
        .map((item) => [item.id, item] as const),
    );

    return NextResponse.json(
      {
        cases: report.cases.map((item) => ({
          ...item,
          expected_filenames: sources.get(item.case_id)?.expected_filenames ?? [],
        })),
        run_metadata: report.run_metadata,
        batch: reviewBatch,
      },
      { headers: { "Cache-Control": "no-store" } },
    );
  } catch {
    return NextResponse.json(
      { detail: "正式审核数据不可用。请确认 Web 服务已使用项目当前镜像启动。" },
      { status: 503 },
    );
  }
}
