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

/** What a Hotkey does (see engine/hotkeys.py). */
export type HotkeyAction =
	| { do: 'toggle' }
	| { do: 'set'; state: StateChange }
	| { do: 'step'; field: 'brightness' | 'target_temp'; by: number }
	| { do: 'press'; button: string }
	| { do: 'open_app'; app: string };

/** Keys on the PC running Control that do one thing to one Device or Group (ADR 0007). */
export interface Hotkey {
	uid: string;
	/** e.g. "Ctrl+Alt+L", "F13", "Volume Up" */
	keys: string;
	/** A Device's or Group's uid. */
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
