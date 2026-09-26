<script lang="ts">
	// Dashboards: every Dashboard, making new ones, and which one this browser opens to (ADR 0010).
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { Check, ChevronRight, GripVertical, House, Pencil, Plus, Trash2 } from '@lucide/svelte';
	import { flip } from 'svelte/animate';
	import { MediaQuery } from 'svelte/reactivity';
	import { dashboards } from '$lib/dashboards/dashboards.svelte';
	import { COLUMNS, columnsFor, homeItems, moveItem, type Columns } from '$lib/dashboards/layout';
	import { reorder } from '$lib/dashboards/reorder';
	import { home } from '$lib/home.svelte';
	import type { Dashboard } from '$lib/types';
	import Button from '$lib/ui/Button.svelte';
	import Segmented from '$lib/ui/Segmented.svelte';

	const reduceMotion = new MediaQuery('prefers-reduced-motion: reduce');

	$effect(() => dashboards.start());

	let making = $state(false);
	let name = $state('');
	let start = $state<'empty' | 'home'>('empty');
	/** Made for a phone, a tablet or a desktop: this screen's, unless changed. */
	let columns = $state<Columns>(columnsFor(window.innerWidth));
	let busy = $state(false);
	/** The row being renamed, or asked about deleting. */
	let renaming = $state<string | null>(null);
	let deleting = $state<string | null>(null);
	/** The order while a row is being dragged. */
	let dragged = $state<Dashboard[] | null>(null);

	const list = $derived(dragged ?? dashboards.list);

	function open(uid: string) {
		goto(resolve('/(app)/dashboards/[uid]', { uid }));
	}

	async function create(e: SubmitEvent) {
		e.preventDefault();
		busy = true;
		const items = start === 'home' ? homeItems(home.groups, home.controllable, columns) : [];
		const d = await dashboards.create(name, columns, items);
		busy = false;
		if (!d) return;
		if (start === 'empty') dashboards.arrangeOnOpen = d.uid;
		making = false;
		name = '';
		open(d.uid);
	}

	async function rename(d: Dashboard, value: string) {
		renaming = null;
		if (value.trim() && value.trim() !== d.name) await dashboards.save(d.uid, { name: value.trim() });
	}

	function count(d: Dashboard) {
		const n = d.items.filter((i) => i.kind === 'tile').length;
		const made = COLUMNS.find((c) => c.value === d.columns)?.label ?? '';
		return `${made} · ${n ? `${n} tile${n === 1 ? '' : 's'}` : 'empty'}`;
	}
</script>

<svelte:head><title>Dashboards · Control</title></svelte:head>

