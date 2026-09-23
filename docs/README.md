# Docs index

- **[overview.md](overview.md)** — what simplify-med is, who it's for, how to install and run it, what a report contains, and what the pipeline does and does not guarantee.
- **[architecture.md](architecture.md)** — a deep dive: the run folder, the stage graph, every deterministic check by name, the data contracts, the stage prompts, rendering, testing, and known gaps.
- **[plugins.md](plugins.md)** — for an engineer or agent adding support for another platform (ChatGPT, Gemini, Cursor, a custom harness): what is portable, what a platform wrapper must provide, and how `packaging/build.py` works today.
- **[openai.md](openai.md)** — the OpenAI package and presentation-only MCP viewer: pipeline placement, data flow, privacy/security contract, build, deploy, test, troubleshooting, prototype gates, PHI constraints, and the owner action checklist.
- **[agent_files/](agent_files/)** — design history: the original brainstorm and decision log, the deliberately-cut futures list, and the two kill-test reports that drove the fixes since v0.1.0.
