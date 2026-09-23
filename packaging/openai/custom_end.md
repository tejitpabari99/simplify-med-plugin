# OpenAI result presentation

These instructions apply only after Stage 5 has completed successfully. They change
how the existing outputs are presented; they do not change or rerun the medical
pipeline.

1. Give a concise native ChatGPT summary of the completed report, including the most
   important next actions, medication changes or questions, tests, appointments,
   follow-up timing, and important uncertainty that is explicitly present in the
   report. Do not infer a source-document type or date. State that this is a reading
   aid based on the supplied documents, not a new diagnosis or treatment instruction.
2. Attach or link these three completed outputs: `<run>/06_plan.final.json`,
   `<run>/report.md`, and `<run>/report.html`.
3. Immediately call `render_simplify_med_report` once with
   `<run>/06_plan.final.json` as the `report` file parameter. Do not ask the user to
   select or upload it again.
4. Never pass an uploaded source document, `00_input`, source units, a fact ledger,
   review or coverage files, additions, flags, `run.json`, or an audit report to that
   tool. Never put report JSON in ordinary tool arguments, `structuredContent`,
   `content`, or `_meta`; use the declared OpenAI file parameter only.
5. If the viewer tool or a required host capability is unavailable, keep the native
   summary and the JSON, Markdown, and self-contained HTML downloads as the complete
   fallback. Do not introduce a second file picker.
