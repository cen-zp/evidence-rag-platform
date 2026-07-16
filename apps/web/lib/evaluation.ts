export function parseExpectedFilenames(value: string): string[] {
  return [
    ...new Set(
      value
        .split(/[，,]/)
        .map((filename) => filename.trim())
        .filter(Boolean),
    ),
  ];
}

const reviewedKnowledgeBaseNames: Record<string, string> = {
  "FastAPI 官方文档评测语料（题集待人工复核）":
    "FastAPI 官方文档评测语料（已人工复核）",
};

export function displayKnowledgeBaseName(name: string): string {
  return reviewedKnowledgeBaseNames[name] ?? name;
}
