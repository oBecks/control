// Home's live view of the Engine: devices, their states, optimistic changes, polling.
import { api, ApiError, type Device, type DeviceState, type ScanResult } from './api';
import type { StateChange } from './types';

const POLL_MS = 8000;

class Home {
	devices = $state<Device[]>([]);
	states = $state<Record<string, DeviceState>>({});
	/** Result of each device's last state read: true = didn't answer. Beats the Scan's view, which can go stale. */
	unreachable = $state<Record<string, boolean>>({});
	loaded = $state(false);
	engineDown = $state(false);
	scanning = $state(false);
	toast = $state<string | null>(null);

	/** Devices with a change in flight: polling must not overwrite their optimistic state. */
	#pending = new Set<string>();
	#timer: ReturnType<typeof setInterval> | undefined;

	/** Controllable devices only; Transmitters and not-yet-ready devices live in Add Devices. */
	controllable = $derived(this.devices.filter((d) => d.control !== null));
	newCount = $derived(this.devices.filter((d) => d.is_new).length);

	isOffline(d: Device) {
		return this.unreachable[d.uid] ?? !d.online;
	}

	start() {
		this.refresh();
		this.#timer = setInterval(() => {
			if (document.visibilityState === 'visible') this.refresh();
		}, POLL_MS);
		const onVisible = () => document.visibilityState === 'visible' && this.refresh();
		document.addEventListener('visibilitychange', onVisible);
		return () => {
			clearInterval(this.#timer);
			document.removeEventListener('visibilitychange', onVisible);
		};
	}

	async refresh() {
		try {
			this.devices = await api.devices();
			this.engineDown = false;
		} catch (e) {
			this.engineDown = e instanceof ApiError && e.status === 0;
			return;
		} finally {
			this.loaded = true;
		}
		// Offline devices are asked too: a Scan can miss a reply, and a direct answer brings them back.
		await Promise.all(this.controllable.map((d) => this.#readState(d.uid)));
	}

	async #readState(uid: string) {
		if (this.#pending.has(uid)) return;
		try {
			const s = await api.state(uid);
			if (!this.#pending.has(uid)) this.states[uid] = s;
			this.unreachable[uid] = false;
		} catch (e) {
			if (e instanceof ApiError && e.unreachable) this.unreachable[uid] = true;
		}
	}

	/** A Remote Device to open Learning for when Add Devices opens ("Teach more buttons"). */
	teachTarget = $state<string | null>(null);

	/** Bumped each time a Signal is sent to a remote, so its Tile can flash a confirmation. */
	pulses = $state<Record<string, number>>({});

	toggle(uid: string) {
		const s = this.states[uid];
		if (!s) return;
		if (s.control === 'remote') {
			if (!s.features.can_power) return this.notify('Teach its Power button first');
			this.pulses[uid] = (this.pulses[uid] ?? 0) + 1;
			// Power Toggle: just press it. Discrete On/Off: flip the Assumed State.
			return this.change(uid, s.features.discrete_power ? { on: !s.state.on } : { press: 'power' });
		}
		this.change(uid, { on: !s.state.on });
	}

	/** Apply locally at once, send to the Engine, then take the Engine's answer as truth. */
	async change(uid: string, change: StateChange) {
		const before = this.states[uid];
		if (before) this.states[uid] = optimistic(before, change);
		this.#pending.add(uid);
		try {
			this.states[uid] = await api.setState(uid, change);
			this.unreachable[uid] = false;
		} catch (e) {
			if (before) this.states[uid] = before;
			if (e instanceof ApiError && e.unreachable) this.unreachable[uid] = true;
			this.notify(e instanceof Error ? e.message : String(e));
		} finally {
			this.#pending.delete(uid);
		}
	}

	/** Rename a Device. An empty name resets a network device to the name it reports itself. */
	async rename(uid: string, name: string): Promise<boolean> {
		try {
			const updated = await api.patch(uid, { name: name.trim() });
			this.devices = this.devices.map((d) => (d.uid === uid ? updated : d));
			return true;
		} catch (e) {
			this.notify(e instanceof Error ? e.message : String(e));
			return false;
		}
	}

	/** Scan the network; returns the result, or null if it failed (already reported). */
	async scan(): Promise<ScanResult | null> {
		this.scanning = true;
		try {
			const r = await api.scan();
			await this.refresh();
			return r;
		} catch (e) {
			this.notify(e instanceof Error ? e.message : String(e));
			return null;
		} finally {
			this.scanning = false;
		}
	}

	async findAgain() {
		const r = await this.scan();
		if (!r) return;
		const moved = Object.keys(r.moved).length;
		this.notify(moved ? `Found ${moved} device${moved > 1 ? 's' : ''} at a new address` : 'Scan finished');
	}

	notify(message: string) {
		this.toast = message;
		setTimeout(() => {
			if (this.toast === message) this.toast = null;
		}, 4000);
	}
}

/** The Engine's rule, mirrored for instant feedback: changing a setting also turns a device on. */
function optimistic(s: DeviceState, change: StateChange): DeviceState {
	// A button press isn't a state change; the Engine's answer tells us any effect.
	if (change.press) return s;
	const next = structuredClone($state.snapshot(s)) as DeviceState;
	const st = next.state as unknown as Record<string, unknown>;
	for (const [k, v] of Object.entries(change)) if (v !== undefined) st[k] = v;
	if (change.on === undefined && Object.keys(change).length) st.on = true;
	if (next.control === 'light') {
		if (change.rgb) Object.assign(next.state, { mode: 'color' });
		if (change.kelvin) Object.assign(next.state, { mode: 'white', rgb: null });
	}
	return next;
}

export const home = new Home();
