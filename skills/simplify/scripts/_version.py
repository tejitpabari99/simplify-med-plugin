"""Fallback version constants.

These mirror plugin.meta.json's "version" and "schema_version" fields.
runlog.plugin_version() prefers reading plugin.meta.json directly (so a dev
checkout always reflects the source of truth), and falls back to
PLUGIN_VERSION here only when plugin.meta.json cannot be found on disk -- for
example when the skill has been packaged for claude.ai, where plugin.meta.json
is intentionally excluded from the archive (see packaging/claude-ai.ignore).

NOTE: packaging/build.py asserts that PLUGIN_VERSION here matches the
"version" field in plugin.meta.json before building any package, so these
two values must be kept in sync by hand until that is automated.
"""

PLUGIN_VERSION = "0.1.0"
SCHEMA_VERSION = "1.0"
