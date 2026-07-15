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

const reportFilename = "fastapi-official-formal-answer-batch.json";
const casesFilename = "fastapi-official-cases.jsonl";

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
    const report = JSON.parse(rawReport) as { cases: BatchCase[]; run_metadata: object };
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
