# Test fixtures

Everything under `documents/` is synthetic: fabricated for tests, never a
real patient record. Each file declares that on its first line.

The `simplify` skill runs no code, so these documents are manual evaluation
inputs: paste one into a session (or upload it) and run `$simplify`, then
compare the report with the target format in
`docs/agent_files/claude-prompt-only-simplify-2026-09-27/PRD.md` (§4) and the
verify checklist in `skills/simplify/stages/verify.md`. No automated test reads
them.

`synthetic-er-visit.txt` resembles the previous worked example (an ER visit for
a headache with an abnormal ECG). Use it to check behavior, not to judge
writing quality against that old example.

If de-identified real documents are later approved, add them alongside the
synthetic set without relabeling fabricated content or removing these files.
