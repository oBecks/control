---
status: accepted
---

# Phone access: Approved Browsers over plain HTTP on the LAN

Phones reach Control by opening the Engine's address on the home Wi-Fi (e.g. `http://192.168.1.20:8321`). The Engine serves the built web UI itself, so there is one process and one port. The phone is only a Client: it needs the Engine's machine to be on. Today that machine is the user's PC. Phone access is **off until the user turns it on** there. Until then the Engine only listens on `127.0.0.1`. Once on, the Engine's own machine stays trusted, and every other browser must be an **Approved Browser** before it can see or control anything. Everything the Engine controls is physical (the AC, the plug that cuts power), so "anyone on the Wi-Fi" is not good enough: guests, a compromised smart device, or a neighbour who knows the Wi-Fi password would all qualify.

## How a browser gets approved

1. An unknown browser opens Control and gets only a waiting screen with a short code (e.g. `482 913`). Nothing else in the API answers it.
2. The Control UI on the Engine's machine, or on any browser that's already approved, shows "A phone wants access, code 482 913 · Approve / Deny". The user checks the codes match and approves. The code exists so the user approves *this* phone, not another pending request.
3. The phone receives a long random token as an `HttpOnly`, `SameSite=Strict` cookie that lasts until revoked. The Engine stores only a hash, plus a name ("iPhone · Safari") and a last-seen time, so the user can revoke it from Settings.

Approval needs something already trusted, the Engine's machine or an approved phone. No passwords to invent, share or forget, which matters for a household where everyone uses it. An approved phone can approve others, so that an Engine on a machine with no screen still works. The cost is that a lost phone can let others in until it's revoked.

## Considered options

- **Trust the whole LAN**: simplest, rejected for the reasons above.
- **A PIN or password**: gets shared around, can't be revoked per phone, and adds a login screen for every family member.
- **HTTPS on the LAN**: needed for a real Android install and for a service worker (see below). On a LAN with no outside service it means a local certificate authority the user installs on every phone, which is too much setup for "anyone downloads it". Remote access (and a valid certificate that could come with it) is out of scope for now.
- **A native phone app that controls devices without the PC**: browsers can't speak the devices' protocols (raw TCP/UDP to Yeelight, Tuya, Broadlink), so working without the PC would need a native app. That app would contain a second Engine, and it would have to keep Code Sets, learned Signals, Local Keys and names in sync with the PC's. Rejected for now as a separate product.

## Consequences

- **The phone only works while the Engine's machine is on.** When that matters, the path is moving the Engine to an always-on box (a Raspberry Pi, a NAS, a spare laptop). No Engine-specific code should assume it runs on the user's desktop. Anything that needs "the PC" must work through an approved browser too.
- **Plain HTTP is an accepted risk**: someone who can sniff the home Wi-Fi could copy a token. Revisit if Control ever reaches beyond the LAN, or when adding a local certificate authority for Android installs.
- **The Engine's machine is trusted by address**, so the Engine must also reject requests whose `Host` isn't the loopback or the machine's own LAN address. Otherwise any website open in that machine's browser could reach the API through DNS rebinding. For the same reason it refuses changes (POST, PUT…) whose `Origin` is another website.
- **PWA-lite only**: a web manifest, icons, full-screen display and theme colour; no service worker (it needs HTTPS, and Control is useless without the Engine anyway). iPhones get a full-screen home-screen app. Android Chrome gets a shortcut that opens in a browser tab.
- **iPhone home-screen apps keep their own cookies**, separate from Safari's. Approving in Safari doesn't carry over to the installed app, so the waiting screen tells the user to add Control to the Home Screen first and approve it from there.
- Every Client except the Engine's own machine goes through the same gate, including a future MCP server if it runs elsewhere.
