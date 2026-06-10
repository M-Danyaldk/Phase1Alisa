# Assessment QA Verification Checklist

Use this after the assessment fixes are deployed to the live platform.

## Automated Local Checks

Run from the repo root:

```powershell
backend\.venv311\Scripts\python.exe -m backend.scripts.check_assessment_all
```

Run from `frontend`:

```powershell
npm run build
```

## Manual Live Checks

### Math Accuracy

- Log in as a student.
- Open Math assessment.
- Submit a correct multiplication answer using child-facing notation.
- Confirm correct answers are not marked wrong.
- Confirm `34 x 3`, `34 × 3`, and `34 * 3` are all treated as `102` in tutor checking.

Expected result:

- Correct math answers show as correct.
- Ms. Alisia does not introduce unrelated problems.

### All-Correct Tone

- Complete a 3-question assessment with all correct answers.

Expected result:

- The result says the child got all 3 correct.
- The tone is positive and confident.
- The old consolation message does not appear.

### Per-Question Results

- Complete any assessment with 3 answers.

Expected result:

- All 3 questions are visible in the result.
- Each question shows the child answer.
- Known-answer questions show correct/practice status.
- Expected answer appears where safe.
- The third question is not missing.

### Mia Pages Word Problem

- Submit this answer when the question appears:

```text
A book has 48 pages. Mia reads 8 pages each day. How many days will it take?
Answer: 6
```

Expected result:

- The answer is marked correct.
- The result acknowledges this question.

### Retake Rotation

- Complete an assessment.
- Retake the same subject/grade assessment.

Expected result:

- The next attempt does not immediately repeat the same question version.
- Results save separately for each attempt.

### Reading And Writing

- Complete Reading with vocabulary, passage, and grammar answers.
- Complete Writing with short open-ended answers.

Expected result:

- Reading known-answer items use deterministic checks.
- Writing answers that need judgment are shown as review-ready, not automatically wrong.

## Approval Rule

Milestone 2 should only be considered ready after:

- Automated checks pass.
- Live Math, Reading, and Writing checks pass.
- The client personally verifies the live platform.
