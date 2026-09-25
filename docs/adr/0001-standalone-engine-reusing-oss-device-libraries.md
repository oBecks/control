# Standalone Engine reusing open-source device libraries, not Home Assistant

Control ships as its own Engine instead of being a front end for Home Assistant. Protocol support comes from the same open-source Python libraries Home Assistant integrations use (e.g. `python-yeelight`, `broadlink`, `tinytuya`), so the Engine is written in Python.

Home Assistant would give us ~3,000 integrations for free, but installing it breaks the core promise: anyone downloads one app, scans, and controls. Writing every protocol from scratch would take years. Reusing the libraries keeps the single-download experience and still reuses most of the protocol work.

## Consequences

- The Engine is Python. Clients (desktop window, web UI, MCP server) talk to it over a local API and contain no device logic.
- Each supported brand is an adapter around one library. Brand coverage grows one adapter at a time, not all at once.
- One exception: the Tuya Link signs in as Home Assistant's registered app. See [ADR 0002](0002-tuya-link-borrows-home-assistant-identity.md).
