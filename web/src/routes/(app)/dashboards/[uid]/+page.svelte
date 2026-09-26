<script lang="ts">
	// One Dashboard: its items in the grid, and Edit mode to arrange them (ADR 0009).
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { GripVertical, Pencil, Plus, Trash2, X } from '@lucide/svelte';
	import { flip } from 'svelte/animate';
	import { MediaQuery } from 'svelte/reactivity';
	import AddItems from '$lib/dashboards/AddItems.svelte';
	import { dashboards } from '$lib/dashboards/dashboards.svelte';
	import { columnsFor, moveItem, SIZE_LABEL, SIZES, spanOf } from '$lib/dashboards/layout';
	import { reorder } from '$lib/dashboards/reorder';
	import { home } from '$lib/home.svelte';
	import { Panel } from '$lib/panel.svelte';
	import TargetPanel from '$lib/TargetPanel.svelte';
	import TargetTile from '$lib/TargetTile.svelte';
	import type { DashboardItem } from '$lib/types';
	import Button from '$lib/ui/Button.svelte';
	import Segmented from '$lib/ui/Segmented.svelte';
	import Sheet from '$lib/ui/Sheet.svelte';

	const desktop = new MediaQuery('min-width: 960px');
	const reduceMotion = new MediaQuery('prefers-reduced-motion: reduce');
	const panel = new Panel();

	$effect(() => dashboards.start());

	const uid = $derived(page.params.uid ?? '');
	const dash = $derived(dashboards.get(uid));

	let arranging = $state(false);
	/** The item picked while arranging, by id. */
	let picked = $state<string | null>(null);
	let adding = $state(false);
	/** The order while an item is being dragged; saved when it's let go. */
	let dragged = $state<DashboardItem[] | null>(null);
	let width = $state(0);

	const items = $derived(dragged ?? dash?.items ?? []);
	const columns = $derived(columnsFor(width || 375));
	const pickedItem = $derived(items.find((i) => i.id === picked));
	const placed = $derived(new Set(items.flatMap((i) => (i.kind === 'tile' ? [i.target] : []))));

	// A new, empty Dashboard opens ready to arrange.
	$effect(() => {
		if (dashboards.arrangeOnOpen && dashboards.arrangeOnOpen === uid) {
			dashboards.arrangeOnOpen = null;
			startArranging();
		}
	});

	function startArranging() {
		panel.close();
		arranging = true;
	}

	function done() {
		arranging = false;
		picked = null;
		adding = false;
	}

	function save(next: DashboardItem[]) {
		if (dash) dashboards.save(dash.uid, { items: next });
	}

	function change(id: string, patch: Partial<DashboardItem>) {
		save(items.map((i) => (i.id === id ? ({ ...i, ...patch } as DashboardItem) : i)));
	}

	function remove(id: string) {
		if (picked === id) picked = null;
		save(items.filter((i) => i.id !== id));
	}

	function add(added: DashboardItem[]) {
		// After the picked item, otherwise at the end.
		const at = picked ? items.findIndex((i) => i.id === picked) + 1 : items.length;
		save([...items.slice(0, at), ...added, ...items.slice(at)]);
		if (added.length === 1) picked = added[0].id;
	}

	function rename(name: string) {
		if (dash && name.trim() && name.trim() !== dash.name) dashboards.save(dash.uid, { name: name.trim() });
	}

	function itemName(item: DashboardItem): string {
		if (item.kind === 'heading') return 'Heading';
		if (item.kind === 'spacer') return 'Spacer';
		const target = item.target;
		return (
			home.groups.find((g) => g.uid === target)?.name ?? home.devices.find((d) => d.uid === target)?.name ?? 'Tile'
		);
	}
</script>

<svelte:head><title>{dash?.name ?? 'Dashboard'} · Control</title></svelte:head>

