# AI Workflow Specs

This directory contains one file per approved or proposed model-backed workflow.

Current status: **no AI workflows are approved for Syncbox v1**.

## Registry

| Workflow | Status | Notes |
|---|---|---|
| None | Not approved | Syncbox v1 remains deterministic unless the owner approves a split workflow spec. |

## Rules

- Start from `_TEMPLATE.md`.
- Keep one workflow per file.
- Write all workflow prompts with `<role>`, `<context>`, `<allowed_scope>`, `<disallowed_scope>`, `<input>`, and `<output_requirements>`.
- State the legitimate user group, permitted environment, lawful purpose, boundaries, refusal behavior, fallback behavior, and human review requirement.
- Do not implement a model-backed workflow until its spec is approved.
