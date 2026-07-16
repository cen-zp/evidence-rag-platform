---
name: Evidence RAG workbench
source_template: linear.app (adapted)
---

# Evidence RAG workbench

## Intent

This is a focused knowledge tool, not a marketing page. It should make the
distinction between an AI answer and supporting evidence easy to inspect. The
main workbench must make the current scope obvious: without a selected knowledge
base it is general chat; with a selected knowledge base it is a
retrieval-grounded answer surface with inspectable evidence. Internal quality
workflows belong to a separate management route and must not interrupt this
ordinary question-answering flow.

## Visual system

- Use a near-black canvas (`#010102`) with elevated charcoal panels
  (`#0f1011`, `#141516`) and 1px borders (`#23252a`).
- Use `#5e6ad2` as the single product accent for the send action, active state,
  and keyboard focus. Reserve green (`#27a644`) for healthy service status.
- Use a system sans stack for Chinese and Latin text; use a system monospace
  stack only for model, latency, and API metadata.
- Keep corners restrained: 8px for controls and 12px for panels. Avoid
  gradients, decorative illustration, or loud shadows.
- Preserve a dense desktop workspace layout, then collapse the secondary
  inspection column beneath chat on narrow screens.

## Chat states

- Empty: explain whether the current mode is direct-model chat or evidence
  question answering, then present example questions.
- Sending: disable the composer and show a clear in-progress state.
- Success: render the answer and validated evidence without exposing internal
  model, token, cost, or latency records; those remain inspectable under the
  evaluation management route.
- Failure: keep the draft message, explain that the API or its local key may
  be unavailable, and avoid exposing secrets or raw provider details.
- Follow-up: retain a small, explicitly disclosed page-local context window;
  clear it when the knowledge-base scope changes.

## Evidence panel

The panel is part of the product contract. It includes compact knowledge-base
selection, document processing status, and an explicit empty state until a
grounded answer exists. When citations exist, render only server-validated
document snippets and locations; never simulate sources. Failed documents show
a compact error and retry action, while pending and processing documents never
offer a duplicate enqueue action.

## Evaluation management

The main workbench contains only knowledge questions, knowledge-base and
document status, and server-validated evidence. Retrieval evaluation, the
72-case formal human-review tool, and model usage, cost, and latency summaries
live under the separate `/evaluation` management route. The top bar may expose
a quiet "评测管理" link, but "知识问答" remains the primary navigation item.

On the management route, users add a question and expected source filename,
then inspect Recall@K, MRR, and local retrieval latency. Treat every result as
scoped to its current knowledge base, case set, and retrieval configuration; do
not present a small smoke run as a general performance claim. Show a deliberate
delete action so incorrect cases can be removed before they contaminate a run.
Keep the ability to generate an answer from an evaluation case and record a
human verdict on that route rather than sending the user back through the main
workbench. Model metadata must state that it covers successful grounded calls,
stores no question or answer content, and is not a quality claim; estimated
costs must be labeled as local pricing snapshots rather than billing truth.
