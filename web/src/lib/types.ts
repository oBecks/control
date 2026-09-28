// Mirrors the Engine API (src/control/api/app.py).
import type { RGB } from './color';

export type Control = 'light' | 'plug' | 'climate' | 'remote' | 'streamer';

/** A Group's control surface: a light's or an AC's when every member is one, otherwise on/off. */
export type GroupControl = 'light' | 'climate' | 'power';

export interface LightFeatures {
	color: boolean;
	color_temp: boolean;
	min_kelvin: number;
	max_kelvin: number;
}

export interface LightState {
	on: boolean;
	brightness: number;
	mode: 'color' | 'white';
	rgb: RGB | null;
	kelvin: number | null;
}

export interface PlugState {
	on: boolean;
}

export interface ClimateFeatures {
	modes: string[];
	fan_modes: string[];
	swing_modes: string[];
	min_temp: number;
	max_temp: number;
	step: number;
}

export interface ClimateState {
	on: boolean;
	mode: string;
	target_temp: number;
	fan: string;
	swing: string | null;
}

export interface RemoteFeatures {
	kind: 'tv' | 'fan' | 'other';
	buttons: { name: string; label: string }[];
	/** Separate On/Off Signals: on/off is an Assumed State. Otherwise Power is a toggle. */
	discrete_power: boolean;
	can_power: boolean;
}

export interface RemoteState {
	/** null with a Power Toggle: the app never claims whether it's on. */
	on: boolean | null;
}

/** A Streamer App Shortcut: a button that opens one app. `app`: its package (names the open app);
 * `link`: what opens it, when known (some devices only open apps by link). */
export interface AppShortcut {
	name: string;
	app: string;
	link?: string;
}

/** An app Control knows, as a Streamer's setup offers it. `default`: ticked at setup. */
export interface CatalogueApp extends AppShortcut {
	default: boolean;
}

export interface StreamerFeatures {
	buttons: { name: string; label: string }[];
	apps: AppShortcut[];
	/** A TV running Android TV itself, not a box plugged into one. */
	is_tv: boolean;
	/** The Link's optional second step: Control may open any app and see what's installed (ADR 0008). */
	adb: boolean;
}

/** A Streamer's real state, as the device reports it. */
export interface StreamerState {
	on: boolean;
	/** The open app's package, and what to call it. */
	app: string | null;
	app_name: string | null;
	volume: number | null;
	volume_max: number | null;
	muted: boolean | null;
}

/** Partial desired state sent to POST /api/devices/{uid}/state */
export interface StateChange {
	on?: boolean;
	brightness?: number;
	rgb?: RGB;
	kelvin?: number;
	mode?: string;
	target_temp?: number;
	fan?: string;
	swing?: string;
	press?: string;
	/** Streamers: an app's package name or link. */
	open_app?: string;
}

/** How one Device or Group should be in a Scene: only what the user chose (engine/scenes.py).
 * Setting anything but `on` also turns it on; `on: false` comes alone. `app`: a Streamer's, by package. */
export interface SceneState {
	on?: boolean;
	brightness?: number;
	rgb?: RGB;
	kelvin?: number;
	mode?: string;
	target_temp?: number;
	fan?: string;
	swing?: string;
	app?: string;
}

export interface ScenePart {
	/** A Device's or Group's uid. */
	target: string;
	state: SceneState;
}

/** A named end state for several Devices, set in one tap (ADR 0013). */
export interface Scene {
	uid: string;
	name: string;
	icon: string;
	/** `label`: the state in words, e.g. "On · 20% · 2700 K". */
	parts: (ScenePart & { target_name: string; label: string })[];
	/** Why it needs looking at, e.g. nothing is left in it. */
	attention: string | null;
	made_by: 'user' | 'assistant';
}

/** What a Hotkey does (see engine/hotkeys.py). */
export type HotkeyAction =
	| { do: 'toggle' }
	| { do: 'set'; state: StateChange }
	| { do: 'step'; field: 'brightness' | 'target_temp'; by: number }
	| { do: 'press'; button: string }
	| { do: 'open_app'; app: string }
	/** An Automation's Run, skipping its Only if (ADR 0012). */
	| { do: 'run' }
	/** A Scene, every part at once (ADR 0013). */
	| { do: 'set_scene' };

