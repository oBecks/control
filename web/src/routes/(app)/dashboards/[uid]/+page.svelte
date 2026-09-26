<script lang="ts">
	// One Dashboard: its items at their cells, and Edit mode to arrange them (ADR 0010).
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { GripVertical, Pencil, Plus, Trash2, X } from '@lucide/svelte';
	import { MediaQuery } from 'svelte/reactivity';
	import AddItems from '$lib/dashboards/AddItems.svelte';
	import { dashboards } from '$lib/dashboards/dashboards.svelte';
	import { gridDrag } from '$lib/dashboards/drag';
	import {
		addBelow,
		bottomOf,
		cellsOf,
		COLUMNS,
		columnsFor,
		fits,
		place,
		readingOrder,
		SIZE_LABEL,
		SIZES,
		withColumns,
		type Columns
	} from '$lib/dashboards/layout';
	import { home } from '$lib/home.svelte';
	import { Panel } from '$lib/panel.svelte';
	import TargetPanel from '$lib/TargetPanel.svelte';
	import TargetTile from '$lib/TargetTile.svelte';
	import type { DashboardItem, NewDashboardItem } from '$lib/types';
	import Button from '$lib/ui/Button.svelte';
	import Segmented from '$lib/ui/Segmented.svelte';
	import Sheet from '$lib/ui/Sheet.svelte';

	/** Empty rows offered under the last item while arranging, to drop things into. */
	const ROOM_BELOW = 6;

	const desktop = new MediaQuery('min-width: 960px');
	const panel = new Panel();

	$effect(() => dashboards.start());

	const uid = $derived(page.params.uid ?? '');
	const dash = $derived(dashboards.get(uid));

	let arranging = $state(false);
	/** The item picked while arranging, by id. */
	let picked = $state<string | null>(null);
	let adding = $state(false);
	/** Where things are while an item is being dragged; saved when it's let go. */
	let dragged = $state<DashboardItem[] | null>(null);
	let draggingId = $state<string | null>(null);
	let width = $state(0);

	const columns = $derived(dash?.columns ?? 8);
	const items = $derived(dragged ?? dash?.items ?? []);
	/** Too narrow for its columns: shown in reading order, and not arranged here. */
	const placed = $derived(!width || fits(columns, width));
	const flowColumns = $derived(columnsFor(width || 375));
	const rows = $derived(bottomOf(items, columns) + (arranging ? ROOM_BELOW : 0));
	const pickedItem = $derived(items.find((i) => i.id === picked));
	const targets = $derived(new Set(items.flatMap((i) => (i.kind === 'tile' ? [i.target] : []))));

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

	function resize(id: string, size: DashboardItem['size']) {
		save(place(items, id, { size }, columns));
	}

	function retitle(id: string, text: string) {
		save(items.map((i) => (i.id === id && i.kind === 'heading' ? { ...i, text } : i)));
	}

	function remove(id: string) {
		if (picked === id) picked = null;
		save(items.filter((i) => i.id !== id));
	}

	function add(added: NewDashboardItem[]) {
		save(addBelow(items, added, columns));
		if (added.length === 1) picked = added[0].id;
	}

	function setColumns(next: Columns) {
		if (dash && next !== dash.columns) dashboards.save(dash.uid, { columns: next, items: withColumns(items, next) });
	}

	function rename(name: string) {
		if (dash && name.trim() && name.trim() !== dash.name) dashboards.save(dash.uid, { name: name.trim() });
	}

	function itemName(item: DashboardItem): string {
		if (item.kind === 'heading') return `Heading ${item.text}`.trim();
		const target = item.target;
		return (
			home.groups.find((g) => g.uid === target)?.name ?? home.devices.find((d) => d.uid === target)?.name ?? 'Tile'
		);
	}

	/** Where an item sits: its own cell, or (too narrow) just its size in reading order. */
	function area(item: DashboardItem) {
		const { w, h } = cellsOf(item, placed ? columns : flowColumns);
		return placed
			? { column: `${item.x + 1} / span ${w}`, row: `${item.y + 1} / span ${h}` }
			: { column: `span ${w}`, row: `span ${h}` };
	}
</script>

<svelte:head><title>{dash?.name ?? 'Dashboard'} · Control</title></svelte:head>

