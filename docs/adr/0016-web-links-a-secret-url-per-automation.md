---
status: accepted
---

# Web links: a secret URL per Automation

Roadmap step 5, phase 2: start an Automation from something that isn't Control's own UI: a phone bookmark, an NFC tag, an iOS Shortcut, a script on another machine.

## Decisions

- **A Trigger kind, `web`, with a secret `token`** the Engine makes (32 random bytes, URL-safe) when the Automation is saved. At most one per Automation. The link is `<the Engine's address>/api/hooks/<token>`: the phone address from Settings → Phone access when it's on, else the PC's own. It is shown, with Copy and "Make a new link", on the Automation's page once saved. An edit that sends the Trigger back keeps the secret whatever it sends; only "Make a new link" changes it, and the old link stops working.
- **GET or POST.** GET makes it a plain bookmark, NFC tag or Shortcut "open URL"; POST is for scripts. A browser (`Accept: text/html`) gets a small "Started …" page, anything else JSON. Link prefetchers may open a GET link, which is why the secret is the only thing that starts it and why a Run restarts rather than piles up.
- **Anyone on the home network with the secret**, no Approved Browser needed: `access.py` lets `/api/hooks/` through the gate (nothing else). It still needs phone access turned on, since that is what opens the Engine to the network at all, so a link never reaches beyond the private addresses ADR 0003 listens on. From the PC itself it always works.
- **It is a Trigger like the others:** the Only if applies, the Run's cause is "The web link is opened". A switched-off Automation answers 409 ("switched off"). Run by hand and the Run button still skip Conditions.
- **Wrong links are held off.** A client address that opens 20 wrong links in a minute gets 429 for the rest of the minute, even for a right one. With a 256-bit secret guessing is hopeless anyway; this only keeps a scan from filling the log.
- **The secret is kept out of the Assistant.** Its tools show the Trigger as "the web link is opened" and never the link; the user copies it from the app. Same for the Runs: none logs the secret.
- **Plain HTTP on the LAN, as ADR 0003 accepts:** someone sniffing the Wi-Fi could copy a link. "Make a new link" is the remedy. HTTPS on the LAN (roadmap step 10) would close it.

## Considered options

- **Approved Browsers only:** reuses phone approval, but a Shortcut, NFC tag or another device has no browser cookie.
- **POST only:** safer against prefetchers, but can't be a bookmark or NFC tag, the main use.
- **A link per Automation set by the user** (a readable name): easy to guess, so it would need a second secret anyway.
- **Links skipping the Only if:** would make the Trigger differ from every other; "run it whatever" is what the Run button is for.
- **Outside the home** (a relay or tunnel): out of scope; it would put the key on a service on the internet.
