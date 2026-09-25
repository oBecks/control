# Control

A home app that discovers smart things on the local network and lets anyone control them from one auto-organised interface, from the Desktop App's Window, a browser on the same wifi, or an AI assistant.

## Language

### Things in the home

**Device**:
Anything the user can control from the app: a light, a plug, an AC. The unit the user thinks in.
_Avoid_: Thing, gadget, entity, accessory

**Found Device**:
Something a Scan saw on the network, before it's usable. It may be controllable now, need a Link, or be unsupported.
_Avoid_: Discovered device, scan result

**Hub**:
A device whose job is to control other devices for the user. It never appears on Home. There are two kinds: Transmitters and Bridges.

**Transmitter**:
A Hub that controls dumb appliances by replaying remote Signals (IR/RF), e.g. a Broadlink. It can't know what's in front of it, so the app asks the user what it controls and turns each answer into a Remote Device.
_Avoid_: Blaster

**Bridge**:
A Hub that reports its own devices (e.g. a Philips Hue bridge), so nothing needs to be asked. Not supported yet.

**Remote Device**:
A Device with no network connection of its own (a TV, an AC, a fan), controlled by sending Signals through a Transmitter. Its Signals come from a Code Set in the Signal Library or are taught by Learning.
_Avoid_: Virtual device, IR device

**Signal**:
One learned or library-provided remote command (e.g. "AC 24°C cool", "TV volume up") that a Transmitter sends on behalf of a Remote Device. A TV's or fan's Signals are named after the remote's buttons.
_Avoid_: Code, IR code

**Learning**:
Teaching a Remote Device a Signal by pointing its original remote at the Transmitter and pressing the button. It's the main way to set up TVs and fans, and the fallback for ACs.
_Avoid_: Recording, capturing, training

**Power Toggle**:
A single Power Signal that switches a Remote Device on *or* off depending on its current state. A Remote Device with only a Power Toggle has no Assumed State for power: the app can send Power but never claims whether it's on.

**Assumed State**:
The state of a Remote Device as last commanded by the app. It may be wrong if someone used the physical remote, so it's always shown as assumed. Only possible when the Signals are absolute (an AC's full-state Signals, separate On and Off), never with a Power Toggle.
_Avoid_: Fake state, cached state

**Signal Library**:
A community catalogue of Signals for known appliance models. The user picks a model from it, and Signals are only learned by hand when the model isn't listed.

**Code Set**:
One appliance model's complete group of Signals in the Signal Library. A brand usually has several, and the right one is found by testing, because the model name on the AC rarely matches the library's.
_Avoid_: Device code, code file, profile

**Unsupported Device**:
A Found Device recognised as smart but of a brand or model the app can't control yet. Shown greyed out. Non-smart network hosts (phones, PCs, routers) are never shown.
_Avoid_: Unknown device

**Offline**:
A remembered Device that didn't show up in the latest Scan of its brand. It keeps its name and settings and comes back when it's seen again, even at a different IP.

**New**:
A flag on a Device the user hasn't looked at since a Scan first found it.

### Organising

**Category**:
The kind of Device (Light, Climate, Media, Plug…), detected automatically and used as the default grouping. Fans belong to Climate.
_Avoid_: Type, class

**Room**:
An optional, user-made grouping of Devices by physical location. Never auto-detected.
_Avoid_: Zone, area, space

**Group**:
A named set of Devices controlled as if it were one Device (e.g. "Living room lights"): one Tile, one set of Device Controls showing only what every member supports. Tapping it turns everything off if any member is on, otherwise everything on. Members are any Devices with power, except Remote Devices that only have a Power Toggle, since "all off" can't be guaranteed for them.
_Avoid_: Light group, zone, Room, Scene

**Scene**:
A named, one-tap set of target states across several Devices (e.g. "Movie night"). A Scene never fires by itself; an Automation can run one.
_Avoid_: Preset, routine, macro

