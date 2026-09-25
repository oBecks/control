<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { Radar } from '@lucide/svelte';
	import { MediaQuery } from 'svelte/reactivity';
	import DeviceControls from '$lib/DeviceControls.svelte';
	import { home } from '$lib/home.svelte';
	import { glowOf, greeting, iconFor, isOn, SECTIONS, statusFor } from '$lib/present';
	import Banner from '$lib/ui/Banner.svelte';
	import Button from '$lib/ui/Button.svelte';
	import SectionHeader from '$lib/ui/SectionHeader.svelte';
	import Sheet from '$lib/ui/Sheet.svelte';
	import Tile from '$lib/ui/Tile.svelte';

	const desktop = new MediaQuery('min-width: 960px');

	let selectedUid = $state<string | null>(null);
	const selected = $derived(home.controllable.find((d) => d.uid === selectedUid));

	const sections = $derived(
		SECTIONS.map((s) => {
			const devices = home.controllable.filter((d) => d.category === s.category);
			const on = devices.filter((d) => !home.isOffline(d) && isOn(home.states[d.uid])).length;
			return { ...s, devices, summary: on ? `${on} on` : undefined };
		}).filter((s) => s.devices.length)
	);

	// A Transmitter that nothing is set up behind yet: ask what it controls.
	const idleHub = $derived(
		home.devices.find(
			(h) => h.category === 'transmitter' && h.readiness === 'ready' && !home.devices.some((d) => d.via === h.uid)
		)
	);
</script>

<svelte:head><title>Home · Control</title></svelte:head>

<div class="home" class:with-panel={desktop.current}>
	<main>
		<header>
			<span class="greet">{greeting()}</span>
			<h1>Home</h1>
		</header>

		{#if idleHub}
			<Banner
				title="What does {idleHub.name} control?"
				detail="Tell Control about your AC, TV or fan to use them here"
				onclick={() => goto(resolve('/add'))}
			/>
		{/if}

		{#if home.newCount}
			<Banner
				title="{home.newCount} new device{home.newCount > 1 ? 's' : ''} found"
				detail="Tap to set {home.newCount > 1 ? 'them' : 'it'} up"
				onclick={() => goto(resolve('/add'))}
			/>
		{/if}

		{#if !home.loaded}
			<div class="grid" aria-busy="true">
				{#each Array(4) as _, i (i)}<div class="skeleton"></div>{/each}
			</div>
		{:else if !sections.length}
			<div class="empty">
				<h2>No devices yet</h2>
				<p>Scan your wifi to find lights, plugs and more.</p>
				<Button variant="primary" onclick={() => goto(resolve('/add'))}
					><Radar size={16} strokeWidth={2.4} /> Add devices</Button
				>
			</div>
		{:else}
			{#each sections as s (s.category)}
				<section>
					<SectionHeader title={s.title} summary={s.summary} />
					<div class="grid">
						{#each s.devices as d (d.uid)}
							{@const st = home.states[d.uid]}
							<Tile
								name={d.name}
								status={statusFor(st)}
								icon={iconFor(d, st)}
								on={isOn(st)}
								glow={glowOf(d, st)}
								pulse={home.pulses[d.uid] ?? 0}
								offline={home.isOffline(d)}
								assumed={d.kind === 'remote'}
								isNew={d.is_new}
								selected={desktop.current && d.uid === selectedUid}
								ontoggle={() => home.toggle(d.uid)}
								onopen={() => (selectedUid = d.uid)}
							/>
						{/each}
					</div>
				</section>
			{/each}
		{/if}
	</main>

	{#if desktop.current}
		<aside class="panel" aria-label="Device controls">
			{#if selected}
				<DeviceControls
					device={selected}
					value={home.states[selected.uid]}
					offline={home.isOffline(selected)}
					scanning={home.scanning}
					onchange={(c) => home.change(selected.uid, c)}
					onfindagain={() => home.findAgain()}
					onclose={() => (selectedUid = null)}
					onteach={() => {
						home.teachTarget = selected.uid;
						goto(resolve('/add'));
					}}
					onrename={(name) => home.rename(selected.uid, name)}
				/>
			{:else}
				<p class="hint">Select a device's <b>›</b> to see all its controls here.</p>
			{/if}
		</aside>
	{:else if selected}
		<Sheet label="{selected.name} controls" onclose={() => (selectedUid = null)}>
			<DeviceControls
				device={selected}
				value={home.states[selected.uid]}
				offline={home.isOffline(selected)}
				scanning={home.scanning}
				onchange={(c) => home.change(selected.uid, c)}
				onfindagain={() => home.findAgain()}
				onclose={() => (selectedUid = null)}
				onteach={() => {
					home.teachTarget = selected.uid;
					goto(resolve('/add'));
				}}
				onrename={(name) => home.rename(selected.uid, name)}
			/>
		</Sheet>
	{/if}
</div>

<style>
	main {
		display: flex;
		flex-direction: column;
		gap: var(--s-6);
		max-inline-size: 1100px;
	}
	header {
		display: flex;
		flex-direction: column;
	}
	.greet {
		font-size: var(--fs-sm);
		color: var(--text-2);
	}
	h1 {
		margin: 0;
		font-size: var(--fs-2xl);
		font-weight: var(--fw-bold);
		line-height: 1.1;
	}
	.grid {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: var(--s-3);
	}
	.skeleton {
		block-size: var(--tile-h);
		border-radius: var(--r-lg);
		background: var(--surface-2);
		animation: pulse 1.2s var(--ease) infinite alternate;
	}
	@keyframes pulse {
		to {
			opacity: 0.5;
		}
	}
	.empty {
		display: flex;
		flex-direction: column;
		align-items: flex-start;
		gap: var(--s-2);
		padding: var(--s-8) 0;
	}
	.empty h2 {
		margin: 0;
		font-size: var(--fs-xl);
	}
	.empty p {
		margin: 0 0 var(--s-3);
		color: var(--text-2);
	}

	@media (min-width: 560px) {
		.grid {
			grid-template-columns: repeat(auto-fill, minmax(var(--tile-min), 1fr));
		}
	}

	/* Desktop: grid + side panel that stays open */
	.with-panel {
		display: grid;
		grid-template-columns: minmax(0, 1fr) 360px;
		min-block-size: 100dvh;
	}
	.with-panel main {
		padding: var(--s-8);
	}
	.panel {
		position: sticky;
		inset-block-start: 0;
		block-size: 100dvh;
		overflow-y: auto;
		padding: var(--s-8) var(--s-6);
		border-inline-start: 1px solid var(--border);
		background: var(--surface);
	}
	.hint {
		margin: var(--s-10) 0 0;
		color: var(--text-3);
		text-align: center;
	}
</style>
