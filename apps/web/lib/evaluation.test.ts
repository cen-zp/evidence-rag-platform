import assert from "node:assert/strict";
import test from "node:test";

import { parseExpectedFilenames } from "./evaluation.ts";

test("parseExpectedFilenames normalizes Chinese commas and removes duplicates", () => {
  assert.deepEqual(
    parseExpectedFilenames("guide.pdf， notes.md,guide.pdf,  handbook.docx  "),
    ["guide.pdf", "notes.md", "handbook.docx"],
  );
});
