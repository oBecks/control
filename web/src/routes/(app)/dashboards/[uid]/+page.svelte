<script lang="ts">
	// One Dashboard: its items at their cells, and Edit mode to arrange them (ADR 0010).
	// Arranging changes a draft on this screen only; Save writes it to the Dashboard, Cancel drops it.
	import { beforeNavigate, goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { Bold, ChevronLeft, GripVertical, Pencil, Plus, Redo2, Trash2, Undo2, X } from '@lucide/svelte';
	import { MediaQuery } from 'svelte/reactivity';
	import AddItems from '$lib/dashboards/AddItems.svelte';
	import ItemView from '$lib/dashboards/ItemView.svelte';
	import { dashboards } from '$lib/dashboards/dashboards.svelte';
	import { gridDrag } from '$lib/dashboards/drag';
	import {
		addBelow,
		bottomOf,
		cellsOf,
		COLUMNS,
		columnsFor,
		fits,
		itemKey,
		limits,
		place,
		readingOrder,
		recall,
		tileLook,
		withColumns,
		type Columns
	} from '$lib/dashboards/layout';
	import { home } from '$lib/home.svelte';
	import { Panel } from '$lib/panel.svelte';
	import TargetPanel from '$lib/TargetPanel.svelte';
	import TargetTile from '$lib/TargetTile.svelte';
	import type { DashboardItem, NewDashboardItem } from '$lib/types';
	import Button from '$lib/ui/Button.svelte';
	import ConfirmDialog from '$lib/ui/ConfirmDialog.svelte';
	import Segmented from '$lib/ui/Segmented.svelte';
	import Sheet from '$lib/ui/Sheet.svelte';
	import Stepper from '$lib/ui/Stepper.svelte';

	type Heading = Extract<DashboardItem, { kind: 'heading' }>;

	/** Left and right as the page reads; they swap in a right-to-left language. */
	const ALIGNS: { value: Heading['align']; label: string }[] = [
		{ value: 'start', label: 'Left' },
		{ value: 'center', label: 'Center' },
		{ value: 'end', label: 'Right' }
	];
	const TEXT_SIZES: { value: Heading['text_size']; label: string }[] = [
		{ value: 's', label: 'S' },
		{ value: 'm', label: 'M' },
		{ value: 'l', label: 'L' },
		{ value: 'xl', label: 'XL' }
	];

	/** Empty rows offered under the last item while arranging, to drop things into. */
	const ROOM_BELOW = 6;

	const desktop = new MediaQuery('min-width: 960px');
	const panel = new Panel();

	$effect(() => dashboards.start());

	const uid = $derived(page.params.uid ?? '');
	const dash = $derived(dashboards.get(uid));

	/** The Dashboard as it's being arranged; null when not arranging. */
	let draft = $state<{ name: string; columns: Columns; items: DashboardItem[] } | null>(null);
	/** The draft as it started, to tell whether anything changed. */
	let original = '';
	/** Each width's arrangement from earlier in this edit, so switching back restores it. */
	let widths: Partial<Record<Columns, DashboardItem[]>> = {};
	let saving = $state(false);
	/** Earlier and undone arrangements in this edit, for Undo and Redo. */
	let past = $state<string[]>([]);
	let future = $state<string[]>([]);
	/** Control's own "are you sure?", when leaving or cancelling would lose changes. */
	let ask = $state<{ title: string; confirmLabel: string; onconfirm: () => void } | null>(null);
	const arranging = $derived(!!draft);
	const changed = $derived(!!draft && JSON.stringify(draft) !== original);
	/** The item picked while arranging, by id. */
	let picked = $state<string | null>(null);
	let adding = $state(false);
	/** Where things are while an item is being dragged; kept in the draft when it's let go. */
	let dragged = $state<DashboardItem[] | null>(null);
	let draggingId = $state<string | null>(null);
	let width = $state(0);

	const columns = $derived(draft?.columns ?? dash?.columns ?? 8);
	const items = $derived(dragged ?? draft?.items ?? dash?.items ?? []);
	/** Too narrow for its columns: shown in reading order, and not arranged here (a draft always shows its grid). */
	const placed = $derived(!width || arranging || fits(columns, width));
	const flowColumns = $derived(columnsFor(width || 375));
	const rows = $derived(bottomOf(items, columns) + (arranging ? ROOM_BELOW : 0));
	const pickedItem = $derived(items.find((i) => i.id === picked));
	const placedKeys = $derived(new Set(items.map(itemKey)));

	// A new, empty Dashboard opens ready to arrange.
	$effect(() => {
		if (dashboards.arrangeOnOpen && dashboards.arrangeOnOpen === uid) {
			dashboards.arrangeOnOpen = null;
			startArranging();
		}
	});

	function startArranging() {
		if (!dash) return;
		panel.close();
		draft = { name: dash.name, columns: dash.columns, items: structuredClone($state.snapshot(dash.items)) };
		original = JSON.stringify(draft);
		widths = {};
		past = [];
		future = [];
	}

	function stopArranging() {
		draft = null;
		picked = null;
		adding = false;
		ask = null;
	}

	const layoutOf = () => JSON.stringify({ columns: draft?.columns, items: draft?.items });

	/** Remember the arrangement before a change, for Undo. */
	function record() {
		past = [...past.slice(-99), layoutOf()];
		future = [];
	}

	function restore(layout: string) {
		if (!draft) return;
		const { columns, items } = JSON.parse(layout);
		draft.columns = columns;
		draft.items = items;
		if (!draft.items.some((i) => i.id === picked)) picked = null;
	}

	function undo() {
		const layout = past.at(-1);
		if (!layout) return;
		future = [...future, layoutOf()];
		past = past.slice(0, -1);
		restore(layout);
	}

	function redo() {
		const layout = future.at(-1);
		if (!layout) return;
		past = [...past, layoutOf()];
		future = future.slice(0, -1);
		restore(layout);
	}

	/** Ctrl+Z undoes, Ctrl+Shift+Z or Ctrl+Y redoes; a text field keeps its own undo. */
	function keydown(e: KeyboardEvent) {
		const typing = e.target instanceof Element && e.target.closest('input, textarea');
		if (!draft || !(e.ctrlKey || e.metaKey) || typing) return;
		const key = e.key.toLowerCase();
		if (key === 'z' && !e.shiftKey) undo();
		else if ((key === 'z' && e.shiftKey) || key === 'y') redo();
		else return;
		e.preventDefault();
	}

	async function saveDraft() {
		if (!dash || !draft) return;
		if (!changed) return stopArranging();
		saving = true;
		const name = draft.name.trim() || dash.name;
		const ok = await dashboards.save(dash.uid, { name, columns: draft.columns, items: draft.items });
		saving = false;
		if (ok) stopArranging();
	}

	function cancel() {
		if (!changed) return stopArranging();
		ask = { title: 'Throw away your changes?', confirmLabel: 'Throw away', onconfirm: stopArranging };
	}

	// Leaving with unsaved changes asks first: in the app, and (the browser's own prompt) when the tab closes.
	beforeNavigate((nav) => {
		if (!changed) return;
		nav.cancel();
		const to = nav.to?.url;
		if (nav.type === 'leave' || !to) return;
		ask = {
			title: 'Leave without saving your changes?',
			confirmLabel: 'Leave without saving',
			onconfirm: () => {
				stopArranging();
				// eslint-disable-next-line svelte/no-navigation-without-resolve -- the app's own link, already resolved
				goto(to.pathname + to.search);
			}
		};
	});

	/** Change the draft's items. */
	function save(next: DashboardItem[]) {
		if (!draft) return;
		record();
		draft.items = next;
	}

	function resize(id: string, size: { w?: number; h?: number }) {
		save(place(items, id, size, columns));
	}

	/** Change a Heading's text or style. */
	function restyle(id: string, change: Partial<Pick<Heading, 'text' | 'align' | 'text_size' | 'bold'>>) {
		save(items.map((i) => (i.id === id && i.kind === 'heading' ? { ...i, ...change } : i)));
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
		if (!draft || next === draft.columns) return;
		record();
		widths[draft.columns] = draft.items;
		const before = widths[next];
		draft.items = before ? recall(before, draft.items, next) : withColumns(draft.items, next);
		draft.columns = next;
	}

	const KIND_NAMES = { tile: 'Tile', big_control: 'Big control', pad: 'Remote pad', button: 'Button' } as const;
	const CONTROL_NAMES = { brightness: 'brightness', colour: 'colour', climate: 'AC' } as const;

	/** What the arrange bar and screen readers call an item, e.g. "Living room brightness". */
	function itemName(item: DashboardItem): string {
		if (item.kind === 'heading') return `Heading ${item.text}`.trim();
		if (item.kind === 'clock') return 'Clock';
		const name = home.nameOf(item.target) ?? KIND_NAMES[item.kind];
		if (item.kind === 'big_control') return `${name} ${CONTROL_NAMES[item.control]}`;
		if (item.kind === 'pad') return `${name} remote`;
		if (item.kind === 'button') {
			const reading = home.stateOf(item.target);
			const shortcuts = reading?.control === 'streamer' ? reading.features.apps : [];
			const buttons = reading?.control === 'remote' || reading?.control === 'streamer' ? reading.features.buttons : [];
			const label = item.app
				? (shortcuts.find((a) => a.app === item.app)?.name ?? item.app)
				: (buttons.find((b) => b.name === item.button)?.label ?? item.button);
			return `${name} ${label}`;
		}
		return name;
	}

	/** Where an item sits: its own cell, or (too narrow) just its size in reading order. */
	function area(item: DashboardItem) {
		const { w, h } = cellsOf(item, placed ? columns : flowColumns);
		return placed
			? { column: `${item.x + 1} / span ${w}`, row: `${item.y + 1} / span ${h}` }
			: { column: `span ${w}`, row: `span ${h}` };
	}
</script>

<svelte:window onkeydown={keydown} />

{#if ask}
	<ConfirmDialog
		title={ask.title}
		detail="Your changes to this dashboard aren't saved yet."
		confirmLabel={ask.confirmLabel}
		cancelLabel="Keep editing"
		onconfirm={ask.onconfirm}
		oncancel={() => (ask = null)}
	/>
{/if}

<svelte:head><title>{dash?.name ?? 'Dashboard'} · Control</title></svelte:head>

<div class="dash" class:with-panel={desktop.current}>
	<main bind:clientWidth={width} style:--cols={placed ? columns : flowColumns}>
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
				{#if draft}
					<input class="title" bind:value={draft.name} aria-label="Dashboard name" maxlength="40" />
					<div class="actions">
						<button class="icon" aria-label="Undo" title="Undo (Ctrl+Z)" disabled={!past.length} onclick={undo}>
							<Undo2 size={18} strokeWidth={2.2} />
						</button>
						<button class="icon" aria-label="Redo" title="Redo (Ctrl+Y)" disabled={!future.length} onclick={redo}>
							<Redo2 size={18} strokeWidth={2.2} />
						</button>
						<Button variant="ghost" size="sm" onclick={cancel}>Cancel</Button>
						<Button variant="primary" size="sm" disabled={saving} onclick={saveDraft}>
							{changed ? 'Save' : 'Done'}
						</Button>
					</div>
				{:else}
					<a class="back" href={resolve('/dashboards')} aria-label="Dashboards" title="Dashboards">
						<ChevronLeft size={20} strokeWidth={2.4} />
					</a>
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
						dragged = place(draft?.items ?? dash.items, id, { x, y }, columns);
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
								size={tileLook(item)}
								inert={arranging}
								selected={desktop.current && !arranging && panel.highlighted(item.target)}
								onopen={(target) => panel.open(target)}
							/>
						{:else if item.kind === 'heading'}
							<h2 class="size-{item.text_size}" class:bold={item.bold} style:text-align={item.align}>
								{item.text}
							</h2>
						{:else}
							<ItemView {item} inert={arranging} onopen={(target) => panel.open(target)} />
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
								onchange={(e) => restyle(pickedItem.id, { text: e.currentTarget.value })}
							/>
						{/if}
						<div class="group">
							<Stepper
								label="Width"
								value={Math.min(pickedItem.w, columns)}
								min={limits(pickedItem).minW}
								max={columns}
								onchange={(w) => resize(pickedItem.id, { w })}
							/>
							<Stepper
								label="Height"
								value={pickedItem.h}
								min={limits(pickedItem).minH}
								max={limits(pickedItem).maxH}
								onchange={(h) => resize(pickedItem.id, { h })}
							/>
						</div>
						{#if pickedItem.kind === 'heading'}
							{@const heading = pickedItem}
							<div class="group">
								<Segmented
									label="Align"
									options={ALIGNS}
									value={heading.align}
									onchange={(align) => restyle(heading.id, { align })}
								/>
								<Segmented
									label="Text size"
									options={TEXT_SIZES}
									value={heading.text_size}
									onchange={(text_size) => restyle(heading.id, { text_size })}
								/>
								<button
									type="button"
									class="toggle"
									aria-label="Bold"
									aria-pressed={heading.bold}
									onclick={() => restyle(heading.id, { bold: !heading.bold })}
								>
									<Bold size={16} strokeWidth={heading.bold ? 3 : 2} />
								</button>
							</div>
						{/if}
						<Button variant="ghost" size="sm" onclick={() => remove(pickedItem.id)}>
							<Trash2 size={15} strokeWidth={2.4} /> Remove
						</Button>
					{:else}
						<span class="what"
							>Drag <GripVertical size={14} strokeWidth={2.4} /> to any cell. Tap an item to change its size.</span
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
				<AddItems placed={placedKeys} {columns} onadd={add} onclose={() => (adding = false)} />
			{:else if panel.showing}
				<TargetPanel {panel} />
			{:else if arranging}
				<p class="hint">Add items, drag them to any cell, and tap one to change its size.</p>
			{:else}
				<p class="hint">Select an item's <b>›</b>, or hold a small tile, to see all its controls here.</p>
			{/if}
		</aside>
	{:else if adding}
		<Sheet label="Add items" onclose={() => (adding = false)}>
			<AddItems placed={placedKeys} {columns} onadd={add} onclose={() => (adding = false)} />
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
	header .actions {
		display: flex;
		align-items: center;
		gap: var(--s-2);
	}
	header .icon {
		display: grid;
		place-items: center;
		inline-size: 36px;
		block-size: 36px;
		border: 0;
		border-radius: var(--r-pill);
		background: transparent;
		color: var(--text-2);
	}
	header .icon:hover:not(:disabled) {
		background: var(--surface-2);
	}
	header .icon:disabled {
		color: var(--text-3);
		opacity: 0.5;
	}
	.title:focus {
		border: 1px solid var(--accent);
		outline: none;
	}
	/* Only shown on a phone on its side, where the tab bar is hidden. */
	.back {
		display: none;
		place-items: center;
		flex: none;
		inline-size: 36px;
		block-size: 36px;
		margin-inline-start: calc(-1 * var(--s-2));
		border-radius: var(--r-pill);
		color: var(--text-2);
	}
	.back:hover {
		background: var(--surface-2);
	}
	:global([dir='rtl']) .back :global(svg) {
		transform: scaleX(-1);
	}
	header h1 {
		flex: 1;
		min-inline-size: 0;
	}

	/* A phone on its side: the Dashboard gets the screen, with a short header, centered. */
	@media (orientation: landscape) and (max-height: 500px) and (max-width: 959px) {
		main {
			gap: var(--s-3);
			max-inline-size: calc(var(--cols) * 180px + (var(--cols) - 1) * var(--s-3));
			margin-inline: auto;
		}
		header {
			min-block-size: 36px;
		}
		.back {
			display: grid;
		}
		h1,
		.title {
			font-size: var(--fs-lg);
		}
		.grid {
			max-inline-size: none;
		}
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
		align-items: center;
	}
	/* The text is clipped, not the cell: the × sits outside the cell's corner. */
	.cell h2 {
		min-inline-size: 0;
		max-block-size: 100%;
		overflow: hidden;
		margin: 0;
		font-size: var(--fs-lg);
		font-weight: var(--fw-regular);
		line-height: 1.2;
		overflow-wrap: anywhere;
	}
	.cell h2.bold {
		font-weight: var(--fw-bold);
	}
	.cell h2.size-s {
		font-size: var(--fs-md);
	}
	.cell h2.size-l {
		font-size: var(--fs-xl);
	}
	.cell h2.size-xl {
		font-size: var(--fs-2xl);
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
	.bar .group {
		display: flex;
		flex-wrap: wrap;
		gap: var(--s-2);
	}
	.toggle {
		display: grid;
		place-items: center;
		inline-size: 38px;
		block-size: 38px;
		border: 1px solid var(--border);
		border-radius: var(--r-pill);
		background: var(--surface-2);
		color: var(--text-2);
	}
	.toggle[aria-pressed='true'] {
		background: var(--accent);
		border-color: var(--accent);
		color: var(--on-accent);
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
	@media (orientation: landscape) and (max-height: 500px) and (max-width: 959px) {
		.bar {
			inset-block-end: calc(var(--s-3) + env(safe-area-inset-bottom));
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
