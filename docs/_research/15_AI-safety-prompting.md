# AI Safety and Prompt Workflow Requirements - Research Note

Date: 2026-07-02

## Status

Holds. Any model-backed workflow must be specified as a separate, auditable workflow contract before implementation. The goal is to provide truthful context for legitimate users and reduce avoidable false-positive refusals, not to bypass or weaken model safety systems.

## Sources Checked

- Anthropic Claude Platform, "Stop reasons and fallback": `https://platform.claude.com/docs/en/build-with-claude/handling-stop-reasons`
- Anthropic Claude Platform, "Streaming refusals": `https://platform.claude.com/docs/en/test-and-evaluate/strengthen-guardrails/handle-streaming-refusals`
- OpenAI API, "Structured model outputs": `https://developers.openai.com/api/docs/guides/structured-outputs`
- OpenAI API, "Reasoning models": `https://developers.openai.com/api/docs/guides/reasoning`
- OWASP GenAI Security Project, "2025 Top 10 Risk & Mitigations for LLMs and Gen AI Apps": `https://genai.owasp.org/llm-top-10/`
- OWASP Large Language Model Security Verification Standard: `https://owasp.org/www-project-llm-verification-standard/`
- OWASP Artificial Intelligence Security Verification Standard repository: `https://github.com/OWASP/AISVS`
- NIST AI 600-1, "Artificial Intelligence Risk Management Framework: Generative Artificial Intelligence Profile": `https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence`
- ISO/IEC 42001:2023, "AI management systems": `https://www.iso.org/standard/42001`

## Findings

1. **Refusals are normal model outcomes, not transport failures.** Anthropic documents `stop_reason` as part of successful Messages API responses, with `refusal` as a possible value. Streaming refusals are successful responses and must be handled explicitly, including context reset before continuing the same conversation.
2. **Structured output does not remove the need for refusal handling.** OpenAI Structured Outputs make refusals programmatically detectable, and a refusal may not follow the requested JSON schema. The application must check refusal content before parsing or trusting structured data.
3. **Raw hidden reasoning must not be requested.** OpenAI reasoning docs describe internal reasoning tokens and supported reasoning summaries. Prompt specs should request concise rationale, assumptions, evidence, or supported reasoning summaries instead of chain-of-thought disclosure.
4. **LLM security standards require lifecycle controls, not only prompt text.** OWASP LLM Top 10 2025 highlights prompt injection, sensitive information disclosure, improper output handling, excessive agency, system prompt leakage, and unbounded consumption. OWASP LLMSVS/AISVS frame these as testable application security controls.
5. **Governance standards require explicit risk management.** NIST AI 600-1 and ISO/IEC 42001 support documenting AI lifecycle risk, context of use, risk treatment, monitoring, and human accountability.

## Decision

Create a dedicated AI workflow safety specification and require one file per model-backed workflow. Sensitive domains must be split by use case and must explicitly state:

- legitimate user group,
- permitted environment,
- defensive, educational, or otherwise lawful purpose,
- operational boundaries,
- human review requirements,
- refusal and fallback behavior.

Cybersecurity workflows are permitted only for defensive, detection, hardening, logging, patching, triage, or clearly authorized testing contexts. The specs must prohibit malware, persistence, credential theft, real third-party exploitation, evasion, and bypassing security controls.
