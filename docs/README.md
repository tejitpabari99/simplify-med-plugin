# Docs index

- **[overview.md](overview.md)** — what simplify-med is, who it's for, how to install and run it, what a report contains, and what the prompt-only `simplify` workflow does and does not guarantee.
- **[architecture.md](architecture.md)** — a deep dive: the READ → WRITE → VERIFY → OUTPUT flow, where verification runs (sub-agent or second pass), the verify rules that replaced the former scripts, the final JSON schema, the package contents, testing, and known gaps.
- **[openai-plugin.md](openai-plugin.md)** — the defining plugin and skill authoring rules for this repository, including when scripts are justified for future skills, the prompt-only decision for `simplify`, and the checklist for adding future skills.
- **[openai.md](openai.md)** — the current directly installable, skills-only OpenAI package and its no-MCP archive boundary.
- **[agent_files/](agent_files/)** — design history: the original brainstorm and decision log, the deliberately-cut futures list, the kill-test reports, the write-then-verify pipeline design, and the move to a prompt-only `simplify`.