/** Keys on the PC running Control that do one thing to one Device or Group (ADR 0007). */
export interface Hotkey {
	uid: string;
	/** e.g. "Ctrl+Alt+L", "F13", "Volume Up" */
	keys: string;
	/** A Device's, Group's, Automation's or Scene's uid. */
	target: string;
	target_name: string;
	action: HotkeyAction;
	/** e.g. "Toggle", "Brightness up 10%" */
	action_label: string;
	/** Holding the keys repeats it. */
	repeats: boolean;
	made_by: 'user' | 'assistant';
	/** taken: another app has the keys. off: the Desktop App isn't running, so no Hotkey works. */
	status: 'active' | 'taken' | 'pending' | 'off';
}

/** Whether keys can be a Hotkey. */
export interface KeysCheck {
	/** The keys as Control writes them, e.g. "Ctrl+Alt+L". */
	keys: string;
	/** Why they can't. */
	problem: string | null;
	/** What they'd take from other apps. */
	warning: string | null;
}

/** A key to pick when the Window can't see it pressed. */
export interface PickableKey {
	code: string;
	label: string;
	group: 'spare' | 'media' | 'function' | 'letters' | 'numpad' | 'other';
	/** Types text, so it needs Ctrl, Alt or Win. */
	types: boolean;
}

/** A Big Control's kind: a light's brightness bar or colour wheel, or an AC's temperature, mode and power. */
export type BigControl = 'brightness' | 'colour' | 'climate';

/** A Dashboard item before it has a cell (ADR 0010): w is its width in columns, h its height in rows. */
export type NewDashboardItem =
	| { id: string; kind: 'tile'; w: number; h: number; target: string }
	| { id: string; kind: 'big_control'; w: number; h: number; target: string; control: BigControl }
	/** A Remote Pad: the Device's buttons laid out like its remote. */
	| { id: string; kind: 'pad'; w: number; h: number; target: string }
	/** A Single Button: presses one remote button, or opens one Streamer app (by package). */
	| { id: string; kind: 'button'; w: number; h: number; target: string; button?: string; app?: string }
	| { id: string; kind: 'clock'; w: number; h: number }
	/** Who's home: each Person, home or away (ADR 0014). */
	| { id: string; kind: 'people'; w: number; h: number }
	/** A Run Button: starts an Automation's Run (target is its uid). */
	| { id: string; kind: 'run'; w: number; h: number; target: string }
	/** A Scene Button: sets a Scene (target is its uid), lit while it's active. */
	| { id: string; kind: 'scene'; w: number; h: number; target: string }
	| {
			id: string;
			kind: 'heading';
			w: number;
			h: number;
			text: string;
			align: 'start' | 'center' | 'end';
			text_size: 's' | 'm' | 'l' | 'xl';
			bold: boolean;
	  };

/** One item on a Dashboard, at its cell: x is its column, y its row (a row is half a Tile tall), from 0. */
export type DashboardItem = NewDashboardItem & { x: number; y: number };

export type DashboardItemKind = DashboardItem['kind'];

/** A named screen the user arranges by hand. */
export interface Dashboard {
	uid: string;
	name: string;
	/** The grid's width: 4 for a phone, 6 for a tablet, 8 for a desktop. */
	columns: 4 | 6 | 8;
	items: DashboardItem[];
}

// --- Automations (ADR 0006, 0012; engine/automations.py) ---------------------------

/** Weekday numbers, Monday 0 to Sunday 6. */
export type Weekday = 0 | 1 | 2 | 3 | 4 | 5 | 6;

/** The "When" of an Automation: any one starts a Run. Times are "HH:MM", the PC's local time. */
export type Trigger =
	| { type: 'time'; at: string; days: Weekday[] }
	/** offset: minutes before (negative) or after. */
	| { type: 'sun'; event: 'sunrise' | 'sunset'; offset: number; days: Weekday[] }
	/** A Device or Group turns on or off (a Group: its first member on, its last off), and stays so for
	 * `minutes` first (0: at once). The Engine listens to the Devices these name (ADR 0011). */
	| { type: 'state'; target: string; on: boolean; minutes: number }
	/** Opens the app, and keeps it open for `minutes` first (0: at once). */
	| { type: 'app'; target: string; app: string; minutes: number }
	/** Goes Offline (a minute without an answer), or (false) comes back online. */
	| { type: 'offline'; target: string; offline: boolean }
	/** A Scene is set, by anyone (ADR 0013). */
	| { type: 'scene'; target: string }
	/** A Person arrives home, or (false) leaves (ADR 0014). */
	| { type: 'person'; target: string; home: boolean }
	/** The first person arrives home, or (false) the last one leaves. */
	| { type: 'home'; occupied: boolean };

