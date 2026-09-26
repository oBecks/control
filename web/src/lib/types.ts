// Mirrors the Engine API (src/control/api/app.py).
import type { RGB } from './color';

export type Control = 'light' | 'plug' | 'climate' | 'remote';

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
}
