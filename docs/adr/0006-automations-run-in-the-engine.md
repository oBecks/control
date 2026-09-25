---
status: accepted
---

# Automations run in the Engine; the Assistant only writes them

An Automation is stored in the Registry and run by the Engine's own scheduler, whether or not Claude or any Window is open. You create one without writing code: either in the app's When → Then builder, or by describing it to the Assistant, which creates the same object through MCP tools ([ADR 0005](0005-assistant-through-a-local-mcp-server.md), amended). Plain language goes through the Claude the user already has connected. Control itself contains no language model, needs no API key, and stays fully local.

## Decisions

- **The Engine runs them, so they only run while the PC is on.** A timed Automation that was due while the PC was asleep or off is **skipped** and logged as missed, never run late by surprise. The "PC wakes" trigger covers wanting something to happen on wake. This makes the always-on box on the roadmap more valuable.
- **Web links are a narrow exception to Approved Browsers** ([ADR 0003](0003-phone-access-approved-browsers-over-lan-http.md)). An Automation can have a private URL, so phone Shortcuts and NFC tags can fire it. Each link carries its own long random secret, answers only on the LAN listener (with Phone access on), can fire only that one Automation, and can be revoked. It never reads state or controls anything else.
- **Presence comes from the network.** A Person is home while one of their marked phones is on the home Wi-Fi, which a network scan can already see. There's no phone app and no location sharing. Expect about a minute of delay, and phones that drop off Wi-Fi while asleep.
- **Notifications** are a Windows notification from the tray plus a notice in the UI. Phone push waits for HTTPS on the LAN.

## Considered options

- **Claude runs them** (scheduled tasks calling the MCP server): each run would depend on a Claude session and cost tokens, and it would fail whenever Claude isn't running.
- **A plain-language box inside the app**: needs an Anthropic API key and internet access, both firsts for Control. It can come later.
- **Catching up missed runs on wake**: a light switching on at 07:40 for a 07:00 rule is surprising, and an AC or plug catching up can be worse.
