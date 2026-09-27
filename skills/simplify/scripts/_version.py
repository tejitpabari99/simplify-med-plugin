"""Fallback production version constants for pipeline artifacts.

Production builds keep ``PLUGIN_VERSION`` synchronized with root
``plugin.json``. Development builds stamp the selected dev version into the
packaged copy. ``runlog.plugin_version()`` reads the packaged manifest when
available and uses this constant only outside a complete plugin checkout.
"""

PLUGIN_VERSION = "0.1.5"
SCHEMA_VERSION = "3.0"
