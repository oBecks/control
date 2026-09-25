import { describe, expect, it } from 'vitest';
import type { DeviceState } from './api';
import { isOn, statusFor } from './present';

const remote = (on: boolean | null, discrete: boolean): DeviceState => ({
	control: 'remote',
	features: { kind: 'tv', buttons: [], discrete_power: discrete, can_power: true },
	state: { on },
	assumed: true
});

describe('statusFor', () => {
	it('shows brightness for lights and mode + temperature for ACs', () => {
		expect(
			statusFor({
				control: 'light',
				features: { color: true, color_temp: true, min_kelvin: 1700, max_kelvin: 6500 },
				state: { on: true, brightness: 30, mode: 'white', rgb: null, kelvin: 3000 }
			})
		).toBe('On · 30%');
		expect(
			statusFor({
				control: 'climate',
				features: { modes: [], fan_modes: [], swing_modes: [], min_temp: 16, max_temp: 30, step: 1 },
				state: { on: true, mode: 'cool', target_temp: 22, fan: 'low', swing: null },
				assumed: true
			})
		).toBe('Cool 22°');
	});

	it('never claims on/off for a Power Toggle remote', () => {
		expect(statusFor(remote(null, false))).toBe('Tap for Power');
		expect(isOn(remote(null, false))).toBe(false);
	});

	it('shows the Assumed State of a remote with separate On/Off', () => {
		expect(statusFor(remote(true, true))).toBe('On');
		expect(isOn(remote(true, true))).toBe(true);
	});

	it('shows a placeholder while loading', () => {
		expect(statusFor(undefined)).toBe('…');
	});
});
