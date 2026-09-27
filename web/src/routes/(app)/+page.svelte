<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { Plus, Radar } from '@lucide/svelte';
	import { MediaQuery } from 'svelte/reactivity';
	import { home } from '$lib/home.svelte';
	import { Panel } from '$lib/panel.svelte';
	import { greeting, isOn, SECTIONS } from '$lib/present';
	import TargetPanel from '$lib/TargetPanel.svelte';
	import TargetTile from '$lib/TargetTile.svelte';
	import SceneRow from '$lib/scenes/SceneRow.svelte';
	import Banner from '$lib/ui/Banner.svelte';
	import Button from '$lib/ui/Button.svelte';
	import SectionHeader from '$lib/ui/SectionHeader.svelte';
	import Sheet from '$lib/ui/Sheet.svelte';

	const desktop = new MediaQuery('min-width: 960px');
	const panel = new Panel();

	const canGroup = $derived(home.controllable.filter((d) => !d.group_problem).length >= 2);

	const groupSummary = $derived.by(() => {
		const on = home.groups.filter((g) => !home.isGroupOffline(g) && home.groupStates[g.uid]?.state.on).length;
		return on ? `${on} on` : undefined;
	});

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
			<div>
				<span class="greet">{greeting()}</span>
				<h1>Home</h1>
			</div>
			{#if canGroup}
				<Button variant="ghost" size="sm" onclick={() => panel.openEditor(null)}
					><Plus size={16} strokeWidth={2.4} /> New group</Button
				>
			{/if}
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
			<SceneRow />
			{#if home.groups.length}
				<section aria-label="Groups">
					<SectionHeader title="Groups" summary={groupSummary} />
					<div class="grid">
						{#each home.groups as g (g.uid)}
							<TargetTile
								uid={g.uid}
								selected={desktop.current && panel.highlighted(g.uid)}
								onopen={(uid) => panel.open(uid)}
							/>
						{/each}
					</div>
				</section>
			{/if}
			{#each sections as s (s.category)}
				<section>
					<SectionHeader title={s.title} summary={s.summary} />
					<div class="grid">
						{#each s.devices as d (d.uid)}
							<TargetTile
								uid={d.uid}
								selected={desktop.current && panel.highlighted(d.uid)}
								onopen={(uid) => panel.open(uid)}
							/>
						{/each}
					</div>
				</section>
			{/each}
		{/if}
	</main>

	{#if desktop.current}
		<aside class="panel" aria-label="Device controls">
			{#if panel.showing}
				<TargetPanel {panel} />
			{:else}
				<p class="hint">Select a device's <b>›</b> to see all its controls here.</p>
			{/if}
		</aside>
	{:else if panel.showing}
		<Sheet label={panel.label} onclose={() => panel.close()}>
			<TargetPanel {panel} />
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
		align-items: flex-end;
		justify-content: space-between;
		gap: var(--s-3);
	}
	header > div {
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
