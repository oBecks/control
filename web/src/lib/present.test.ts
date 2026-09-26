import { describe, expect, it } from 'vitest';
import type { DeviceState, GroupState } from './api';
import { groupStatus, isOn, statusFor, streamerName } from './present';

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

const lights = (on_count: number, total: number): GroupState => ({
	control: 'light',
	features: { color: true, color_temp: true, min_kelvin: 1700, max_kelvin: 6500 },
	state: { on: on_count > 0, brightness: 60, mode: 'white', rgb: null, kelvin: 3000 },
	assumed: false,
	on_count,
	total,
	members: {},
	failed: {}
});

describe('groupStatus', () => {
	it('counts members while only some are on', () => {
		expect(groupStatus(lights(0, 3))).toBe('Off');
		expect(groupStatus(lights(2, 3))).toBe('2 of 3 on');
	});

	it('reads like a single Device once all are on', () => {
		expect(groupStatus(lights(3, 3))).toBe('On · 60%');
		expect(
			groupStatus({
				control: 'power',
				features: {},
				state: { on: true },
				assumed: false,
				on_count: 2,
				total: 2,
				members: {},
				failed: {}
			})
		).toBe('All on');
	});
});

describe('streamerName', () => {
	it("keeps a box from sounding like the TV it's plugged into", () => {
		expect(streamerName('TV – סלון', false)).toBe('Streamer – סלון');
		expect(streamerName('SHIELD', false)).toBe('Streamer SHIELD');
		expect(streamerName('Streamer – Den', false)).toBe('Streamer – Den');
		expect(streamerName('TVRoom box', false)).toBe('Streamer TVRoom box');
	});
	it('calls a TV a TV', () => {
		expect(streamerName('Streamer – Den', true)).toBe('TV – Den');
		expect(streamerName('BRAVIA', true)).toBe('TV BRAVIA');
		expect(streamerName('TV – Den', true)).toBe('TV – Den');
	});
});

describe('a Streamer', () => {
	it('says which app is open', () => {
		const s = (on: boolean, app_name: string | null): DeviceState => ({
			control: 'streamer',
			features: { buttons: [], apps: [], is_tv: false, adb: false },
			state: { on, app: null, app_name, volume: null, volume_max: null, muted: null }
		});
		expect(statusFor(s(true, 'Netflix'))).toBe('Netflix');
		expect(statusFor(s(true, null))).toBe('On');
		expect(statusFor(s(false, 'Netflix'))).toBe('Off');
	});
});
