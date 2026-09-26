<script lang="ts">
	// "Add item": a Heading at once, or ticked Groups and Devices as Tiles. The Dashboard places them.
	import { Check, Heading, Search, X } from '@lucide/svelte';
	import { home } from '$lib/home.svelte';
	import { groupIcon, iconFor, SECTIONS } from '$lib/present';
	import type { NewDashboardItem } from '$lib/types';
	import Button from '$lib/ui/Button.svelte';
	import Segmented from '$lib/ui/Segmented.svelte';
	import { headingItem, tileItem } from './layout';

	interface Props {
		/** Devices and Groups already on the Dashboard: they can be added again, but say so. */
		placed: Set<string>;
		/** The Dashboard's width: a new Heading spans it. */
		columns: number;
		onadd: (items: NewDashboardItem[]) => void;
		onclose: () => void;
	}

	let { placed, columns, onadd, onclose }: Props = $props();

	let query = $state('');
	let picked = $state<string[]>([]);
	/** New Tiles' look; each one's width and height can be changed afterwards. */
	let size = $state<'small' | 'wide' | 'large'>('wide');
	const CELLS = { small: [1, 2], wide: [2, 2], large: [2, 4] } as const;

	const matches = (name: string) => name.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase());

	const sections = $derived(
		[
			{
				title: 'Groups',
				rows: home.groups.map((g) => ({ uid: g.uid, name: g.name, icon: groupIcon(g, home.groupStates[g.uid]) }))
			},
			...SECTIONS.map((s) => ({
				title: s.title,
				rows: home.controllable
					.filter((d) => d.category === s.category)
					.map((d) => ({ uid: d.uid, name: d.name, icon: iconFor(d) }))
			}))
		]
			.map((s) => ({ ...s, rows: s.rows.filter((r) => matches(r.name)) }))
			.filter((s) => s.rows.length)
	);

	function toggle(uid: string) {
		picked = picked.includes(uid) ? picked.filter((u) => u !== uid) : [...picked, uid];
	}

	function add() {
		onadd(picked.map((uid) => tileItem(uid, ...CELLS[size])));
		onclose();
	}
</script>

