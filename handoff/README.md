# Einstein Tutor Claude Handoff

This folder is the takeover pack for another coding agent.

## Read in this order

1. `HANDOFF.md`
2. `FILE_GUIDE.md`
3. `ARCHITECTURE.md`
4. `BUGS_AND_RISKS.md`
5. `NEXT_STEPS.md`

## What this folder covers

- what the app does
- how the architecture works
- where the important logic lives
- how upload, grouping, and concept-map flows work
- what is broken or fragile
- what should be fixed next

## Important code files outside this folder

Claude should inspect these code files immediately after reading the docs:

1. `/Users/madu/Desktop/Codex/main.py`
2. `/Users/madu/Desktop/Codex/app.js`
3. `/Users/madu/Desktop/Codex/index.html`
4. `/Users/madu/Desktop/Codex/schema.sql`
5. `/Users/madu/Desktop/Codex/tests/test_einstein_tutor.py`
6. `/Users/madu/Desktop/Codex/styles.css`

## Short instruction you can give Claude

"Start with `/Users/madu/Desktop/Codex/handoff/README.md`, then inspect the code files referenced there. Focus first on document identity, subject grouping, concept-map source tracking, and any fragile or unfinished logic."
