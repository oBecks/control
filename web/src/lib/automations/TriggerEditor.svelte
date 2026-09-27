<script lang="ts">
	// One "When" of an Automation: a time, or sunrise or sunset, on some days.
	import { Trash2 } from '@lucide/svelte';
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
	let type = $state<Trigger['type']>(initial?.type ?? 'time');
	let at = $state(initial?.type === 'time' ? initial.at : '07:00');
	let event = $state<'sunrise' | 'sunset'>(initial?.type === 'sun' ? initial.event : 'sunset');
	let minutes = $state(initial?.type === 'sun' ? Math.abs(initial.offset) : 0);
	let side = $state<'before' | 'after'>(initial?.type === 'sun' && initial.offset < 0 ? 'before' : 'after');
	let days = $state<Weekday[]>(initial?.days ?? [...EVERY_DAY]);
	let problem = $state<string | null>(null);
	let saving = $state(false);

	const built = $derived<Trigger>(
		type === 'time'
			? { type: 'time', at, days }
			: { type: 'sun', event, offset: side === 'before' ? -minutes : minutes, days }
	);

	async function save(e: SubmitEvent) {
		e.preventDefault();
		saving = true;
		problem = await onsave(built);
		saving = false;
	}
</script>

<form class="part-editor" onsubmit={save}>
	<h2>{initial ? 'When' : 'Add a When'}</h2>

	<Segmented
		label="When"
		options={[
			{ value: 'time', label: 'At a time' },
			{ value: 'sun', label: 'Sunrise or sunset' }
		]}
		bind:value={type}
	/>

	{#if type === 'time'}
		<label class="field inline">
			<span>Time</span>
			<input type="time" bind:value={at} required />
		</label>
	{:else if !location}
		<LocationPicker {location} onchange={onlocation} />
	{:else}
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
	{/if}

	<div class="field">
		<span>Days</span>
		<DaysPicker bind:days />
	</div>

	{#if problem}<p class="problem">{problem}</p>{/if}

	<div class="actions">
		<Button type="submit" variant="primary" disabled={saving || (type === 'sun' && !location)}>Done</Button>
		<Button type="button" variant="ghost" onclick={onclose}>Cancel</Button>
		{#if onremove}
			<span class="remove">
				<Button type="button" variant="ghost" onclick={onremove}><Trash2 size={15} strokeWidth={2.4} /> Remove</Button>
			</span>
		{/if}
	</div>
</form>
