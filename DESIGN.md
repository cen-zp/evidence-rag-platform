---
name: Evidence RAG workbench
source_template: linear.app (adapted)
---

# Evidence RAG workbench

## Intent

This is a focused internal knowledge tool, not a marketing page. It should make
the distinction between an AI answer and supporting evidence easy to inspect.
The initial chat screen must also be honest about its current scope: before
document retrieval is implemented, it is a direct-model chat rather than a
retrieval-grounded answer.

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

- Empty: explain that the current milestone sends a direct model request and
  present example questions.
- Sending: disable the composer and show a clear in-progress state.
- Success: render the answer, model name, and measured latency as separate,
  inspectable information.
- Failure: keep the draft message, explain that the API or its local key may
  be unavailable, and avoid exposing secrets or raw provider details.

## Evidence panel

The panel is part of the product contract, even though citations are not
available in this milestone. Show an explicit "not connected yet" state rather
than simulated sources. When the RAG pipeline exists, this area will render
validated document snippets, locations, and confidence signals.