<div class="dash" class:with-panel={desktop.current}>
	<main>
		{#if !dash}
			{#if dashboards.loaded}
				<div class="empty">
					<h1>This dashboard is gone</h1>
					<p>Someone deleted it.</p>
					<a href={resolve('/dashboards')}>See your dashboards</a>
				</div>
			{/if}
		{:else}
			<header>
				{#if arranging}
					<input
						class="title"
						value={dash.name}
						aria-label="Dashboard name"
						maxlength="40"
						onchange={(e) => rename(e.currentTarget.value)}
					/>
					<Button variant="primary" size="sm" onclick={done}>Done</Button>
				{:else}
					<h1>{dash.name}</h1>
					<Button variant="ghost" size="sm" onclick={startArranging}>
						<Pencil size={15} strokeWidth={2.4} /> Edit
					</Button>
				{/if}
			</header>

			{#if !items.length && !arranging}
				<div class="empty">
					<p>Nothing here yet.</p>
					<Button variant="primary" onclick={startArranging}><Plus size={16} strokeWidth={2.4} /> Add items</Button>
				</div>
			{/if}

			<div
				class="grid"
				class:arranging
				style:--cols={columns}
				bind:clientWidth={width}
				{@attach reorder(() => ({
					onmove: (from, to) => (dragged = moveItem(items, from, to)),
					onend: () => {
						if (dragged) save(dragged);
						dragged = null;
					}
				}))}
			>
				{#each items as item, i (item.id)}
					<div
						class="cell {item.kind}"
						class:picked={arranging && picked === item.id}
						data-index={i}
						style:grid-column="span {spanOf(item, columns)}"
						animate:flip={{ duration: reduceMotion.current ? 0 : 200 }}
					>
						{#if item.kind === 'tile'}
							<TargetTile
								uid={item.target}
								small={item.size === '1x1'}
								inert={arranging}
								selected={desktop.current && !arranging && panel.highlighted(item.target)}
								onopen={(target) => panel.open(target)}
							/>
						{:else if item.kind === 'heading'}
							<h2>{item.text}</h2>
						{/if}

						{#if arranging}
							<button
								class="pick"
								aria-label="Select {itemName(item)}"
								aria-pressed={picked === item.id}
								onclick={() => (picked = picked === item.id ? null : item.id)}
							></button>
							<span class="handle" data-handle aria-hidden="true"><GripVertical size={16} strokeWidth={2.4} /></span>
							<button class="remove" aria-label="Remove {itemName(item)}" onclick={() => remove(item.id)}>
								<X size={14} strokeWidth={2.8} />
							</button>
						{/if}
					</div>
				{/each}
			</div>

			{#if arranging}
				<div class="bar" role="toolbar" aria-label="Arrange">
					{#if pickedItem}
						<span class="what">{itemName(pickedItem)}</span>
						{#if pickedItem.kind === 'heading'}
							<input
								value={pickedItem.text}
								aria-label="Heading text"
								maxlength="60"
								onchange={(e) => change(pickedItem.id, { text: e.currentTarget.value })}
							/>
						{/if}
						{#if SIZES[pickedItem.kind].length > 1}
							<Segmented
								label="Size"
								options={SIZES[pickedItem.kind].map((s) => ({ value: s, label: SIZE_LABEL[s] }))}
								value={pickedItem.size}
								onchange={(size) => change(pickedItem.id, { size } as Partial<DashboardItem>)}
							/>
						{/if}
						<Button variant="ghost" size="sm" onclick={() => remove(pickedItem.id)}>
							<Trash2 size={15} strokeWidth={2.4} /> Remove
						</Button>
					{:else}
						<span class="what">Drag <GripVertical size={14} strokeWidth={2.4} /> to move. Tap an item to size it.</span>
					{/if}
					<Button variant="primary" size="sm" onclick={() => (adding = true)}>
						<Plus size={16} strokeWidth={2.4} /> Add item
					</Button>
				</div>
			{/if}
		{/if}
	</main>

	{#if desktop.current}
		<aside class="panel" aria-label={adding ? 'Add items' : 'Device controls'}>
			{#if adding}
				<AddItems {placed} onadd={add} onclose={() => (adding = false)} />
			{:else if panel.showing}
				<TargetPanel {panel} />
			{:else if arranging}
				<p class="hint">Add items, drag them into place, and tap one to change its size.</p>
			{:else}
				<p class="hint">Select a tile's <b>›</b>, or hold a small one, to see all its controls here.</p>
			{/if}
		</aside>
	{:else if adding}
		<Sheet label="Add items" onclose={() => (adding = false)}>
			<AddItems {placed} onadd={add} onclose={() => (adding = false)} />
		</Sheet>
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
		align-items: center;
		justify-content: space-between;
		gap: var(--s-3);
		min-block-size: 44px;
	}
	h1,
	.title {
		margin: 0;
		font-size: var(--fs-2xl);
		font-weight: var(--fw-bold);
		line-height: 1.1;
	}
	.title {
		flex: 1;
		min-inline-size: 0;
		padding: var(--s-1) var(--s-2);
		margin-inline-start: calc(-1 * var(--s-2));
		border: 1px dashed var(--border);
		border-radius: var(--r-sm);
		background: transparent;
		color: var(--text);
		font-family: inherit;
	}
	.title:focus {
		border: 1px solid var(--accent);
		outline: none;
	}

	.grid {
		display: grid;
		grid-template-columns: repeat(var(--cols), minmax(0, 1fr));
		gap: var(--s-3);
		align-items: stretch;
	}
	.cell {
		position: relative;
		display: grid;
		min-inline-size: 0;
	}
	.cell.tile,
	.cell.spacer {
		min-block-size: var(--tile-h);
	}
	.cell.heading {
		align-items: end;
		padding-block-start: var(--s-3);
	}
	.cell h2 {
		margin: 0;
		font-size: var(--fs-lg);
		font-weight: var(--fw-bold);
		overflow-wrap: anywhere;
	}
	.cell > :global(.tile) {
		min-inline-size: 0;
	}

	/* Arranging: every item can be picked, dragged by its handle, and removed. */
	.arranging .cell {
		border-radius: var(--r-lg);
		animation: settle var(--dur) var(--ease);
	}
	.arranging .cell.spacer {
		border: 2px dashed var(--border);
	}
	.arranging .cell.heading {
		/* Room for the handle at the end; the × sits outside the corner. */
		padding-block: var(--s-2);
		padding-inline: var(--s-3) var(--s-10);
		border: 1px dashed var(--border);
		border-radius: var(--r-md);
	}
	.arranging .cell.picked {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}
	.grid:global([data-dragging]) .cell {
		transition: opacity var(--dur-fast) var(--ease);
	}
	.pick {
		position: absolute;
		inset: 0;
		z-index: 1;
		border: 0;
		border-radius: inherit;
		background: transparent;
	}
	.handle,
	.remove {
		position: absolute;
		z-index: 2;
		display: grid;
		place-items: center;
		inline-size: 30px;
		block-size: 30px;
		border-radius: var(--r-pill);
		box-shadow: var(--shadow-1);
	}
	.handle {
		inset-block-start: var(--s-2);
		inset-inline-end: var(--s-2);
		background: var(--surface);
		color: var(--text-2);
		cursor: grab;
		touch-action: none;
	}
	.handle:active {
		cursor: grabbing;
	}
	.remove {
		inset-block-start: calc(-1 * var(--s-2));
		inset-inline-start: calc(-1 * var(--s-2));
		border: 0;
		background: var(--text);
		color: var(--bg);
	}
	.cell.heading .handle {
		inset-block-start: 50%;
		translate: 0 -50%;
	}
	@keyframes settle {
		from {
			opacity: 0.6;
		}
	}

	.bar {
		position: sticky;
		inset-block-end: calc(88px + env(safe-area-inset-bottom));
		z-index: 5;
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: var(--s-2) var(--s-3);
		padding: var(--s-3) var(--s-4);
		border: 1px solid var(--border);
		border-radius: var(--r-lg);
		background: var(--surface);
		box-shadow: var(--shadow-2);
	}
	.bar .what {
		display: inline-flex;
		align-items: center;
		gap: var(--s-1);
		flex: 1 1 140px;
		color: var(--text-2);
		font-size: var(--fs-sm);
	}
	.bar input {
		flex: 1 1 160px;
		min-block-size: 36px;
		padding-inline: var(--s-3);
		border-radius: var(--r-md);
		border: 1px solid var(--border);
		background: var(--surface-2);
		font-size: var(--fs-md);
		color: var(--text);
	}
	.bar input:focus {
		border-color: var(--accent);
		outline: none;
	}
	@media (min-width: 960px) {
		.bar {
			inset-block-end: var(--s-6);
		}
	}

	.empty {
		display: flex;
		flex-direction: column;
		align-items: flex-start;
		gap: var(--s-3);
	}
	.empty h1 {
		font-size: var(--fs-xl);
	}
	.empty p {
		margin: 0;
		color: var(--text-2);
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
