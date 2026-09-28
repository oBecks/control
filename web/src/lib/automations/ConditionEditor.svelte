<script lang="ts">
	// One "Only if" of an Automation: a Device's or Group's state, a Streamer's app, a Scene being
	// active, a time window, some days, or dark or light. Checked once, when a Trigger fires.
	import { Trash2 } from '@lucide/svelte';
	import { home } from '$lib/home.svelte';
	import type { Condition, HomeLocation, Weekday } from '$lib/types';
	import Button from '$lib/ui/Button.svelte';
	import Segmented from '$lib/ui/Segmented.svelte';
	import DaysPicker from './DaysPicker.svelte';
	import LocationPicker from './LocationPicker.svelte';
	import './editor.css';
	import OnOffTargetSelect from './OnOffTargetSelect.svelte';
	import { EVERY_DAY } from './parts';
	import { appsOf, onOffTargets, streamerDevices } from './targets';

	interface Props {
		/** The Condition to change; none to add one. */
		condition?: Condition;
		location: HomeLocation | null;
		onlocation: (location: HomeLocation) => void;
		/** Keep it: answers why it can't be, or null. */
		onsave: (condition: Condition) => Promise<string | null>;
		onremove?: () => void;
		onclose: () => void;
	}

	let { condition, location, onlocation, onsave, onremove, onclose }: Props = $props();

	const initial = (() => condition)();
	let type = $state<Condition['type']>(initial?.type ?? 'state');
	let target = $state(
		initial?.type === 'state' || initial?.type === 'app' || initial?.type === 'scene' ? initial.target : ''
	);
	let on = $state(initial?.type === 'state' ? initial.on : true);
	let active = $state(initial?.type === 'scene' ? initial.active : true);
	let app = $state(initial?.type === 'app' ? initial.app : '');
	let after = $state(initial?.type === 'time' ? initial.after : '22:00');
	let before = $state(initial?.type === 'time' ? initial.before : '06:00');
	let days = $state<Weekday[]>(initial?.type === 'days' ? initial.days : [...EVERY_DAY]);
	let is = $state<'dark' | 'light'>(initial?.type === 'sun' ? initial.is : 'dark');
	let problem = $state<string | null>(null);
	let saving = $state(false);

	const withState = $derived(onOffTargets());
	const streamers = $derived(streamerDevices());
	const apps = $derived(appsOf(target));

	const KINDS = $derived([
		{ value: 'state', label: 'A device or group is on or off' },
		...(streamers.length || initial?.type === 'app' ? [{ value: 'app', label: 'A TV box has an app open' }] : []),
		...(home.scenes.length || initial?.type === 'scene'
			? [{ value: 'scene', label: 'A scene is active, or not' }]
			: []),
		{ value: 'time', label: 'It’s between two times' },
		{ value: 'days', label: 'It’s one of some days' },
		{ value: 'sun', label: 'It’s dark, or light' }
	]);

	function pickKind(next: Condition['type']) {
		type = next;
		if (next === 'app' && !streamers.some((s) => s.uid === target)) target = streamers[0]?.uid ?? '';
		if (next === 'state' && !withState.some((t) => t.uid === target)) target = '';
		if (next === 'scene' && !home.scenes.some((sc) => sc.uid === target)) target = '';
	}

	// A TV box's apps arrive with its state.
	$effect(() => {
		if (type === 'app' && apps.length && !apps.some((a) => a.app === app)) app = apps[0].app;
	});

	const built = $derived.by((): Condition | null => {
		switch (type) {
			case 'state':
				return target ? { type, target, on } : null;
			case 'app':
				return target && app ? { type, target, app } : null;
			case 'scene':
				return target ? { type, target, active } : null;
			case 'time':
				return { type, after, before };
			case 'days':
				return { type, days };
			case 'sun':
				return { type, is };
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
	<h2>{initial ? 'Only if' : 'Add an Only if'}</h2>

	<label class="field">
		<span>Only if</span>
		<select value={type} onchange={(e) => pickKind(e.currentTarget.value as Condition['type'])}>
			{#each KINDS as k (k.value)}<option value={k.value}>{k.label}</option>{/each}
		</select>
	</label>

	{#if type === 'state'}
		<label class="field">
			<span>Device or group</span>
			<OnOffTargetSelect bind:value={target} targets={withState} />
		</label>
		<Segmented
			label="Is"
			options={[
				{ value: 'on', label: 'Is on' },
				{ value: 'off', label: 'Is off' }
			]}
			value={on ? 'on' : 'off'}
			onchange={(v) => (on = v === 'on')}
		/>
		<p class="hint">
			A group counts as on while any of its devices is. For an AC, TV or fan this is what Control last set, since it
			can't see the physical remote.
		</p>
	{:else if type === 'app'}
		<label class="field">
			<span>TV box</span>
			<select bind:value={target} required>
				{#each streamers as s (s.uid)}<option value={s.uid}>{s.name}</option>{/each}
			</select>
		</label>
		<label class="field">
			<span>Has open</span>
			<select bind:value={app} required>
				{#if !apps.length}<option value={app}>{app || 'Loading its apps…'}</option>{/if}
				{#each apps as a (a.app)}<option value={a.app}>{a.name}</option>{/each}
			</select>
		</label>
	{:else if type === 'scene'}
		<label class="field">
			<span>Scene</span>
			<select bind:value={target} required>
				<option value="" disabled>Pick a scene</option>
				{#each home.scenes as sc (sc.uid)}<option value={sc.uid}>{sc.name}</option>{/each}
			</select>
		</label>
		<Segmented
			label="Is"
			options={[
				{ value: 'active', label: 'Is active' },
				{ value: 'inactive', label: 'Isn’t active' }
			]}
			value={active ? 'active' : 'inactive'}
			onchange={(v) => (active = v === 'active')}
		/>
		<p class="hint">
			Active while every device in it is as the scene says, however it got that way. A device that doesn’t answer counts
			as not.
		</p>
	{:else if type === 'time'}
		<div class="amounts">
			<span>From</span>
			<input type="time" bind:value={after} aria-label="From" required />
			<span>until</span>
			<input type="time" bind:value={before} aria-label="Until" required />
		</div>
		<p class="hint">It may cross midnight, like 22:00 until 06:00.</p>
	{:else if type === 'days'}
		<DaysPicker bind:days />
	{:else if !location}
		<LocationPicker {location} onchange={onlocation} />
	{:else}
		<Segmented
			label="It's"
			options={[
				{ value: 'dark', label: 'Dark' },
				{ value: 'light', label: 'Light' }
			]}
			bind:value={is}
		/>
		<p class="hint">Dark is from sunset until sunrise in {location.name}.</p>
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
