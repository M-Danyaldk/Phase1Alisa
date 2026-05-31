# MsAlisia Phase 1 MVP Package

This package contains the frontend, backend, and documentation for a Phase 1 MVP scaffold.

## Current Phase 1 Scope

The Phase 1 MVP is designed around:

- Grades 3-12 curriculum support
- Adaptive progression by subject
- Math, ELA, and Writing assessment engine
- Writing composition support
- Lightweight handwriting/penmanship feedback through upload workflow
- Parent/student experience
- Admin visibility
- Claude primary LLM and Groq fallback
- Future platform modules visible as Coming Soon

## Stack

- Frontend: React + TypeScript + Vite
- Backend: Python + FastAPI
- LLM: Claude first, Groq fallback
- Prototype storage: SQLite
- Styling: custom CSS with lilac/purple + gold direction
- Deployment-ready: Dockerfiles and docker-compose

## Run Locally

1. Start backend:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

2. Start frontend:

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

3. Open:

```text
http://localhost:5173
```

## Docker Compose

```bash
docker compose up --build
```

Frontend: `http://localhost:5173`  
Backend: `http://localhost:8000`

## Important

Do not commit real API keys. Put keys in `.env` only.

Before launch, confirm Supabase automatic backups are enabled in the Supabase dashboard. This cannot be verified or enabled from application code.
