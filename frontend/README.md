# MsAlisia Phase 1 Frontend

React + TypeScript + Vite frontend for the MsAlisia Phase 1 MVP scaffold.

## Purpose

This interface is designed for non-technical parents, students, and admin users. It uses a calm lilac/purple and gold visual direction and avoids heavy "AI chatbot" branding.

## Main Screens

- Home dashboard
- Parent setup / onboarding
- Assessment center
- Student learning chat
- Homework and handwriting upload workflow
- Parent reports
- Billing and trial preview
- Admin visibility
- Future modules / Coming Soon

## Quick Start

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

Open:

```text
http://localhost:5173
```

## Environment

```env
VITE_API_BASE_URL=http://localhost:8000
```

## Key Files

| File | Purpose |
|---|---|
| `src/main.tsx` | Full MVP interface and frontend API calls |
| `src/styles.css` | UI theme, responsive layout, lilac/gold styling |
| `public/logo.jpeg` | MsAlisia logo if provided |
| `.env.example` | API base URL config |
| `Dockerfile` | Containerized frontend deployment |

## UI Strategy

Functional in Phase 1:

- Parent profile setup
- Assessments for Math, ELA, and Writing
- Ms Alisia learning chat
- Homework/handwriting feedback workflow
- Reports view
- Admin visibility screen

Shown as Coming Soon:

- Voice learning
- Mobile app
- Teacher portal
- School/LMS integrations
- Advanced analytics
- Full K-12 expansion
- Advanced handwriting AI
- Science and Social Studies