<main>
	<header>
		<h1>Dashboards</h1>
		{#if !making}
			<Button variant="ghost" size="sm" onclick={() => (making = true)}>
				<Plus size={16} strokeWidth={2.4} /> New dashboard
			</Button>
		{/if}
	</header>

	<p class="hint">
		Screens you arrange yourself, the same on every phone and computer. Pick one for this browser to open to.
	</p>

	{#if making}
		<form class="card" onsubmit={create}>
			<label class="field">
				<span>Name</span>
				<!-- svelte-ignore a11y_autofocus -->
				<input bind:value={name} placeholder="e.g. Phone remote" maxlength="40" required autofocus />
			</label>
			<div class="field">
				<span>Made for</span>
				<Segmented label="Made for" options={COLUMNS} bind:value={columns} />
				<small>How wide its grid is. Items stay exactly where you put them; you can change this later.</small>
			</div>
			<div class="field">
				<span>Start with</span>
				<Segmented
					label="Start with"
					options={[
						{ value: 'empty', label: 'Nothing' },
						{ value: 'home', label: 'A copy of Home' }
					]}
					bind:value={start}
				/>
			</div>
			<div class="actions">
				<Button type="submit" variant="primary" disabled={busy || !name.trim()}>Create</Button>
				<Button type="button" variant="ghost" onclick={() => (making = false)}>Cancel</Button>
			</div>
		</form>
	{/if}

	{#if !dashboards.loaded}
		<p class="hint">Loading…</p>
	{:else if list.length}
		<ul
			{@attach reorder(() => ({
				onmove: (from, to) => (dragged = moveItem(list, from, to)),
				onend: () => {
					if (dragged) dashboards.order(dragged.map((d) => d.uid));
					dragged = null;
				}
			}))}
		>
			{#each list as d, i (d.uid)}
				{@const opensHere = dashboards.openTo === d.uid}
				<li data-index={i} animate:flip={{ duration: reduceMotion.current ? 0 : 200 }}>
					{#if deleting === d.uid}
						<div class="row confirm">
							<span>Delete {d.name}? Its devices stay as they are.</span>
							<Button variant="secondary" size="sm" onclick={() => dashboards.remove(d.uid)}>
								<Trash2 size={15} strokeWidth={2.4} /> Delete
							</Button>
							<Button variant="ghost" size="sm" onclick={() => (deleting = null)}>Keep it</Button>
						</div>
					{:else}
						<div class="row">
							{#if list.length > 1}
								<span class="handle" data-handle aria-hidden="true"><GripVertical size={16} strokeWidth={2.4} /></span>
							{/if}
							{#if renaming === d.uid}
								<!-- svelte-ignore a11y_autofocus -->
								<input
									class="rename"
									value={d.name}
									aria-label="Name"
									maxlength="40"
									autofocus
									onblur={(e) => rename(d, e.currentTarget.value)}
									onkeydown={(e) => {
										if (e.key === 'Enter') e.currentTarget.blur();
										if (e.key === 'Escape') renaming = null;
									}}
								/>
							{:else}
								<a class="name" href={resolve('/(app)/dashboards/[uid]', { uid: d.uid })}>
									<b>{d.name}</b>
									<small>{count(d)}{opensHere ? ' · this browser opens to it' : ''}</small>
								</a>
							{/if}
							<button
								class="icon"
								class:on={opensHere}
								aria-pressed={opensHere}
								title={opensHere ? 'This browser opens to it. Tap to open Home instead.' : 'Open this browser to it'}
								aria-label="Open this browser to {d.name}"
								onclick={() => dashboards.setOpenTo(opensHere ? null : d.uid)}
							>
								{#if opensHere}<Check size={16} strokeWidth={2.6} />{:else}<House size={16} strokeWidth={2.2} />{/if}
							</button>
							<button class="icon" aria-label="Rename {d.name}" onclick={() => (renaming = d.uid)}>
								<Pencil size={15} strokeWidth={2.4} />
							</button>
							<button class="icon" aria-label="Delete {d.name}" onclick={() => (deleting = d.uid)}>
								<Trash2 size={15} strokeWidth={2.4} />
							</button>
							<a class="icon go" href={resolve('/(app)/dashboards/[uid]', { uid: d.uid })} aria-label="Open {d.name}">
								<ChevronRight size={16} strokeWidth={2.4} />
							</a>
						</div>
					{/if}
				</li>
			{/each}
		</ul>
	{:else if !making}
		<div class="empty">
			<p>No dashboards yet. Make one for a room, or a phone that works as a remote.</p>
			<Button variant="primary" onclick={() => (making = true)}>
				<Plus size={16} strokeWidth={2.4} /> New dashboard
			</Button>
		</div>
	{/if}
</main>

<style>
	main {
		display: flex;
		flex-direction: column;
		gap: var(--s-4);
		max-inline-size: 560px;
		padding: var(--s-2) 0;
	}
	@media (min-width: 960px) {
		main {
			padding: var(--s-8);
		}
	}
	header {
		display: flex;
		align-items: flex-end;
		justify-content: space-between;
		gap: var(--s-3);
	}
	h1 {
		margin: 0;
		font-size: var(--fs-2xl);
	}
	p {
		margin: 0;
	}
	.hint {
		color: var(--text-2);
	}
	.card {
		display: flex;
		flex-direction: column;
		gap: var(--s-4);
		padding: var(--s-5);
		border-radius: var(--r-lg);
		border: 1px solid var(--border);
		background: var(--surface);
	}
	.field {
		display: flex;
		flex-direction: column;
		align-items: flex-start;
		gap: var(--s-2);
		font-weight: var(--fw-medium);
	}
	.field input,
	.rename {
		align-self: stretch;
		min-block-size: 44px;
		padding-inline: var(--s-3);
		border-radius: var(--r-md);
		border: 1px solid var(--border);
		background: var(--surface-2);
		font-size: var(--fs-md);
		color: var(--text);
	}
	.field input:focus,
	.rename:focus {
		border-color: var(--accent);
		outline: none;
	}
	.field small {
		color: var(--text-2);
		font-size: var(--fs-sm);
		font-weight: var(--fw-regular);
	}
	.actions {
		display: flex;
		gap: var(--s-2);
	}
	ul {
		display: flex;
		flex-direction: column;
		gap: var(--s-2);
		margin: 0;
		padding: 0;
		list-style: none;
	}
	.row {
		display: flex;
		align-items: center;
		gap: var(--s-1);
		min-block-size: 60px;
		padding: var(--s-2);
		border-radius: var(--r-lg);
		border: 1px solid var(--border);
		background: var(--surface);
		box-shadow: var(--shadow-1);
	}
	.row.confirm {
		flex-wrap: wrap;
		gap: var(--s-2);
		padding: var(--s-3) var(--s-4);
	}
	.row.confirm span {
		flex: 1 1 200px;
		color: var(--text-2);
	}
	.row.confirm :global(.btn.secondary) {
		color: var(--danger);
	}
	.handle {
		display: grid;
		place-items: center;
		inline-size: 28px;
		block-size: 40px;
		color: var(--text-3);
		cursor: grab;
		touch-action: none;
	}
	.name,
	.rename {
		flex: 1;
		min-inline-size: 0;
	}
	.name {
		display: flex;
		flex-direction: column;
		padding: var(--s-1) var(--s-2);
		color: var(--text);
		text-decoration: none;
	}
	.name b {
		overflow: hidden;
		font-weight: var(--fw-medium);
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.name small {
		color: var(--text-2);
		font-size: var(--fs-sm);
	}
	.icon {
		display: grid;
		flex-shrink: 0;
		place-items: center;
		inline-size: 36px;
		block-size: 36px;
		border: 0;
		border-radius: var(--r-pill);
		background: transparent;
		color: var(--text-2);
		transition: background-color var(--dur-fast) var(--ease);
	}
	.icon:hover {
		background: var(--surface-2);
	}
	.icon.on {
		background: var(--accent);
		color: var(--on-accent);
	}
	:global([dir='rtl']) .go :global(svg) {
		transform: scaleX(-1);
	}
	.empty {
		display: flex;
		flex-direction: column;
		align-items: flex-start;
		gap: var(--s-4);
		padding-block: var(--s-6);
	}
</style>
