# MsAlisia Phase 1 Backend

Python FastAPI backend for the MsAlisia Phase 1 MVP scaffold.

## Purpose

This backend supports:

- Claude-first LLM routing
- Groq fallback when Claude API key is missing or fails
- Grades 3-6 Math, ELA, and Writing tutoring prompts
- Assessment evaluation for Math, ELA, and Writing
- Adaptive progression by subject
- Lightweight homework/handwriting feedback
- SQLite local prototype persistence
- Admin overview endpoints

## Quick Start

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

Open the API docs:

```text
http://localhost:8000/docs
```

## LLM Environment

The backend is designed to use Claude first and Groq second.

```env
PRIMARY_LLM_PROVIDER=claude
FALLBACK_LLM_PROVIDER=groq
ANTHROPIC_API_KEY=
GROQ_API_KEY=
FALLBACK_ON_LLM_ERROR=true
```

Routing behavior:

1. If `ANTHROPIC_API_KEY` exists, Claude is used first.
2. If the Claude key is missing, Groq is used.
3. If Claude errors and `FALLBACK_ON_LLM_ERROR=true`, Groq is used.
4. If no model keys are available, local fallback messages keep the demo running.

## Key Files

| File | Purpose |
|---|---|
| `app/main.py` | FastAPI app and API routes |
| `app/config.py` | Environment settings |
| `app/models.py` | Pydantic request/response models |
| `app/curriculum.py` | Grades 3-6 subject scope |
| `app/prompts.py` | Ms Alisia tutoring, assessment, and safety prompts |
| `app/services/llm/router.py` | Claude-first / Groq-fallback routing logic |
| `app/services/llm/claude_provider.py` | Anthropic Messages API client |
| `app/services/llm/groq_provider.py` | Groq OpenAI-compatible chat client |
| `app/services/assessment_service.py` | Assessment evaluation and JSON parsing |
| `app/database.py` | SQLite schema and helpers |

## Production Notes

For production, replace local SQLite with PostgreSQL and add:

- Real authentication
- Per-user authorization
- API rate limiting
- Structured logging
- Background jobs
- Proper file upload storage
- Stripe integration
- Deployment secrets management
