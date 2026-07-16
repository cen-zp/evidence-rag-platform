import assert from "node:assert/strict";
import test from "node:test";

import { displayKnowledgeBaseName, parseExpectedFilenames } from "./evaluation.ts";

test("parseExpectedFilenames normalizes Chinese commas and removes duplicates", () => {
  assert.deepEqual(
    parseExpectedFilenames("guide.pdf， notes.md,guide.pdf,  handbook.docx  "),
    ["guide.pdf", "notes.md", "handbook.docx"],
  );
});

test("displayKnowledgeBaseName marks the reviewed FastAPI corpus as complete", () => {
  assert.equal(
    displayKnowledgeBaseName("FastAPI 官方文档评测语料（题集待人工复核）"),
    "FastAPI 官方文档评测语料（已人工复核）",
  );
  assert.equal(displayKnowledgeBaseName("产品文档"), "产品文档");
});