<div class="dash" class:with-panel={desktop.current}>
	<main bind:clientWidth={width}>
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
					{#if placed}
						<Button variant="ghost" size="sm" onclick={startArranging}>
							<Pencil size={15} strokeWidth={2.4} /> Edit
						</Button>
					{/if}
				{/if}
			</header>

			{#if !placed}
				<p class="note">
					Made for a wider screen, so it shows here in reading order. Arrange it on a {COLUMNS.find(
						(c) => c.value === columns
					)?.label.toLowerCase()}.
				</p>
			{/if}

			{#if !items.length && !arranging}
				<div class="empty">
					<p>Nothing here yet.</p>
					<Button variant="primary" onclick={startArranging}><Plus size={16} strokeWidth={2.4} /> Add items</Button>
				</div>
			{/if}

			<div
				class="grid"
				class:arranging
				class:flow={!placed}
				style:--cols={placed ? columns : flowColumns}
				style:--rows={placed ? rows : undefined}
				{@attach gridDrag(() => ({
					columns,
					onmove: (id, x, y) => {
						draggingId = id;
						dragged = place(dash.items, id, { x, y }, columns);
					},
					onend: () => {
						if (dragged) save(dragged);
						dragged = null;
						draggingId = null;
					}
				}))}
			>
				{#if arranging}
					{#each { length: rows * columns }, n (n)}
						<div
							class="slot"
							aria-hidden="true"
							style:grid-column={(n % columns) + 1}
							style:grid-row={Math.floor(n / columns) + 1}
						></div>
					{/each}
				{/if}

				{#each placed ? items : readingOrder(items) as item (item.id)}
					{@const at = area(item)}
					<div
						class="cell {item.kind}"
						class:picked={arranging && picked === item.id}
						class:dragging={draggingId === item.id}
						data-id={item.id}
						data-x={item.x}
						data-y={item.y}
						style:grid-column={at.column}
						style:grid-row={at.row}
					>
						{#if item.kind === 'tile'}
							<TargetTile
								uid={item.target}
								size={item.size === '1x1' ? 'small' : item.size === '2x2' ? 'large' : 'normal'}
								inert={arranging}
								selected={desktop.current && !arranging && panel.highlighted(item.target)}
								onopen={(target) => panel.open(target)}
							/>
						{:else}
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
						<span class="what">{pickedItem.kind === 'heading' ? 'Heading' : itemName(pickedItem)}</span>
						{#if pickedItem.kind === 'heading'}
							<input
								value={pickedItem.text}
								aria-label="Heading text"
								maxlength="60"
								onchange={(e) => retitle(pickedItem.id, e.currentTarget.value)}
							/>
						{/if}
						<Segmented
							label="Size"
							options={SIZES[pickedItem.kind].map((s) => ({ value: s, label: SIZE_LABEL[s] }))}
							value={pickedItem.size}
							onchange={(size) => resize(pickedItem.id, size)}
						/>
						<Button variant="ghost" size="sm" onclick={() => remove(pickedItem.id)}>
							<Trash2 size={15} strokeWidth={2.4} /> Remove
						</Button>
					{:else}
						<span class="what"
							>Drag <GripVertical size={14} strokeWidth={2.4} /> to any cell. Tap an item to size it.</span
						>
						<Segmented label="Made for" options={COLUMNS} value={columns} onchange={setColumns} />
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
				<AddItems placed={targets} onadd={add} onclose={() => (adding = false)} />
			{:else if panel.showing}
				<TargetPanel {panel} />
			{:else if arranging}
				<p class="hint">Add items, drag them to any cell, and tap one to change its size.</p>
			{:else}
				<p class="hint">Select a tile's <b>›</b>, or hold a small one, to see all its controls here.</p>
			{/if}
		</aside>
	{:else if adding}
		<Sheet label="Add items" onclose={() => (adding = false)}>
			<AddItems placed={targets} onadd={add} onclose={() => (adding = false)} />
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
	.note {
		margin: 0;
		padding: var(--s-3);
		border-radius: var(--r-md);
		background: var(--surface-2);
		color: var(--text-2);
		font-size: var(--fs-sm);
	}

	/* A row is half a Tile tall, so a Tile (two rows and the gap between) is exactly --tile-h. */
	.grid {
		--row-h: calc((var(--tile-h) - var(--s-3)) / 2);
		display: grid;
		grid-template-columns: repeat(var(--cols), minmax(0, 1fr));
		grid-template-rows: repeat(var(--rows, 0), var(--row-h));
		grid-auto-rows: var(--row-h);
		gap: var(--s-3);
		max-inline-size: calc(var(--cols) * 180px);
	}
	.cell {
		position: relative;
		z-index: 1;
		display: grid;
		min-inline-size: 0;
	}
	.cell > :global(.tile) {
		min-inline-size: 0;
		min-block-size: 0;
	}
	.cell.heading {
		align-items: end;
		padding-block-end: var(--s-1);
	}
	.cell h2 {
		margin: 0;
		overflow: hidden;
		font-size: var(--fs-lg);
		font-weight: var(--fw-bold);
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	/* Arranging: the empty cells show, and every item can be picked, dragged by its handle, and removed. */
	.slot {
		border-radius: var(--r-sm);
		background: color-mix(in oklab, var(--text) 4%, transparent);
		pointer-events: none;
	}
	.arranging .cell.heading {
		align-items: center;
		padding-block: 0;
		padding-inline: var(--s-3) var(--s-10);
		border: 1px dashed var(--border);
		border-radius: var(--r-md);
		background: var(--bg);
	}
	.arranging .cell.picked {
		z-index: 2;
		outline: 2px solid var(--accent);
		outline-offset: 2px;
		border-radius: var(--r-lg);
	}
	.cell.dragging {
		z-index: 3;
		opacity: 0.85;
		filter: drop-shadow(0 12px 24px rgb(0 0 0 / 0.35));
	}
	.pick {
		position: absolute;
		inset: 0;
		z-index: 1;
		border: 0;
		border-radius: var(--r-lg);
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
	.grid:global([data-dragging]) .handle {
		cursor: grabbing;
	}
	.cell.heading .handle {
		inset-block-start: 50%;
		translate: 0 -50%;
	}
	.remove {
		inset-block-start: calc(-1 * var(--s-2));
		inset-inline-start: calc(-1 * var(--s-2));
		border: 0;
		background: var(--text);
		color: var(--bg);
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
