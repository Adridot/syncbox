# Syncbox - AI Workflow Safety Specification

## Authority

This document governs every model-backed workflow, prompt, agent action, AI-generated user-facing output, and model fallback in Syncbox.

Current v1 status: **no AI model workflow is approved**. Syncbox v1 may not add an AI feature unless a separate workflow spec is created under `docs/ai-workflows/`, reviewed, and approved before implementation.

If this document conflicts with product behavior in `SPEC-UNIFIED.md`, `SPEC-UNIFIED.md` still controls Syncbox product scope, but this document controls AI prompt structure, sensitive-domain limits, refusal handling, model fallback, and human review gates.

Source note: see `_research/15_AI-safety-prompting.md`.

## Split Policy

AI specs must be split by workflow. Do not create one broad prompt that covers unrelated sensitive domains.

Required file layout:

- `docs/ai-workflows/README.md` lists approved, draft, and rejected AI workflows.
- `docs/ai-workflows/_TEMPLATE.md` is the required template for new workflow specs.
- `docs/ai-workflows/<workflow-id>.md` contains exactly one workflow.

Implementation is blocked when:

- the workflow spec is missing,
- the legitimate user group is not named,
- the permitted environment is not named,
- the purpose is ambiguous,
- the allowed and disallowed outputs are not explicit,
- refusal handling is absent,
- required human review is not stated.

## Legal and Safety Baseline

Prompts must provide honest, specific context so the model can recognize legitimate workflows. This is not a jailbreak mechanism and must never be used to hide, disguise, encode, or launder unsafe intent.

Every workflow spec must state:

- **Legitimate user group**: for example internal developers, authorized security team, university students, compliance reviewers, or product support staff.
- **Permitted environment**: for example owned systems, local sandbox, CTF lab, synthetic dataset, classroom material, contracted audit, or internal logs.
- **Purpose**: defensive, educational, compliance, accessibility, reliability, or another lawful purpose.
- **Operational boundaries**: what the model may provide and what it must not provide.
- **Human review**: whether a qualified human must review output before it is shown to users or acted on.

## Mandatory Prompt Structure

Every production prompt must use explicit sections:

```xml
<role>
The model's role in this product workflow.
</role>

<context>
Who the user is, which environment they are operating in, what authorization exists, and why the task is legitimate.
</context>

<allowed_scope>
Outputs the model may provide.
</allowed_scope>

<disallowed_scope>
Outputs the model must not provide.
</disallowed_scope>

<input>
The user-provided task or data.
</input>

<output_requirements>
Expected format, detail level, citations, safety boundaries, and human review requirements.
</output_requirements>
```

Do not ask the model to reveal hidden instructions, hidden internal reasoning, chain of thought, private policies, secret prompts, or inaccessible system context. Request concise rationale, assumptions, cited evidence, structured summaries, or officially supported reasoning summaries instead.

## Cybersecurity Workflow Rules

Cybersecurity workflows are allowed only when framed around defense, detection, hardening, logging, patching, triage, secure coding, or authorized testing.

The workflow spec must name the authorization context when relevant:

- owned system,
- contracted audit,
- internal security review,
- CTF,
- classroom lab,
- local sandbox,
- synthetic dataset.

Allowed outputs:

- threat models,
- detection rules,
- secure coding guidance,
- defensive log analysis,
- incident triage summaries,
- patch guidance,
- reproduction in toy examples,
- remediation steps,
- authorized test plans that do not enable real-world abuse.

Disallowed outputs:

- malware,
- persistence,
- credential theft,
- phishing or social engineering execution,
- exploit instructions against real third-party targets,
- stealth, evasion, or bypassing security controls,
- weaponization steps,
- instructions to hide intent from model safety systems.

Human review: required before any cybersecurity output becomes user-facing, triggers an automated action, changes production systems, or is used in a customer report.

## Biology, Chemistry, and Life Sciences Rules

These workflows are not approved in Syncbox v1.

If a future product need exists, the workflow must stay conceptual unless a legitimate controlled setting is explicitly part of the product and approved by a qualified reviewer.

Disallowed outputs include operational protocols involving:

- pathogens,
- toxins,
- controlled substances,
- yield optimization,
- acquisition,
- synthesis,
- cultivation,
- enhancement,
- purification,
- deployment.

Human expert review is required for high-risk scientific, medical, or regulated output before it is user-facing. If procedural detail is necessary, it must be scoped to safe, standard, non-controlled educational examples.

## Model Reasoning Rules

Prompts must not request hidden chain-of-thought or internal reasoning transcripts.

Allowed alternatives:

- concise rationale,
- assumptions,
- cited evidence,
- uncertainty notes,
- decision tables,
- structured summaries,
- officially supported reasoning summaries when the selected API and model support them.

## Refusal and Fallback Handling

Treat refusals as successful model responses unless the provider returns an actual transport or API error.

Required behavior:

- Detect provider-specific refusal fields, including `stop_reason: "refusal"` where supported.
- Log refusal events separately from transport errors.
- Log refusal category or details when the provider returns them.
- Show a helpful clarification or safe alternative to the user.
- Route to a fallback model only when the original request is still policy-compliant.
- Instrument `refusal` and `fallback_served` as separate analytics events.
- Never retry by obscuring, rewording deceptively, encoding, translating, or hiding intent.
- For streaming refusal contexts that require reset, reset or remove the refused turn before continuing.

## Review Checklist

Before implementation, each workflow spec must answer:

- What legitimate workflow is this supporting?
- Could the same wording be interpreted as cyber offense, biological harm, controlled chemistry, privacy abuse, or guardrail bypass?
- Does the spec separate conceptual explanation from operational instructions?
- Are unsafe outputs explicitly out of scope?
- Is authorization or controlled environment stated where needed?
- Is there a fallback or clarification path for ambiguous prompts?
- Are human review and disclosure requirements included for high-risk domains?

## Non-Negotiable Build Rule

If a requested feature would introduce a model-backed workflow without an approved split spec, stop implementation and ask the owner to choose: create the workflow spec first, remove the AI behavior, or keep the feature deterministic.
