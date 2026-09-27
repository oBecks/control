// What the builder's When and Only if editors offer to pick: Devices and Groups whose on/off Control
// knows, TV boxes and their apps, and Devices with a connection of their own. Read inside $derived,
// these follow the home store as it changes.
import { home } from '$lib/home.svelte';

export interface PickTarget {
	uid: string;
	name: string;
	group: boolean;
}

/** Groups, then Devices whose on/off Control knows: not a Power Toggle. Groups always know. */
export function onOffTargets(): PickTarget[] {
	return [
		...home.groups.map((g) => ({ uid: g.uid, name: g.name, group: true })),
		...home.controllable.filter((d) => !d.group_problem).map((d) => ({ uid: d.uid, name: d.name, group: false }))
	];
}

export function streamerDevices() {
	return home.controllable.filter((d) => d.control === 'streamer');
}

/** A TV box's apps, which arrive with its state (empty until then). */
export function appsOf(uid: string) {
	const st = home.states[uid];
	return st?.control === 'streamer' ? st.features.apps : [];
}

/** Devices with a connection of their own: an AC, TV or fan behind a Hub is never offline itself. */
export function connectedDevices() {
	return home.controllable.filter(
		(d) => d.kind === 'network' && ['light', 'plug', 'streamer'].includes(d.control ?? '')
	);
}
