---
status: accepted
---

# Presence from phones on the home network

[ADR 0006](0006-automations-run-in-the-engine.md) said a Person is home while one of their phones is on the home Wi-Fi, "which a network scan can already see". It can't: a phone that's asleep stops answering, drops out of the PC's neighbour (ARP) table, and no Scan looks for phones anyway. Tried on 2026-09-28: a UDP packet to port 5353 on every address brought back six devices the table lacked, among them one with a private MAC (a phone). So presence needs its own small check, and it has to be light on the PC (roadmap step 8).

## Decisions

- **A phone is known by its MAC.** Phones use a private MAC per network, stable unless the user sets it to "Rotating" (iOS) or "non-persistent" (Android), so the Wi-Fi address identifies the phone even when its IP changes. The IP is only where to look first.
- **Seen means it answered just now.** Control nudges the phone's last IP with a UDP packet to port 5353 (mDNS, which a sleeping iPhone wakes for), which makes Windows ask for its MAC, then reads Windows' neighbour table and counts only an entry that is *Reachable* for that MAC. `arp -a` also lists *Stale* entries for phones that left minutes ago, so its list alone isn't enough.
- **Checked every 30 seconds, and only while some phone is marked.** Each check nudges the marked phones' last IPs (a few packets, one table read: about 2 ms of CPU). With no phones marked, nothing runs.
- **The whole subnet is swept only when a phone may have moved** (about 30 ms of CPU and 253 ARP requests on the network): when Control starts, when this PC's address changes, and when the network comes back (a router restarting after a power cut may hand out new addresses); and for a phone missing 5 minutes, then every 30 minutes while it stays missing, so the network stays quiet while someone is away all day. Routers mostly give a phone its old address back, so arriving still shows within a minute.
- **Away after 10 minutes unseen, counted in time the PC is awake.** Sleeping phones and short Wi-Fi drops don't make anyone "leave"; arriving shows within about a minute. A PC waking from sleep doesn't count its sleep as everyone being away.
- **Can't see is not away.** When this PC has no address on the home network, or nothing answers at all (not even the router), nobody counts as home or away: everyone becomes unknown, which fires nothing, until Control sees again. A power cut that takes the router down doesn't make everyone leave, and its end doesn't make everyone arrive; arrivals and departures during it are lost.
- **Only changes count** (as with listening, ADR 0011). Until a Person's phone is seen, or 10 minutes pass without it, their presence is unknown; leaving unknown fires nothing, so starting Control never says everyone arrived.
- **Marking a phone, two ways:** from the phone itself ("This is my phone", from an Approved Browser: Control looks up the MAC of the address the request came from), or on the PC from the phones seen on the network (a sweep; private MACs first, Devices Control already knows left out), for people who never open Control.
- **Automations:** Triggers "a Person arrives / leaves" and "the first person arrives / the last person leaves"; Conditions "a Person is home / away" and "someone / nobody is home". A Person whose presence is unknown makes a Condition unmet ("couldn't tell"). Nothing an Automation does changes presence, so these need no loop guard.
- **Nothing leaves the house.** No phone app, no location sharing, no cloud: only packets on the home network.

## Considered options

- **Ping (ICMP)**: sleeping iPhones ignore it, and Windows Firewall on some phones' hotspots blocks it.
- **Read `arp -a` after a Scan**: Scans are rare, and stale entries would keep a phone "home" for minutes after it left.
- **Ask the router** (its DHCP or client list): the most accurate, but every router is different and needs its admin password.
- **Approved Browsers as presence** (the phone opened Control recently): only while Control is open on the phone, so nobody would ever "arrive".
- **A phone app or geofencing**: accurate and early, but it's an app to build per platform, needs location permission, and presence would leave the home network.
- **A shorter away delay** (5 minutes): quicker "leaves", but more false leave and arrive pairs at night while phones sleep.
