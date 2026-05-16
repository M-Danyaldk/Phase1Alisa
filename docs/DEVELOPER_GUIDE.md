# MsAlisia Phase 1 Developer Guide

## 1. Purpose

This package provides a Phase 1 MVP scaffold for MsAlisia. It is built to show the working MVP modules and the future platform structure without overbuilding later-phase features.

## 2. Functional Phase 1 Modules

- Parent setup and onboarding
- Student profile context
- Assessment center for Math, ELA, and Writing
- Adaptive tutoring chat with Ms Alisia
- Grades 3-6 curriculum structure
- Subject-level progression
- Homework and handwriting upload workflow
- Parent reports
- Admin visibility
- Claude/Groq LLM provider router
- Basic safety and age-appropriate prompts

## 3. Coming Soon Modules

The UI includes Coming Soon cards for:

- Voice Learning
- Mobile App
- Teacher Portal
- School/LMS Integrations
- Advanced Analytics
- Full K-12 Expansion
- Advanced Handwriting AI
- Science
- Social Studies
- Test Prep

These modules are intentionally not fully functional in Phase 1.

## 4. LLM Design

The backend uses Claude as the primary LLM provider and Groq as fallback.

Routing:

1. Use Claude if `ANTHROPIC_API_KEY` is set.
2. Use Groq if Claude key is missing.
3. If Claude fails and `FALLBACK_ON_LLM_ERROR=true`, use Groq.
4. If no keys exist, use local fallback responses so development is not blocked.

The prompt layer is course-aware and includes:

- Grades 3-6 curriculum context
- Subject-specific teaching rules
- Safety behavior
- Short response requirements
- One-concept-at-a-time tutoring
- Validation question requirement

## 5. Curriculum Structure

Grades 3-6 are included for:

- Math
- English Language Arts
- Writing

Each subject can progress independently. A Grade 4 student can be Grade 5 in Math, Grade 4 in ELA, and Grade 3 in Writing.

## 6. Assessment Engine

The assessment endpoint evaluates submitted answers and returns:

- Estimated current level
- Score/readiness label
- Strengths
- Learning gaps
- Recommended progression
- Parent summary

## 7. Writing and Handwriting

Writing support includes:

- Grammar
- Sentence structure
- Organization
- Clarity
- Comprehension
- Writing composition

Handwriting support is MVP-lightweight:

- Legibility
- Spacing
- Neatness
- Letter formation
- Overall readability

Advanced handwriting AI analysis is intentionally left for a future phase.

## 8. UI Principles

The interface is built for non-technical users:

- Clear navigation
- Friendly labels
- Calm lilac/purple and gold palette
- Large cards
- Low cognitive load
- Minimal technical terms
- Premium learning platform feel, not heavy AI branding
