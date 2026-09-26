// Hotkeys in the UI: reading pressed keys, and the choices the editor offers for what a Hotkey does.
// The Engine checks everything again (engine/hotkeys.py); this only shapes the form.
import type { RGB } from '$lib/color';
import type { HotkeyAction } from '$lib/types';

const MODIFIER_CODES = new Set([
	'ControlLeft',
	'ControlRight',
	'AltLeft',
	'AltRight',
	'ShiftLeft',
	'ShiftRight',
	'MetaLeft',
	'MetaRight',
	'OSLeft',
	'OSRight'
]);

interface Pressed {
	code: string;
	ctrlKey: boolean;
	altKey: boolean;
	shiftKey: boolean;
	metaKey: boolean;
}

/** The modifiers held, in the order Control writes them. */
export function modifiersOf(e: Omit<Pressed, 'code'>): string[] {
	return [e.ctrlKey && 'Ctrl', e.altKey && 'Alt', e.shiftKey && 'Shift', e.metaKey && 'Win'].filter(
		(m): m is string => !!m
	);
}

/** The keys as the Engine reads them (e.g. "Ctrl+Alt+KeyL"): the key by its physical name, so any
 * keyboard layout records the same keys. Null while only modifiers are down. */
export function keysOf(e: Pressed): string | null {
	if (!e.code || MODIFIER_CODES.has(e.code)) return null;
	return [...modifiersOf(e), e.code].join('+');
}

/** "Ctrl+Alt+L" → ["Ctrl", "Alt", "L"], to show each as a key cap. */
export function keyCaps(keys: string): string[] {
	return keys.split('+').map((k) => k.trim());
}

// --- What a Hotkey does ----------------------------------------------------------------

export type Choice =
	| 'toggle'
	| 'on'
	| 'off'
	| 'brightness_up'
	| 'brightness_down'
	| 'brightness'
	| 'color'
	| 'temp_up'
	| 'temp_down'
	| 'climate'
	| 'press'
	| 'open_app';

export interface Params {
	/** % for brightness, ° for temperature. */
	step: number;
	brightness: number;
	/** #rrggbb */
	color: string;
	mode: string;
	temp: number;
	button: string;
	app: string;
}

export const DEFAULT_PARAMS: Params = {
	step: 10,
	brightness: 50,
	color: '#ffb44a',
	mode: '',
	temp: 24,
	button: '',
	app: ''
};

/** What a target can do, for the choices. */
export interface Abilities {
	control: 'light' | 'plug' | 'climate' | 'remote' | 'streamer' | 'power' | null;
	/** Has power that can be toggled (a Power Toggle counts). */
	toggle: boolean;
	/** Can be turned on or off for sure. */
	onOff: boolean;
	color: boolean;
	buttons: { name: string; label: string }[];
	apps: { name: string; app: string }[];
	modes: string[];
}

export function choicesFor(a: Abilities): { value: Choice; label: string }[] {
	const out: { value: Choice; label: string }[] = [];
	if (a.toggle) out.push({ value: 'toggle', label: 'Toggle on and off' });
	if (a.onOff) out.push({ value: 'on', label: 'Turn on' }, { value: 'off', label: 'Turn off' });
	if (a.control === 'light') {
		out.push(
			{ value: 'brightness_up', label: 'Brightness up' },
			{ value: 'brightness_down', label: 'Brightness down' },
			{ value: 'brightness', label: 'Set brightness' }
		);
		if (a.color) out.push({ value: 'color', label: 'Set colour' });
	}
	if (a.control === 'climate') {
		out.push(
			{ value: 'temp_up', label: 'Temperature up' },
			{ value: 'temp_down', label: 'Temperature down' },
			{ value: 'climate', label: 'Set mode and temperature' }
		);
	}
	if (a.buttons.length) out.push({ value: 'press', label: 'Press a button' });
	if (a.control === 'streamer') out.push({ value: 'open_app', label: 'Open an app' });
	return out;
}

function hex(rgb: RGB): string {
	return '#' + rgb.map((v) => v.toString(16).padStart(2, '0')).join('');
}

function rgbOf(color: string): RGB {
	const n = parseInt(color.slice(1), 16);
	return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

export function actionOf(choice: Choice, p: Params): HotkeyAction {
	switch (choice) {
		case 'toggle':
			return { do: 'toggle' };
		case 'on':
		case 'off':
			return { do: 'set', state: { on: choice === 'on' } };
		case 'brightness_up':
		case 'brightness_down':
			return { do: 'step', field: 'brightness', by: choice === 'brightness_up' ? p.step : -p.step };
		case 'temp_up':
		case 'temp_down':
			return { do: 'step', field: 'target_temp', by: choice === 'temp_up' ? p.step : -p.step };
		case 'brightness':
			return { do: 'set', state: { brightness: p.brightness } };
		case 'color':
			return { do: 'set', state: { rgb: rgbOf(p.color) } };
		case 'climate':
			return { do: 'set', state: { ...(p.mode ? { mode: p.mode } : {}), target_temp: p.temp } };
		case 'press':
			return { do: 'press', button: p.button };
		case 'open_app':
			return { do: 'open_app', app: p.app };
	}
}

/** The editor's choice and fields for a saved action. */
export function choiceOf(action: HotkeyAction): { choice: Choice; params: Partial<Params> } {
	switch (action.do) {
		case 'toggle':
			return { choice: 'toggle', params: {} };
		case 'press':
			return { choice: 'press', params: { button: action.button } };
		case 'open_app':
			return { choice: 'open_app', params: { app: action.app } };
		case 'step': {
			const up = action.by > 0;
			const choice =
				action.field === 'brightness' ? (up ? 'brightness_up' : 'brightness_down') : up ? 'temp_up' : 'temp_down';
			return { choice, params: { step: Math.abs(action.by) } };
		}
		case 'set': {
			const s = action.state;
			if (s.rgb) return { choice: 'color', params: { color: hex(s.rgb) } };
			if (s.brightness !== undefined) return { choice: 'brightness', params: { brightness: s.brightness } };
			if (s.target_temp !== undefined || s.mode !== undefined)
				return { choice: 'climate', params: { temp: s.target_temp ?? 24, mode: s.mode ?? '' } };
			return { choice: s.on === false ? 'off' : 'on', params: {} };
		}
	}
}

/** The step's unit and its usual size, for the field next to it. */
export function stepOf(choice: Choice): { unit: string; normal: number; max: number } | null {
	if (choice === 'brightness_up' || choice === 'brightness_down') return { unit: '%', normal: 10, max: 50 };
	if (choice === 'temp_up' || choice === 'temp_down') return { unit: '°', normal: 1, max: 5 };
	return null;
}
