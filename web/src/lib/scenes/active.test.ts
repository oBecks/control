import { describe, expect, it } from 'vitest';
import type { DeviceState } from '$lib/api';
import type { Scene } from '$lib/types';
import { matches, sceneActive } from './active';

const light = (
	state: Partial<{ on: boolean; brightness: number; mode: string; rgb: number[] | null; kelvin: number | null }>
) =>
	({
		control: 'light',
		features: { color: true, color_temp: true, min_kelvin: 1700, max_kelvin: 6500 },
		state: { on: true, brightness: 50, mode: 'white', rgb: null, kelvin: 4000, ...state }
	}) as DeviceState;

const ac = (on: boolean | null, target_temp = 24) =>
	({
		control: 'climate',
		features: {},
		state: { on, mode: 'cool', target_temp, fan: 'low', swing: null },
		assumed: true
	}) as unknown as DeviceState;

describe('matches', () => {
	it('checks only what the part sets, with a little slack', () => {
		const r = light({ brightness: 21, kelvin: 2710 });
		expect(matches({ on: true }, r)).toBe(true);
		expect(matches({ brightness: 20, kelvin: 2700 }, r)).toBe(true);
		expect(matches({ brightness: 40 }, r)).toBe(false);
		expect(matches({ rgb: [255, 0, 0] }, r)).toBe(false);
	});

	it('off matches whatever else it has, and setting anything means on', () => {
		expect(matches({ on: false }, light({ on: false, brightness: 90 }))).toBe(true);
		expect(matches({ brightness: 50 }, light({ on: false }))).toBe(false);
	});

	it('counts an Assumed State, never an unknown power', () => {
		expect(matches({ mode: 'cool', target_temp: 24 }, ac(true))).toBe(true);
		expect(matches({ target_temp: 25 }, ac(true))).toBe(false);
		expect(matches({ on: false }, ac(null))).toBe(false);
		expect(matches({ on: true }, undefined)).toBe(false);
	});
});

describe('sceneActive', () => {
	const scene = (parts: Scene['parts']): Scene => ({
		uid: 'scene:1',
		name: 'Movie night',
		icon: 'clapperboard',
		parts,
		attention: null,
		made_by: 'user'
	});
	const part = (target: string, state: Scene['parts'][number]['state']) => ({
		target,
		state,
		target_name: target,
		label: ''
	});
	const readings: Record<string, DeviceState> = { a: light({}), b: light({ on: false }), ac: ac(true) };
	const r = (offline: string[] = []) => ({
		reading: (u: string) => readings[u],
		members: (u: string) => (u === 'group:ab' ? ['a', 'b'] : null),
		offline: (u: string) => offline.includes(u)
	});

	it('is active while every part matches', () => {
		expect(sceneActive(scene([part('a', { on: true }), part('ac', { target_temp: 24 })]), r())).toBe(true);
		expect(sceneActive(scene([part('a', { on: true }), part('b', { on: true })]), r())).toBe(false);
	});

	it('needs every member of a Group, and nothing Offline', () => {
		expect(sceneActive(scene([part('group:ab', { on: true })]), r())).toBe(false);
		expect(sceneActive(scene([part('a', { on: true })]), r(['a']))).toBe(false);
	});

	it('an empty Scene is never active', () => {
		expect(sceneActive(scene([]), r())).toBe(false);
	});
});
