import { describe, expect, it } from 'vitest';
import { actionOf, choiceOf, choicesFor, DEFAULT_PARAMS, keyCaps, keysOf, type Abilities } from './keys';

const none = { ctrlKey: false, altKey: false, shiftKey: false, metaKey: false };

describe('recording keys', () => {
	it('writes modifiers first, then the key by its physical name', () => {
		expect(keysOf({ ...none, ctrlKey: true, altKey: true, code: 'KeyL' })).toBe('Ctrl+Alt+KeyL');
		expect(keysOf({ ...none, metaKey: true, shiftKey: true, code: 'F13' })).toBe('Shift+Win+F13');
		expect(keysOf({ ...none, code: 'MediaPlayPause' })).toBe('MediaPlayPause');
	});

	it('waits while only modifiers are down', () => {
		expect(keysOf({ ...none, ctrlKey: true, code: 'ControlLeft' })).toBeNull();
		expect(keysOf({ ...none, altKey: true, code: 'AltRight' })).toBeNull();
		expect(keysOf({ ...none, code: '' })).toBeNull();
	});

	it('splits keys into caps', () => {
		expect(keyCaps('Ctrl+Alt+L')).toEqual(['Ctrl', 'Alt', 'L']);
		expect(keyCaps('Volume Up')).toEqual(['Volume Up']);
	});
});

const light: Abilities = {
	control: 'light',
	toggle: true,
	onOff: true,
	color: true,
	buttons: [],
	apps: [],
	modes: []
};

describe('what a Hotkey does', () => {
	it('offers what the target can do', () => {
		const values = (a: Abilities) => choicesFor(a).map((c) => c.value);
		expect(values(light)).toEqual(['toggle', 'on', 'off', 'brightness_up', 'brightness_down', 'brightness', 'color']);
		expect(values({ ...light, color: false })).not.toContain('color');
		const tv: Abilities = { ...light, control: 'remote', onOff: false, buttons: [{ name: 'power', label: 'Power' }] };
		expect(values(tv)).toEqual(['toggle', 'press']);
		expect(values({ ...light, control: 'streamer', buttons: tv.buttons })).toEqual([
			'toggle',
			'on',
			'off',
			'press',
			'open_app'
		]);
		expect(values({ ...light, control: 'climate' })).toContain('temp_up');
	});

	it('turns choices into actions and back', () => {
		const p = { ...DEFAULT_PARAMS, step: 20, color: '#ff8000', mode: 'cool', temp: 22, button: 'mute' };
		for (const choice of ['toggle', 'on', 'off', 'brightness_down', 'temp_up', 'color', 'climate', 'press'] as const) {
			const action = actionOf(choice, p);
			expect(choiceOf(action).choice).toBe(choice);
		}
		expect(actionOf('brightness_down', p)).toEqual({ do: 'step', field: 'brightness', by: -20 });
		expect(actionOf('color', p)).toEqual({ do: 'set', state: { rgb: [255, 128, 0] } });
		expect(choiceOf(actionOf('color', p)).params.color).toBe('#ff8000');
		expect(choiceOf({ do: 'step', field: 'target_temp', by: -2 }).params.step).toBe(2);
	});
});
