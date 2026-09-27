import { describe, expect, it } from 'vitest';
import { glowFor, hexToRgb, hsToRgb, kelvinToRgb, rgbToHs } from './color';

describe('kelvinToRgb', () => {
	it('is warm at low kelvin and cool at high kelvin', () => {
		const [r2700, , b2700] = kelvinToRgb(2700);
		const [r6500, , b6500] = kelvinToRgb(6500);
		expect(r2700).toBe(255);
		expect(b2700).toBeLessThan(200);
		expect(b6500).toBeGreaterThan(b2700);
		expect(r6500).toBeGreaterThanOrEqual(250);
	});

	it('stays within 0-255', () => {
		for (const k of [500, 1700, 4000, 6500, 50000]) {
			for (const c of kelvinToRgb(k)) {
				expect(c).toBeGreaterThanOrEqual(0);
				expect(c).toBeLessThanOrEqual(255);
			}
		}
	});
});

describe('glowFor', () => {
	it("uses a light's real colour", () => {
		expect(glowFor('light', { rgb: [255, 0, 0] })).toBe('rgb(255 0 0)');
		expect(glowFor('light', { kelvin: 2700, rgb: null })).toMatch(/^rgb\(255 /);
	});

	it('tints climate by mode and plugs with the accent', () => {
		expect(glowFor('climate', { mode: 'heat' })).toBe('var(--heat)');
		expect(glowFor('climate', { mode: 'cool' })).toBe('var(--cool)');
		expect(glowFor('plug', {})).toBe('var(--accent)');
	});
});

it('hexToRgb', () => {
	expect(hexToRgb('#007aff')).toEqual([0, 122, 255]);
});

describe('colour wheel', () => {
	it('puts red, green and blue a third of the way round each, and white in the middle', () => {
		expect(hsToRgb(0, 1)).toEqual([255, 0, 0]);
		expect(hsToRgb(120, 1)).toEqual([0, 255, 0]);
		expect(hsToRgb(240, 1)).toEqual([0, 0, 255]);
		expect(hsToRgb(200, 0)).toEqual([255, 255, 255]);
	});

	it('finds a colour where it put it', () => {
		for (const [hue, sat] of [
			[30, 1],
			[200, 0.5],
			[330, 0.8]
		]) {
			const back = rgbToHs(hsToRgb(hue, sat));
			expect(back.hue).toBeCloseTo(hue, 0);
			expect(back.sat).toBeCloseTo(sat, 1);
		}
	});
});
