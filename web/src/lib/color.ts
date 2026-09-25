export type RGB = [number, number, number];

/** Approximate colour of white light at a colour temperature (Tanner Helland's fit). */
export function kelvinToRgb(kelvin: number): RGB {
	const t = Math.min(Math.max(kelvin, 1000), 40000) / 100;
	const clamp = (v: number) => Math.round(Math.min(255, Math.max(0, v)));
	const r = t <= 66 ? 255 : 329.698727446 * Math.pow(t - 60, -0.1332047592);
	const g = t <= 66 ? 99.4708025861 * Math.log(t) - 161.1195681661 : 288.1221695283 * Math.pow(t - 60, -0.0755148492);
	const b = t >= 66 ? 255 : t <= 19 ? 0 : 138.5177312231 * Math.log(t - 10) - 305.0447927307;
	return [clamp(r), clamp(g), clamp(b)];
}

export const rgbCss = ([r, g, b]: RGB) => `rgb(${r} ${g} ${b})`;

export const hexToRgb = (hex: string): RGB => {
	const h = hex.replace('#', '');
	return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16)) as RGB;
};

/** The colour an "on" Tile takes: the light's real colour, the AC's mode tint, or the accent. */
export function glowFor(
	control: 'light' | 'plug' | 'climate',
	state: { mode?: string; rgb?: RGB | null; kelvin?: number | null }
): string {
	if (control === 'light') {
		if (state.rgb) return rgbCss(state.rgb);
		return rgbCss(kelvinToRgb(state.kelvin ?? 4000));
	}
	if (control === 'climate') {
		if (state.mode === 'heat') return 'var(--heat)';
		if (state.mode?.startsWith('fan')) return 'var(--fan)';
		return 'var(--cool)';
	}
	return 'var(--accent)';
}
