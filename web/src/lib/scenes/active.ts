// Whether a Scene is active: every part as its Device reads (ADR 0013). Mirrors engine/scenes.py
// `matches`, so Home can light a chip from the readings it already polls.
import type { DeviceState } from '$lib/api';
import type { Scene, SceneState } from '$lib/types';

// Some brands round what they're sent (Tuya's 0-1000 scales, colours through HSV).
const BRIGHTNESS_SLACK = 1;
const RGB_SLACK = 6;
const KELVIN_SLACK = 50;

/** Whether one Device's reading is as the part's state says. An Assumed State counts. */
export function matches(want: SceneState, reading: DeviceState | undefined): boolean {
	if (!reading) return false;
	const s = reading.state as unknown as Record<string, unknown>;
	const on = want.on ?? true; // setting anything else turns it on
	if (s.on === null || s.on === undefined || Boolean(s.on) !== on) return false;
	if (!on) return true;
	const num = (k: string) => (typeof s[k] === 'number' ? (s[k] as number) : null);
	for (const [key, value] of Object.entries(want)) {
		if (key === 'on' || value === undefined) continue;
		if (key === 'brightness') {
			const b = num('brightness');
			if (b === null || Math.abs(b - (value as number)) > BRIGHTNESS_SLACK) return false;
		} else if (key === 'rgb') {
			const rgb = s.rgb as number[] | null;
			if (s.mode !== 'color' || !rgb || rgb.some((c, i) => Math.abs(c - (value as number[])[i]) > RGB_SLACK))
				return false;
		} else if (key === 'kelvin') {
			const k = num('kelvin');
			if (s.mode !== 'white' || k === null || Math.abs(k - (value as number)) > KELVIN_SLACK) return false;
		} else if (key === 'target_temp') {
			const t = num('target_temp');
			if (t === null || Math.abs(t - (value as number)) > 0.01) return false;
		} else if (s[key] !== value) {
			return false; // mode, fan, swing, app
		}
	}
	return true;
}

export interface Readings {
	/** A Device's reading, or undefined when it has none (or didn't answer). */
	reading: (uid: string) => DeviceState | undefined;
	/** A Group's members, or null for a Device. */
	members: (uid: string) => string[] | null;
	offline: (uid: string) => boolean;
}

/** Whether a part's Device (or every member of its Group) is as the part says. */
export function partActive(part: Scene['parts'][number], r: Readings): boolean {
	const uids = r.members(part.target) ?? [part.target];
	return uids.length > 0 && uids.every((u) => !r.offline(u) && matches(part.state, r.reading(u)));
}

export function sceneActive(scene: Scene, r: Readings): boolean {
	return scene.parts.length > 0 && scene.parts.every((p) => partActive(p, r));
}