**Automation**:
A user-made rule that the Engine runs on its own: when something happens (a time, sunrise, a Device changing state, the PC waking…), do something (control Devices or Groups, run a Scene). Runs only while the Engine is running. Made in the app or by describing it to the Assistant, never by writing code.
_Avoid_: Routine, rule, script, trigger

**Person**:
Someone who lives in the home, known to Control by the phone(s) the user marked as theirs. A Person is home while one of their phones is on the home network, which lets Automations react to someone arriving or the last person leaving. Not an account and not an Approved Browser.
_Avoid_: User, member, resident

### Screens

**Home**:
The main screen: Scenes and Groups on top, then every controllable Device as a Tile (including Devices that are also in a Group), grouped by Category (or by Room once Rooms exist). Always auto-sorted, so a new Device shows up without anyone placing it. Hubs never appear here.
_Avoid_: Main page

**Dashboard**:
A named screen the user arranges by hand, holding only the Tiles (and other items) they placed on it, e.g. "Phone remote". Each browser can pick one to open to instead of Home. A Dashboard is one layout that reflows on narrow screens, not separate phone and desktop layouts.
_Avoid_: Custom home, board, panel, page

**Tile**:
A Device's or Group's compact presence on Home or a Dashboard. Tapping it toggles on/off, and its chevron opens Device Controls. When on, it takes the Device's real colour.
_Avoid_: Card, widget, button

**Device Controls**:
The full controls for one Device (brightness, colour, AC mode and temperature…). A bottom sheet on phones, a side panel on desktop.
_Avoid_: Details page, modal, popup

**Add Devices**:
The screen for Scans and for finishing Found Devices that aren't Ready (Links, Setup, adding Remote Devices). Reached from the New banner on Home.
_Avoid_: Onboarding, setup wizard, discovery page

**Hubs & Bridges**:
The Settings list of Hubs, with their status and the Remote Devices that depend on them.

### Getting connected

**Scan**:
A pass over the local network that produces Found Devices.
_Avoid_: Discovery, search

**Link**:
The one-time step that makes a Found Device controllable when it needs more than being found, e.g. signing into a brand account to fetch its local key, or pressing a bridge button. After a Link, control stays on the local network.
_Avoid_: Pair, integrate, connect, login

**Readiness**:
How close a Found Device is to being controllable: _Ready_, _Needs Link_ (the app can finish it with the user's help), _Needs Setup_ (the user must change something in the brand's own app or on the device first, e.g. unlocking a Broadlink), or _Unsupported_.
_Avoid_: Status, state

**Local Key**:
The per-device secret some brands (e.g. Tuya) require for local control, obtained once through a Link.

### Clients

**Engine**:
The always-running core that owns every Device, its state, and all control. Everything else is a client of it.
_Avoid_: Server, backend, daemon, hub

**Client**:
Anything that talks to the Engine: the Window, the web UI in a browser, the MCP server. Clients hold no device logic.

**Assistant**:
An AI the user talks to (e.g. Claude) that reads and controls Devices through Control, by way of the MCP server. It can do what Home does, not set things up.
_Avoid_: AI agent, bot, Claude integration

**Desktop App**:
The program a user downloads and installs on their PC. It runs the Engine, shows the Window, and keeps a tray icon so the Engine stays running (and phones keep working) after the Window is closed. It starts with Windows.
_Avoid_: Launcher, tray app, desktop client

**Window**:
The Desktop App's own app window: a Client showing the same UI a browser gets. Closing it hides it; only quitting from the tray stops the Engine.
_Avoid_: Desktop window, main window

**Approved Browser**:
A browser on another device (e.g. a phone) that the user has allowed, once, from the machine running the Engine or from another Approved Browser, by matching the short code it shows. Unapproved browsers can't see or control anything. The user can revoke an Approved Browser at any time.
_Avoid_: Paired device, trusted device, logged-in user
