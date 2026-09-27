# OpenAI package

The repository root is a directly usable, skills-only OpenAI plugin. It supports independent production and development builds and has no MCP connection.

## Runtime Contents

```text
simplify-med/
  plugin.json
  .codex-plugin/
    plugin.json
  skills/
    prep/                        SKILL.md, agents/, assets/, references/
    med-lit/                     SKILL.md, agents/, assets/, references/
    simplify/
      SKILL.md
      agents/openai.yaml
      assets/icon-large.png
      assets/icon-small.svg
      stages/write.md
      stages/verify.md
      reference/style_rules.md
      reference/abbreviations.json
      schema/plan.schema.json
```

`simplify` contains no scripts, templates, or other schemas. `schema/plan.schema.json` is read only when the user asks for structured output.

The root `plugin.json` is the portable manifest. `.codex-plugin/plugin.json` is the compatibility manifest. Both describe the same `simplify-med` plugin and expose the same skills directory.

`skills/simplify/agents/openai.yaml` contains only skill interface metadata and invocation policy. It declares no MCP dependency.

## Build

Production:

```bash
python3 build.py
```

Development:

```bash
python3 build.py --dev
```

`build-versions.json` is the repository-only source for the production and
development counters. Each successful build increments the selected patch
version before packaging it. A failed build leaves both counters unchanged.

Production builds update the source `plugin.json` and `.codex-plugin/plugin.json`,
then package:

```text
dist/simplify-med-<version>-openai.zip
```

Development builds leave those production source files unchanged. Inside the
archive, both manifests use the `simplify-med-dev` name and the incremented dev
version:

```text
dist/simplify-med-dev-<version>-openai.zip
```

The builder no longer stamps a pipeline version into the skill; the manifests
are the only versioned files.

The builder intentionally uses an allowlist rather than copying the repository and subtracting exclusions. Only the two manifests and `skills/` enter the archive; `build-versions.json` does not.

## No-MCP Boundary

The current plugin:

- contains no `mcp.json` or `.mcp.json`;
- declares no `mcpServers`, app connection, endpoint, or MCP tool dependency;
- requires no server deployment or authentication setup;
- does not invoke an MCP viewer from `SKILL.md`;
- returns the short verified Markdown report directly in the conversation, with the same content as JSON (per `schema/plan.schema.json`) available on request.

The existing `mcp/openai/` directory is parked repository source for potential future work. It still reads an older plan shape and has not been updated to the prompt-only `simplify` workflow (read, write, verify, output) or its final schema. `build.py` cannot package it because the builder only includes explicitly allowlisted plugin paths.

## Install and Test

Install or import the generated ZIP through the supported OpenAI plugin interface. Start a new session after installation so the bundled skill is discovered.

Validate before distribution:

```bash
python3 -m unittest discover -s tests -v
```

Also run the OpenAI plugin and skill validators when they are available in the
development environment.

Run a build only when intentionally advancing the selected version.

Inspect the archive when the package boundary changes:

```bash
unzip -l dist/simplify-med-<version>-openai.zip
unzip -l dist/simplify-med-dev-<version>-openai.zip
```

## Publication Gaps

Before public marketplace submission, the publisher still needs real privacy-policy and terms-of-service URLs. Do not add invented or placeholder legal URLs.
