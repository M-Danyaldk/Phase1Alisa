# Live QA Assessment and Tutor Report - 2026-06-10

## Scope

Live production QA was run against the student classroom on June 10, 2026.

The pass covered:

- Student classroom login
- Backend-rotated Math assessment questions
- Deterministic assessment answer validation
- Per-question result display
- All-correct score-based child feedback
- Retake question rotation
- Tutor direct answer validation for `34 × 3 = 102`

## Live Assessment Verification

Test assessment shown live:

- `What is 4 x 4.5?` Answer submitted: `18`
- `What is 1/3 + 1/6?` Answer submitted: `1/2`
- `A box is 6 units long, 7 units wide, and 8 units tall. What is its volume?` Answer submitted: `336`

Observed result:

- Badge: `All Correct`
- Title: `Excellent work`
- Score: `3/3 correct`
- All three questions appeared in the `Question results` section.
- Each item showed the student answer, expected answer, and a correct status.

## Retake Rotation Verification

After the assessment was submitted, a fresh assessment load showed a different Math question set:

- `What is 10 x 2.2?`
- `What is 2/6 + 3/6?`
- `A box is 7 units long, 3 units wide, and 5 units tall. What is its volume?`

This confirms the live system is now saving assessment tracking fields and selecting a different version for retakes.

## Tutor Verification

Live tutor prompt:

`The problem is 34 × 3. My answer is 102. Is that correct?`

Observed tutor response:

`Yes, that's correct.`

`34 × 3 = 102.`

`Nice work. Want to try one more? What is 45 × 4?`

This confirms the direct tutor answer-check path now handles the reported `34 × 3 = 102` case without wrong-answer language.

## Automated Verification

Local automated QA also passed:

- Assessment bank: 240 versions, 720 questions
- Grades covered: 3, 4, 5, 6
- Subjects covered: Math, Reading, Writing
- First 20 attempts per grade/subject cover all versions without immediate repeats
- Deterministic math validation covers multiplication symbols, division, negative numbers, fractions, and number words
- The reported Mia pages problem accepts `6`, `6 days`, `six`, and `six days`
- Per-question result persistence checks passed
- Score-based feedback checks passed
- Direct tutor answer checks now cover `my answer is ...` math messages

Commands run:

```bash
backend\.venv311\Scripts\python.exe -m backend.scripts.check_assessment_all
npm run build
```

## Evidence

Screenshot evidence is stored in:

`docs/qa-evidence/live-assessment-tutor-clean-2026-06-10T18-06-14-738Z/`

Client-facing PDF evidence:

`docs/qa-evidence/live-assessment-tutor-clean-2026-06-10T18-06-14-738Z/LIVE_QA_EVIDENCE_2026-06-10.pdf`
