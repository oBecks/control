// How a Device or Group looks on Home: icon, status line, glow, section. Shared by Home and Device Controls.
// Per-icon imports: the barrel pulls in every icon, which makes unit tests very slow to start.
import AirVent from '@lucide/svelte/icons/air-vent';
import Fan from '@lucide/svelte/icons/fan';
import Gamepad2 from '@lucide/svelte/icons/gamepad-2';
import Layers from '@lucide/svelte/icons/layers';
import Lightbulb from '@lucide/svelte/icons/lightbulb';
import LightbulbOff from '@lucide/svelte/icons/lightbulb-off';
import Plug from '@lucide/svelte/icons/plug';
import Tv from '@lucide/svelte/icons/tv';
import TvMinimalPlay from '@lucide/svelte/icons/tv-minimal-play';
import type { Device, DeviceState, Group, GroupState } from './api';
import { glowFor } from './color';

const MODE_LABEL: Record<string, string> = {
	cool: 'Cool',
	heat: 'Heat',
	fan: 'Fan',
	fan_only: 'Fan',
	dry: 'Dry',
	auto: 'Auto'
};

export function iconFor(d: Device, s?: DeviceState): typeof Lightbulb {
	switch (d.control) {
		case 'light':
			return s && !s.state.on ? LightbulbOff : Lightbulb;
		case 'climate':
			return AirVent;
		case 'plug':
			return Plug;
		case 'streamer':
			return d.is_tv ? Tv : TvMinimalPlay;
		default:
			return d.category === 'media' ? Tv : d.category === 'climate' ? Fan : Gamepad2;
	}
}

export function statusFor(s?: DeviceState): string {
	if (!s) return '…';
	// Power Toggle remotes never claim on/off.
	if (s.control === 'remote' && s.state.on === null) return 'Tap for Power';
	if (!s.state.on) return 'Off';
	if (s.control === 'light') return `On · ${s.state.brightness}%`;
	if (s.control === 'climate') return `${MODE_LABEL[s.state.mode] ?? s.state.mode} ${s.state.target_temp}°`;
	if (s.control === 'streamer') return s.state.app_name ?? 'On';
	return 'On';
}

/** Whether the Tile lights up. Remotes with a Power Toggle never do: their state is unknown. */
export function isOn(s?: DeviceState): boolean {
	return !!s?.state.on;
}

export function glowOf(d: Device, s?: DeviceState): string | undefined {
	if (!s) return undefined;
	if (s.control === 'remote') return d.category === 'climate' ? 'var(--fan)' : 'var(--accent)';
	if (s.control === 'streamer') return 'var(--accent)';
	return glowFor(
		s.control,
		s.state as { mode?: string; rgb?: [number, number, number] | null; kelvin?: number | null }
	);
}

export function groupIcon(g: Group, s?: GroupState): typeof Lightbulb {
	if (g.control === 'light') return s && !s.state.on ? LightbulbOff : Lightbulb;
	if (g.control === 'climate') return AirVent;
	return { plug: Plug, media: Tv, climate: Fan, light: Lightbulb }[g.category] ?? Layers;
}

/** "Off", "2 of 3 on", or when all are on, what a single Device would say ("On · 60%", "Cool 22°"). */
export function groupStatus(s?: GroupState): string {
	if (!s) return '…';
	if (s.on_count === 0 || !s.state.on) return 'Off';
	if (s.on_count < s.total) return `${s.on_count} of ${s.total} on`;
	if (s.control === 'light') return `On · ${s.state.brightness}%`;
	if (s.control === 'climate') return `${MODE_LABEL[s.state.mode] ?? s.state.mode} ${s.state.target_temp}°`;
	return 'All on';
}

export function groupGlow(s?: GroupState): string | undefined {
	if (!s) return undefined;
	return glowFor(
		s.control === 'power' ? 'plug' : s.control,
		s.state as { mode?: string; rgb?: [number, number, number] | null; kelvin?: number | null }
	);
}

/** Home sections, by Category (fans sit under Climate). */
export const SECTIONS: { category: string; title: string }[] = [
	{ category: 'light', title: 'Lights' },
	{ category: 'climate', title: 'Climate' },
	{ category: 'media', title: 'Media' },
	{ category: 'plug', title: 'Plugs' },
	{ category: 'unknown', title: 'Other' }
];

/** The name a Streamer's setup suggests, so it doesn't read like the TV (or, for a TV, does):
 * "TV – Living room" becomes "Streamer – Living room"; any other name gets "Streamer " in front. */
export function streamerName(networkName: string, isTv: boolean): string {
	const want = isTv ? 'TV' : 'Streamer';
	const other = isTv ? 'Streamer' : 'TV';
	const name = networkName.trim();
	if (name.toLowerCase().startsWith(want.toLowerCase())) return name;
	const rest = name.slice(other.length);
	if (name.toLowerCase().startsWith(other.toLowerCase()) && !/^[a-z]/i.test(rest)) return want + rest;
	return `${want} ${name}`.trim();
}

export function greeting(now = new Date()): string {
	const h = now.getHours();
	return h < 5 ? 'Good night' : h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening';
}