<div class="add">
	<div class="head">
		<h2>Add items</h2>
		<button type="button" class="close" aria-label="Close" onclick={onclose}><X size={18} strokeWidth={2.4} /></button>
	</div>

	<div class="quick">
		<button
			type="button"
			onclick={() => {
				onadd([headingItem('Heading', columns)]);
				onclose();
			}}
		>
			<Heading size={18} strokeWidth={2.2} />
			<span><b>Heading</b><small>A title, as wide as you like, over anything</small></span>
		</button>
	</div>

	<label class="search">
		<Search size={16} strokeWidth={2.2} />
		<input bind:value={query} placeholder="Search devices and groups" aria-label="Search devices and groups" />
	</label>

	{#each sections as s (s.title)}
		<section>
			<h3>{s.title}</h3>
			<ul>
				{#each s.rows as r (r.uid)}
					{@const checked = picked.includes(r.uid)}
					<li>
						<label class="pick" class:checked>
							<input type="checkbox" {checked} onchange={() => toggle(r.uid)} />
							<span class="badge" aria-hidden="true"><r.icon size={16} strokeWidth={2.2} /></span>
							<span class="text">
								<span class="name">{r.name}</span>
								{#if placed.has(r.uid)}<span class="why">Already on this dashboard</span>{/if}
							</span>
							<span class="box" aria-hidden="true"
								>{#if checked}<Check size={14} strokeWidth={3} />{/if}</span
							>
						</label>
					</li>
				{/each}
			</ul>
		</section>
	{:else}
		<p class="hint">{query ? 'Nothing matches.' : 'No devices yet: add some first.'}</p>
	{/each}

	<div class="actions">
		<Segmented
			label="Tile size"
			options={[
				{ value: 'small', label: 'Small' },
				{ value: 'wide', label: 'Wide' },
				{ value: 'large', label: 'Large' }
			]}
			bind:value={size}
		/>
		<Button variant="primary" disabled={!picked.length} onclick={add}>
			Add {picked.length || ''} tile{picked.length === 1 ? '' : 's'}
		</Button>
	</div>
</div>

<style>
	.add {
		display: flex;
		flex-direction: column;
		gap: var(--s-4);
	}
	.head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--s-3);
	}
	h2 {
		margin: 0;
		font-size: var(--fs-xl);
		font-weight: var(--fw-bold);
	}
	h3 {
		margin: 0 0 var(--s-1);
		font-size: var(--fs-sm);
		font-weight: var(--fw-medium);
		color: var(--text-2);
	}
	.close {
		display: grid;
		place-items: center;
		flex-shrink: 0;
		inline-size: 32px;
		block-size: 32px;
		border: 0;
		border-radius: var(--r-pill);
		background: var(--surface-2);
		color: var(--text-2);
	}
	.quick {
		display: grid;
		gap: var(--s-2);
	}
	.quick button {
		display: flex;
		align-items: flex-start;
		gap: var(--s-2);
		padding: var(--s-3);
		border: 1px solid var(--border);
		border-radius: var(--r-md);
		background: var(--surface);
		color: var(--text);
		text-align: start;
		transition: background-color var(--dur-fast) var(--ease);
	}
	.quick button:hover {
		background: var(--surface-2);
	}
	.quick :global(svg) {
		flex-shrink: 0;
		margin-block-start: 2px;
		color: var(--text-2);
	}
	.quick span {
		display: flex;
		flex-direction: column;
		gap: 2px;
	}
	.quick small {
		color: var(--text-2);
		font-size: var(--fs-xs);
	}
	.search {
		display: flex;
		align-items: center;
		gap: var(--s-2);
		min-block-size: 44px;
		padding-inline: var(--s-3);
		border-radius: var(--r-md);
		border: 1px solid var(--border);
		background: var(--surface-2);
		color: var(--text-3);
	}
	.search:focus-within {
		border-color: var(--accent);
	}
	.search input {
		flex: 1;
		min-inline-size: 0;
		border: 0;
		background: transparent;
		font-size: var(--fs-md);
		color: var(--text);
		outline: none;
	}
	ul {
		display: flex;
		flex-direction: column;
		gap: var(--s-1);
		margin: 0;
		padding: 0;
		list-style: none;
	}
	.pick {
		position: relative;
		display: flex;
		align-items: center;
		gap: var(--s-3);
		padding: var(--s-2);
		border-radius: var(--r-md);
		cursor: pointer;
		transition: background-color var(--dur-fast) var(--ease);
	}
	.pick:hover {
		background: var(--surface-2);
	}
	/* The real checkbox stays for keyboards and screen readers; .box draws it. */
	.pick input {
		position: absolute;
		opacity: 0;
		pointer-events: none;
	}
	.pick:has(input:focus-visible) {
		outline: 2px solid var(--accent);
		outline-offset: 1px;
	}
	.badge {
		display: grid;
		place-items: center;
		flex-shrink: 0;
		inline-size: 32px;
		block-size: 32px;
		border-radius: var(--r-pill);
		background: var(--surface-2);
		color: var(--text-2);
	}
	.text {
		display: flex;
		flex-direction: column;
		flex: 1;
		min-inline-size: 0;
	}
	.name {
		overflow: hidden;
		font-weight: var(--fw-medium);
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.why {
		font-size: var(--fs-xs);
		color: var(--text-3);
	}
	.box {
		display: grid;
		place-items: center;
		flex-shrink: 0;
		inline-size: 22px;
		block-size: 22px;
		border-radius: 6px;
		border: 2px solid var(--border);
		background: var(--surface);
		color: var(--on-accent);
		transition:
			background-color var(--dur-fast) var(--ease),
			border-color var(--dur-fast) var(--ease);
	}
	.checked .box {
		border-color: var(--accent);
		background: var(--accent);
	}
	.hint {
		margin: 0;
		color: var(--text-2);
	}
	.actions {
		position: sticky;
		inset-block-end: calc(-1 * var(--s-8));
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		justify-content: space-between;
		gap: var(--s-2);
		padding-block: var(--s-3);
		border-block-start: 1px solid var(--border);
		background: var(--surface);
	}
</style>