/** The "Only if": checked once when a Trigger fires. */
export type Condition =
	| { type: 'state'; target: string; on: boolean }
	| { type: 'app'; target: string; app: string }
	/** May cross midnight. */
	| { type: 'time'; after: string; before: string }
	| { type: 'days'; days: Weekday[] }
	| { type: 'sun'; is: 'dark' | 'light' }
	/** A Scene is active (false: isn't). */
	| { type: 'scene'; target: string; active: boolean }
	/** A Person is home, or (false) away. */
	| { type: 'person'; target: string; home: boolean }
	/** Someone is home, or (false) nobody is. */
	| { type: 'home'; occupied: boolean };

/** The "Then", in order: a Hotkey's action on a Device or Group, running another Automation
 * (skipping its Only if, without waiting for it), a wait, or a notification. */
export type AutomationAction =
	(HotkeyAction & { target: string }) | { do: 'wait'; seconds: number } | { do: 'notify'; text: string };

/** A part as the Engine sends it back: with its plain-language label. */
export type Labelled<T> = T & { label: string };

export type RunOutcome = 'running' | 'succeeded' | 'partly_failed' | 'skipped' | 'missed' | 'interrupted' | 'restarted';

/** One time an Automation went. */
export interface Run {
	id: number;
	/** e.g. "At 07:00, every day" or "Run by hand". */
	cause: string;
	/** Seconds since 1970. */
	started: number;
	ended: number | null;
	outcome: RunOutcome;
	steps: { label: string; result: 'done' | 'failed' | 'not_run'; detail?: string; wait?: boolean }[];
	/** e.g. which Condition wasn't met. */
	note: string;
}

export interface Automation {
	uid: string;
	name: string;
	enabled: boolean;
	/** The Conditions: all must hold, or any one. */
	match: 'all' | 'any';
	triggers: Labelled<Trigger>[];
	conditions: Labelled<Condition>[];
	actions: Labelled<AutomationAction>[];
	/** The whole Automation in plain language. */
	summary: string;
	/** Why it switched itself off, e.g. a Device it used was forgotten. */
	attention: string | null;
	made_by: 'user' | 'assistant';
	running: boolean;
	last_run: Run | null;
	/** When a Trigger fires next (seconds since 1970), if it's on and has one. */
	next_run: number | null;
}

/** The home's location, for sunrise and sunset, with today's times ("HH:MM"). */
export interface HomeLocation {
	name: string;
	lat: number;
	lon: number;
	sunrise: string | null;
	sunset: string | null;
}

/** A notification from an Automation, also shown as a Windows notification on the PC. */
export interface Notice {
	id: number;
	time: number;
	/** The Automation's name. */
	title: string;
	text: string;
	automation: string | null;
	seen: boolean;
}

/** A phone marked as a Person's, known by its Wi-Fi (MAC) address. */
export interface Phone {
	mac: string;
	name: string;
	ip: string;
	/** A private (made-up) Wi-Fi address, as phones use. */
	private: boolean;
	/** When it last answered (seconds since 1970), since Control started. */
	seen: number | null;
	/** The phone this browser runs on. */
	current: boolean;
}

/** Someone who lives in the home (ADR 0014). */
export interface Person {
	uid: string;
	name: string;
	/** Home, away, or null while Control doesn't know yet. */
	home: boolean | null;
	phones: Phone[];
	made_by: 'user' | 'assistant';
}

/** Something answering on the home network now, to pick a phone from. */
export interface Nearby {
	ip: string;
	mac: string;
	private: boolean;
	/** What the router calls it, if it says. */
	name: string | null;
	/** The Approved Browser last seen at this address. */
	browser: string | null;
}
