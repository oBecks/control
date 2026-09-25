# Tuya Link borrows Home Assistant's app identity

The Tuya Link (Smart Life QR sign-in that fetches each device's Local Key) calls Tuya's device-sharing API as **Home Assistant's registered app**: client id `HA_3y9q4ak7g4ephrvke`, schema `haauthorize`, endpoints under `/v1.0/m/life/home-assistant/`. It's the only place in Control that does this. Everything else talks to devices directly over the local network with open-source libraries and has no link to Home Assistant (see [ADR 0001](0001-standalone-engine-reusing-oss-device-libraries.md)).

We chose it because it's the only Tuya flow simple enough for "anyone can just download it": enter your User Code, scan a QR code in Smart Life, and you're done. The alternative, making each user create a Tuya IoT developer project and paste API keys, fails that bar. Tuya offers no self-serve way to register our own app for this QR flow.

## Consequences

- Fine for personal use. **It blocks a public release**: before shipping to others, Control must either register its own app with Tuya or switch the Tuya Link to the developer-account flow. The code is isolated in `src/control/engine/links/tuya_link.py`.
- Tuya can revoke or change this API at any time without notice to us. If it breaks, only the Link breaks. Devices already linked keep working, because their Local Keys are stored and control is local.
