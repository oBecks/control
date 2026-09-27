<script lang="ts">
	// One "When" of an Automation: a time, sunrise or sunset on some days, or a Device changing: a
	// Device or Group turning on or off (and staying so a while), a TV box opening an app, a Device
	// going offline or coming back. The Engine listens to the Devices these name (ADR 0011).
	import { Trash2 } from '@lucide/svelte';
	import { home } from '$lib/home.svelte';
	import type { HomeLocation, Trigger, Weekday } from '$lib/types';
	import Button from '$lib/ui/Button.svelte';
	import Segmented from '$lib/ui/Segmented.svelte';
	import DaysPicker from './DaysPicker.svelte';
	import LocationPicker from './LocationPicker.svelte';
	import './editor.css';
	import { EVERY_DAY } from './parts';

	interface Props {
		/** The Trigger to change; none to add one. */
		trigger?: Trigger;
		location: HomeLocation | null;
		onlocation: (location: HomeLocation) => void;
		/** Keep it: answers why it can't be, or null. */
		onsave: (trigger: Trigger) => Promise<string | null>;
		onremove?: () => void;
		onclose: () => void;
	}

	let { trigger, location, onlocation, onsave, onremove, onclose }: Props = $props();

	const initial = (() => trigger)();
	const timed = initial?.type === 'time' || initial?.type === 'sun';
	let type = $state<Trigger['type']>(initial?.type ?? 'time');
	let at = $state(initial?.type === 'time' ? initial.at : '07:00');
	let event = $state<'sunrise' | 'sunset'>(initial?.type === 'sun' ? initial.event : 'sunset');
	let minutes = $state(initial?.type === 'sun' ? Math.abs(initial.offset) : 0);
	let side = $state<'before' | 'after'>(initial?.type === 'sun' && initial.offset < 0 ? 'before' : 'after');
	let days = $state<Weekday[]>(timed ? initial.days : [...EVERY_DAY]);
	let target = $state(initial && !timed ? initial.target : '');
	let on = $state(initial?.type === 'state' ? initial.on : true);
	let stays = $state(initial?.type === 'state' ? initial.minutes : 0);
	let app = $state(initial?.type === 'app' ? initial.app : '');
	let offline = $state(initial?.type === 'offline' ? initial.offline : true);
	let problem = $state<string | null>(null);
	let saving = $state(false);

	/** Devices whose on/off Control knows: not a Power Toggle. Groups always know. */
	const withState = $derived([
		...home.groups.map((g) => ({ uid: g.uid, name: g.name, group: true })),
		...home.controllable.filter((d) => !d.group_problem).map((d) => ({ uid: d.uid, name: d.name, group: false }))
	]);
	const streamers = $derived(home.controllable.filter((d) => d.control === 'streamer'));
	/** Devices with a connection of their own: an AC, TV or fan behind a Hub is never offline itself. */
	const connected = $derived(
		home.controllable.filter((d) => d.kind === 'network' && ['light', 'plug', 'streamer'].includes(d.control ?? ''))
	);
	const apps = $derived.by(() => {
		const st = home.states[target];
		return st?.control === 'streamer' ? st.features.apps : [];
	});

	const KINDS = $derived([
		{ value: 'time', label: 'At a time' },
		{ value: 'sun', label: 'At sunrise or sunset' },
		{ value: 'state', label: 'A device or group turns on or off' },
		...(streamers.length || initial?.type === 'app' ? [{ value: 'app', label: 'A TV box opens an app' }] : []),
		{ value: 'offline', label: 'A device goes offline or comes back' }
	]);

	function pickKind(next: Trigger['type']) {
		type = next;
		const choices = next === 'state' ? withState : next === 'app' ? streamers : next === 'offline' ? connected : [];
		if (!choices.some((c) => c.uid === target)) target = next === 'app' ? (streamers[0]?.uid ?? '') : '';
	}

	// A TV box's apps arrive with its state.
	$effect(() => {
		if (type === 'app' && apps.length && !apps.some((a) => a.app === app)) app = apps[0].app;
	});

	const built = $derived.by((): Trigger | null => {
		switch (type) {
			case 'time':
				return { type, at, days };
			case 'sun':
				return { type, event, offset: side === 'before' ? -minutes : minutes, days };
			case 'state':
				return target ? { type, target, on, minutes: stays || 0 } : null;
			case 'app':
				return target && app ? { type, target, app } : null;
			case 'offline':
				return target ? { type, target, offline } : null;
		}
	});

	async function save(e: SubmitEvent) {
		e.preventDefault();
		if (!built) return;
		saving = true;
		problem = await onsave(built);
		saving = false;
	}
