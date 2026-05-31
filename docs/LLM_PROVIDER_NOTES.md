# LLM Provider Notes

## Provider Priority

The backend uses Claude first and Groq second.

```env
PRIMARY_LLM_PROVIDER=claude
FALLBACK_LLM_PROVIDER=groq
FALLBACK_ON_LLM_ERROR=true
ANTHROPIC_API_KEY=
GROQ_API_KEY=
```

## Claude / Anthropic

Claude is called through the Anthropic Messages API format.

Backend file:

```text
backend/app/services/llm/claude_provider.py
```

Required environment variables:

```env
ANTHROPIC_API_KEY=
ANTHROPIC_MODEL=claude-sonnet-4-5
ANTHROPIC_API_URL=https://api.anthropic.com/v1/messages
```

## Groq

Groq is called through its OpenAI-compatible chat completions endpoint.

Backend file:

```text
backend/app/services/llm/groq_provider.py
```

Required environment variables:

```env
GROQ_API_KEY=
GROQ_MODEL=llama-3.3-70b-versatile
GROQ_API_URL=https://api.groq.com/openai/v1/chat/completions
```

## Prompt Correctness Controls

All responses are routed through `backend/app/prompts.py`, which enforces:

- Grades 3-12 scope
- Subject-specific rules for Math, ELA, and Writing
- One-concept-at-a-time tutoring
- Short explanations
- One validation question
- Encouragement
- No answer dumping
- Age-appropriate safety behavior
- Handwriting feedback only as lightweight MVP feedback

## Assessment JSON

The assessment prompt requests JSON only. The backend also includes a parser that extracts JSON if the model returns extra text by mistake.

Expected fields:

- estimated_level
- score_label
- strengths
- learning_gaps
- recommended_progression
- parent_summary
