---
name: Evidence RAG workbench
source_template: linear.app (adapted)
---

# Evidence RAG workbench

## Intent

This is a focused internal knowledge tool, not a marketing page. It should make
the distinction between an AI answer and supporting evidence easy to inspect.
The workbench must make the current scope obvious: without a selected knowledge
base it is direct-model chat; with a selected knowledge base it is a
retrieval-grounded answer surface with inspectable evidence.

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
- Success: render the answer, model name, and measured latency as separate,
  inspectable information.
- Failure: keep the draft message, explain that the API or its local key may
  be unavailable, and avoid exposing secrets or raw provider details.

## Evidence panel

The panel is part of the product contract. It includes compact knowledge-base
selection, document processing status, and an explicit empty state until a
grounded answer exists. When citations exist, render only server-validated
document snippets and locations; never simulate sources.

## Evaluation panel

Keep retrieval evaluation close to the document status: users add a question
and the expected source filename, then inspect Recall@K, MRR, and local
retrieval latency. Treat every result as scoped to its current knowledge base,
case set, and retrieval configuration; do not present a small smoke run as a
general performance claim.
