<script lang="ts">
	// Where the home is, for sunrise and sunset (ADR 0006): a city from the list bundled with Control,
	// or typed coordinates. Nothing is looked up online.
	import { MapPin } from '@lucide/svelte';
	import { api } from '$lib/api';
	import { home } from '$lib/home.svelte';
	import type { HomeLocation } from '$lib/types';
	import Button from '$lib/ui/Button.svelte';
	import Segmented from '$lib/ui/Segmented.svelte';

	interface Props {
		location: HomeLocation | null;
		onchange: (location: HomeLocation) => void;
	}

	let { location, onchange }: Props = $props();

	let editing = $state(false);
	let by = $state<'city' | 'coordinates'>('city');
	let query = $state('');
	let cities = $state<{ name: string; lat: number; lon: number }[]>([]);
	let lat = $state('');
	let lon = $state('');
	let saving = $state(false);

	const open = $derived(editing || !location);

	// A newer search wins over an older one still on its way.
	let searches = 0;
	$effect(() => {
		const q = query.trim();
		const n = ++searches;
		if (!q) {
			cities = [];
			return;
		}
		api.cities(q).then(
			(found) => n === searches && (cities = found),
			() => {}
		);
	});

	async function save(where: { name?: string; lat: number; lon: number }) {
		saving = true;
		try {
			onchange(await api.setLocation(where));
			editing = false;
			query = '';
		} catch (e) {
			home.notify(e instanceof Error ? e.message : String(e));
		} finally {
			saving = false;
		}
	}

	function saveCoordinates(e: SubmitEvent) {
		e.preventDefault();
		save({ lat: Number(lat), lon: Number(lon) });
	}
</script>

<div class="location">
	{#if location && !editing}
		<div class="current">
			<MapPin size={16} strokeWidth={2.4} />
			<span class="text">
				<b>{location.name}</b>
				{#if location.sunrise && location.sunset}
					<small>Today the sun rises at {location.sunrise} and sets at {location.sunset}.</small>
				{/if}
			</span>
			<Button type="button" variant="ghost" size="sm" onclick={() => (editing = true)}>Change</Button>
		</div>
	{/if}

	{#if open}
		<p class="hint">
			Sunrise and sunset need to know roughly where the home is. Pick the nearest big city, or type coordinates.
		</p>
		<Segmented
			label="Location by"
			options={[
				{ value: 'city', label: 'A city' },
				{ value: 'coordinates', label: 'Coordinates' }
			]}
			bind:value={by}
		/>
		{#if by === 'city'}
			<input type="search" placeholder="Search cities, e.g. Jerusalem" bind:value={query} aria-label="City" />
			{#if cities.length}
				<ul>
					{#each cities as c (c.name)}
						<li><button type="button" disabled={saving} onclick={() => save(c)}>{c.name}</button></li>
					{/each}
				</ul>
			{:else if query.trim()}
				<p class="hint">
					No city by that name in Control's list, which has capitals and big cities only. Pick one nearby, or use
					coordinates.
				</p>
			{/if}
		{:else}
			<form class="coords" onsubmit={saveCoordinates}>
				<label>
					<span>Latitude</span>
					<input type="number" step="any" min="-90" max="90" bind:value={lat} placeholder="32.08" required />
				</label>
				<label>
					<span>Longitude</span>
					<input type="number" step="any" min="-180" max="180" bind:value={lon} placeholder="34.78" required />
				</label>
				<Button type="submit" variant="primary" size="sm" disabled={saving}>Use these</Button>
			</form>
			<p class="hint">A map app shows them for a place you pick (in Google Maps: long-press it).</p>
		{/if}
		{#if location}
			<Button type="button" variant="ghost" size="sm" onclick={() => (editing = false)}>Keep {location.name}</Button>
		{/if}
	{/if}
</div>

<style>
	.location {
		display: flex;
		flex-direction: column;
		align-items: stretch;
		gap: var(--s-3);
	}
	.location > :global(.btn) {
		align-self: flex-start;
	}
	.current {
		display: flex;
		align-items: center;
		gap: var(--s-3);
		color: var(--text-2);
	}
	.text {
		display: flex;
		flex-direction: column;
		flex: 1;
		min-inline-size: 0;
	}
	.text b {
		color: var(--text);
		font-weight: var(--fw-medium);
	}
	small,
	.hint {
		margin: 0;
		color: var(--text-2);
		font-size: var(--fs-sm);
	}
	input {
		min-block-size: 44px;
		padding-inline: var(--s-3);
		border-radius: var(--r-md);
		border: 1px solid var(--border);
		background: var(--surface-2);
		font-size: var(--fs-md);
	}
	input:focus {
		border-color: var(--accent);
		outline: none;
	}
	ul {
		display: flex;
		flex-direction: column;
		max-block-size: 220px;
		overflow-y: auto;
		margin: 0;
		padding: 0;
		list-style: none;
	}
	ul button {
		inline-size: 100%;
		padding: var(--s-2) var(--s-3);
		border: 0;
		border-radius: var(--r-sm);
		background: transparent;
		text-align: start;
	}
	ul button:hover {
		background: var(--surface-2);
	}
	.coords {
		display: grid;
		grid-template-columns: 1fr 1fr;
		align-items: end;
		gap: var(--s-3);
	}
	.coords label {
		display: flex;
		flex-direction: column;
		gap: var(--s-1);
		font-size: var(--fs-sm);
		font-weight: var(--fw-medium);
	}
	.coords input {
		inline-size: 100%;
	}
	.coords :global(.btn) {
		grid-column: 1 / -1;
		justify-self: start;
	}
</style>