</script>

<form class="part-editor" onsubmit={save}>
	<h2>{initial ? 'When' : 'Add a When'}</h2>

	<label class="field">
		<span>When</span>
		<select value={type} onchange={(e) => pickKind(e.currentTarget.value as Trigger['type'])}>
			{#each KINDS as k (k.value)}<option value={k.value}>{k.label}</option>{/each}
		</select>
	</label>

	{#if type === 'time'}
		<label class="field inline">
			<span>Time</span>
			<input type="time" bind:value={at} required />
		</label>
	{:else if type === 'sun' && !location}
		<LocationPicker {location} onchange={onlocation} />
	{:else if type === 'sun' && location}
		<Segmented
			label="Sun"
			options={[
				{ value: 'sunrise', label: 'Sunrise' },
				{ value: 'sunset', label: 'Sunset' }
			]}
			bind:value={event}
		/>
		<div class="offset">
			<input type="number" min="0" max="180" step="1" bind:value={minutes} aria-label="Minutes" required />
			<span>min</span>
			<select bind:value={side} aria-label="Before or after">
				<option value="before">before</option>
				<option value="after">after</option>
			</select>
			<span>{event}</span>
		</div>
		<p class="hint">
			Today in {location.name}: sunrise {location.sunrise ?? '—'}, sunset {location.sunset ?? '—'}.
		</p>
	{:else if type === 'state'}
		<label class="field">
			<span>Device or group</span>
			<select bind:value={target} required>
				<option value="" disabled>Pick one</option>
				{#if home.groups.length}
					<optgroup label="Groups">
						{#each withState.filter((t) => t.group) as t (t.uid)}<option value={t.uid}>{t.name}</option>{/each}
					</optgroup>
				{/if}
				<optgroup label="Devices">
					{#each withState.filter((t) => !t.group) as t (t.uid)}<option value={t.uid}>{t.name}</option>{/each}
				</optgroup>
			</select>
		</label>
		<Segmented
			label="Turns"
			options={[
				{ value: 'on', label: 'Turns on' },
				{ value: 'off', label: 'Turns off' }
			]}
			value={on ? 'on' : 'off'}
			onchange={(v) => (on = v === 'on')}
		/>
		<div class="amounts">
			<span>and stays {on ? 'on' : 'off'} for</span>
			<input type="number" min="0" max="1440" step="1" bind:value={stays} aria-label="Minutes it stays so" />
			<span>min</span>
		</div>
		<p class="hint">
			0 starts it at once. A group turns on with its first device and off with its last. An AC, TV or fan changes only
			when Control sends it something, since Control can't see the physical remote.
		</p>
	{:else if type === 'app'}
		<label class="field">
			<span>TV box</span>
			<select bind:value={target} required>
				{#each streamers as s (s.uid)}<option value={s.uid}>{s.name}</option>{/each}
			</select>
		</label>
		<label class="field">
			<span>Opens</span>
			<select bind:value={app} required>
				{#if !apps.length}<option value={app}>{app || 'Loading its apps…'}</option>{/if}
				{#each apps as a (a.app)}<option value={a.app}>{a.name}</option>{/each}
			</select>
		</label>
	{:else}
		<label class="field">
			<span>Device</span>
			<select bind:value={target} required>
				<option value="" disabled>Pick one</option>
				{#each connected as d (d.uid)}<option value={d.uid}>{d.name}</option>{/each}
			</select>
		</label>
		<Segmented
			label="Goes"
			options={[
				{ value: 'offline', label: 'Goes offline' },
				{ value: 'online', label: 'Comes back online' }
			]}
			value={offline ? 'offline' : 'online'}
			onchange={(v) => (offline = v === 'offline')}
		/>
		<p class="hint">It counts as offline after a minute without answering, so a short Wi-Fi blip doesn't.</p>
	{/if}

	{#if type === 'time' || type === 'sun'}
		<div class="field">
			<span>Days</span>
			<DaysPicker bind:days />
		</div>
	{/if}

	{#if problem}<p class="problem">{problem}</p>{/if}

	<div class="actions">
		<Button type="submit" variant="primary" disabled={saving || !built || (type === 'sun' && !location)}>Done</Button>
		<Button type="button" variant="ghost" onclick={onclose}>Cancel</Button>
		{#if onremove}
			<span class="remove">
				<Button type="button" variant="ghost" onclick={onremove}><Trash2 size={15} strokeWidth={2.4} /> Remove</Button>
			</span>
		{/if}
	</div>
</form>
