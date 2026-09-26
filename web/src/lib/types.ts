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
