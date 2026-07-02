# <Workflow Name>

Status: Draft

Owner:

Last reviewed:

Source references:

## Workflow Summary

- Legitimate user group:
- Permitted environment:
- Lawful purpose:
- Sensitive domain classification:
- Human review required before user-facing output: Yes/No, with reason.

## Operational Boundaries

Allowed outputs:

- 

Disallowed outputs:

- 

## Prompt Contract

```xml
<role>

</role>

<context>

</context>

<allowed_scope>

</allowed_scope>

<disallowed_scope>

</disallowed_scope>

<input>

</input>

<output_requirements>

</output_requirements>
```

## Refusal and Fallback Handling

- Refusal detection:
- User-facing clarification:
- Safe alternative:
- Fallback model allowed: Yes/No, with conditions.
- Events to instrument:

## Review Checklist

- What legitimate workflow is this supporting?
- Could the same wording be interpreted as cyber offense, biological harm, controlled chemistry, privacy abuse, or guardrail bypass?
- Does the spec separate conceptual explanation from operational instructions?
- Are unsafe outputs explicitly out of scope?
- Is authorization or controlled environment stated where needed?
- Is there a fallback or clarification path for ambiguous prompts?
- Are human review and disclosure requirements included for high-risk domains?
