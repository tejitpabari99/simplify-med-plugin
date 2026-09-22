# Test fixtures

Everything under `documents/` is currently **synthetic** -- fabricated for
testing, not a real patient record. Each synthetic file says so in a
comment line at its top.

When de-identified real documents become available, drop them into
`documents/` alongside the synthetic ones (owner-only step; see the design
brief's sub-projects list). Do not fabricate a document and label it as
de-identified real data, and do not remove the synthetic files -- tests
that only need a synthetic fixture should keep using one.
