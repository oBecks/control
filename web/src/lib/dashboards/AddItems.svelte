<script lang="ts">
	// "Add item": a Heading or Clock at once, or ticked Tiles, Big Controls, Remote Pads, Single Buttons
	// or Run Buttons. The Dashboard places them.
	import { ArrowLeft, Check, Clock, Heading, Search, X } from '@lucide/svelte';
	import AirVent from '@lucide/svelte/icons/air-vent';
	import Gamepad2 from '@lucide/svelte/icons/gamepad-2';
	import Palette from '@lucide/svelte/icons/palette';
	import Play from '@lucide/svelte/icons/play';
	import Workflow from '@lucide/svelte/icons/workflow';
	import SunDim from '@lucide/svelte/icons/sun-dim';
	import type { Component } from 'svelte';
	import { automations } from '$lib/automations/automations.svelte';
	import { home } from '$lib/home.svelte';
	import { groupIcon, iconFor, SECTIONS } from '$lib/present';
	import type { BigControl, NewDashboardItem } from '$lib/types';
	import Button from '$lib/ui/Button.svelte';
	import Segmented from '$lib/ui/Segmented.svelte';
	import { buttonIcon } from './items/buttons';
	import { buttonItem, clockItem, controlItem, headingItem, padItem, runItem, tileItem } from './layout';

	interface Props {
		/** What's on the Dashboard already (see itemKey): it can be added again, but says so. */
		placed: Set<string>;
		/** The Dashboard's width: a new Heading spans it. */
		columns: number;
		onadd: (items: NewDashboardItem[]) => void;
		onclose: () => void;
	}

	let { placed, columns, onadd, onclose }: Props = $props();

	/** One thing to tick. `key` is its itemKey, whatever size it's added at. */
	type Row = { key: string; name: string; icon: Component; make: () => NewDashboardItem };
	type Kind = 'tiles' | 'controls' | 'remotes' | 'buttons';

	const KINDS: { value: Kind; label: string }[] = [
		{ value: 'tiles', label: 'Tiles' },
		{ value: 'controls', label: 'Big controls' },
		{ value: 'remotes', label: 'Remote pads' },
		{ value: 'buttons', label: 'Buttons' }
	];
	const SIZES: Record<Kind, { value: string; label: string }[]> = {
		tiles: [
			{ value: 'small', label: 'Small' },
			{ value: 'wide', label: 'Wide' },
			{ value: 'large', label: 'Large' }
		],
		controls: [],
		remotes: [
			{ value: 'compact', label: 'Compact' },
			{ value: 'full', label: 'Full' }
		],
		buttons: [
			{ value: 'small', label: 'Small' },
			{ value: 'wide', label: 'Wide' }
		]
	};
	const TILE_CELLS: Record<string, [number, number]> = { small: [1, 2], wide: [2, 2], large: [2, 4] };
	const CONTROLS: { control: BigControl; title: string; icon: Component }[] = [
		{ control: 'brightness', title: 'Brightness', icon: SunDim },
		{ control: 'colour', title: 'Colour', icon: Palette },
		{ control: 'climate', title: 'AC', icon: AirVent }
	];
	const NOUNS: Record<Kind, [string, string]> = {
		tiles: ['tile', 'tiles'],
		controls: ['big control', 'big controls'],
		remotes: ['remote pad', 'remote pads'],
		buttons: ['button', 'buttons']
	};
	const EMPTY: Record<Kind, string> = {
		tiles: 'No devices yet: add some first.',
		controls: 'No lights or ACs yet.',
		remotes: 'No TVs, fans or streamers with buttons yet.',
		buttons: 'No TVs, fans or streamers with buttons, and no automations, yet.'
	};
	/** Buttons: the Automations' Run Buttons, in place of a Device's buttons. */
	const AUTOMATIONS = 'automations';

	let kind = $state<Kind>('tiles');
	let query = $state('');
	let picked = $state<string[]>([]);
	/** Each kind's size for new items; each one's width and height can be changed afterwards. */
	let sizes = $state<Record<Kind, string>>({ tiles: 'wide', controls: '', remotes: 'compact', buttons: 'small' });
	/** Buttons: the Device whose buttons are listed, or AUTOMATIONS. */
	let buttonsOf = $state<string | null>(null);

	const matches = (name: string) => name.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase());

	const groupRows = $derived(
		home.groups.map((g) => ({ uid: g.uid, name: g.name, icon: groupIcon(g, home.groupStates[g.uid]) }))
	);
	const deviceRows = $derived(
		home.controllable.map((d) => ({
			uid: d.uid,
			name: d.name,
			category: d.category,
			icon: iconFor(d, home.states[d.uid])
		}))
	);
	/** TVs, fans and Streamers with at least one button. */
	const remotes = $derived(
		deviceRows.filter((d) => {
			const r = home.states[d.uid];
			return (r?.control === 'remote' || r?.control === 'streamer') && r.features.buttons.length > 0;
		})
	);

	function suits(uid: string, control: BigControl): boolean {
		const r = home.stateOf(uid);
		if (control === 'climate') return r?.control === 'climate';
		return r?.control === 'light' && (control === 'brightness' || r.features.color);
	}

	const sections = $derived.by((): { title: string; rows: Row[] }[] => {
		if (kind === 'tiles') {
			const [w, h] = TILE_CELLS[sizes.tiles];
			const tile = (t: { uid: string; name: string; icon: Component }): Row => ({
				key: `tile:${t.uid}`,
				name: t.name,
				icon: t.icon,
				make: () => tileItem(t.uid, w, h)
			});
			return [
				{ title: 'Groups', rows: groupRows.map(tile) },
				...SECTIONS.map((s) => ({
					title: s.title,
					rows: deviceRows.filter((d) => d.category === s.category).map(tile)
				}))
			];
		}
		if (kind === 'controls') {
			return CONTROLS.map((c) => ({
				title: c.title,
				rows: [...groupRows, ...deviceRows]
					.filter((t) => suits(t.uid, c.control))
					.map((t) => ({
						key: `big_control:${t.uid}:${c.control}`,
						name: t.name,
						icon: c.icon,
						make: () => controlItem(t.uid, c.control)
					}))
			}));
		}
		if (kind === 'remotes') {
			const size = sizes.remotes === 'full' ? 'full' : 'compact';
			return [
				{
					title: 'TVs, fans and streamers',
					rows: remotes.map((d) => ({
						key: `pad:${d.uid}`,
						name: d.name,
						icon: d.icon,
						make: () => padItem(d.uid, size)
					}))
				}
			];
		}
		const w = sizes.buttons === 'wide' ? 2 : 1;
		if (buttonsOf === AUTOMATIONS) {
			return [
				{
					title: 'Run an automation',
					rows: automations.list.map((a) => ({
						key: `run:${a.uid}`,
						name: a.name,
						icon: Play,
						make: () => runItem(a.uid, w)
					}))
				}
			];
		}
		const device = remotes.find((d) => d.uid === buttonsOf);
		const r = device && home.states[device.uid];
		if (!device || !(r?.control === 'remote' || r?.control === 'streamer')) return [];
		return [
			{
				title: 'Buttons',
				rows: r.features.buttons.map((b) => ({
					key: `button:${device.uid}:${b.name}`,
					name: b.label,
					icon: buttonIcon(b.name) ?? Gamepad2,
					make: () => buttonItem(device.uid, { button: b.name }, w)
				}))
			},
			{
				title: 'Apps',
				rows: (r.control === 'streamer' ? r.features.apps : []).map((a) => ({
					key: `button:${device.uid}:app:${a.app}`,
					name: a.name,
					icon: device.icon,
					make: () => buttonItem(device.uid, { app: a.app }, w)
				}))
			}
		];
	});

	const shown = $derived(
		sections.map((s) => ({ ...s, rows: s.rows.filter((r) => matches(r.name)) })).filter((s) => s.rows.length)
	);
	const rows = $derived(new Map(sections.flatMap((s) => s.rows.map((r) => [r.key, r] as const))));
	const noun = $derived(NOUNS[kind][picked.length === 1 ? 0 : 1]);

	function toggle(key: string) {
		picked = picked.includes(key) ? picked.filter((k) => k !== key) : [...picked, key];
	}

	function switchKind(next: Kind) {
		kind = next;
		picked = [];
		buttonsOf = null;
	}

	function add() {
		onadd(picked.flatMap((key) => rows.get(key)?.make() ?? []));
		onclose();
	}

	function addNow(item: NewDashboardItem) {
		onadd([item]);
		onclose();
	}
</script>

<div class="add">
	<div class="head">
		<h2>Add items</h2>
		<button type="button" class="close" aria-label="Close" onclick={onclose}><X size={18} strokeWidth={2.4} /></button>
	</div>

	<div class="quick">
		<button type="button" onclick={() => addNow(headingItem('Heading', columns))}>
			<Heading size={18} strokeWidth={2.2} />
			<span><b>Heading</b><small>A title, as wide as you like, over anything</small></span>
		</button>
		<button type="button" onclick={() => addNow(clockItem())}>
			<Clock size={18} strokeWidth={2.2} />
			<span><b>Clock</b><small>The time; make it wider for the date</small></span>
		</button>
	</div>

	<Segmented label="Add" options={KINDS} value={kind} onchange={switchKind} />

	{#if kind === 'buttons' && !buttonsOf}
		<p class="lead">
			Pick a remote or streamer, then the buttons to put on the dashboard on their own. Or automations, for buttons that
			run them.
		</p>
		{#if remotes.length || automations.list.length}
			<ul>
				{#each remotes as d (d.uid)}
					<li>
						<button type="button" class="pick" onclick={() => (buttonsOf = d.uid)}>
							<span class="badge" aria-hidden="true"><d.icon size={16} strokeWidth={2.2} /></span>
							<span class="text"><span class="name">{d.name}</span></span>
						</button>
					</li>
				{/each}
				{#if automations.list.length}
					<li>
						<button type="button" class="pick" onclick={() => (buttonsOf = AUTOMATIONS)}>
							<span class="badge" aria-hidden="true"><Workflow size={16} strokeWidth={2.2} /></span>
							<span class="text"><span class="name">Automations</span></span>
						</button>
					</li>
				{/if}
			</ul>
		{:else}
			<p class="hint">{EMPTY.buttons}</p>
		{/if}
	{:else}
		{#if kind === 'buttons'}
			<button
				type="button"
				class="back"
				onclick={() => {
					buttonsOf = null;
					picked = [];
				}}
			>
				<ArrowLeft size={16} strokeWidth={2.4} />
				{buttonsOf === AUTOMATIONS ? 'Automations' : home.nameOf(buttonsOf ?? '')}
			</button>
		{/if}

		<label class="search">
			<Search size={16} strokeWidth={2.2} />
			<input bind:value={query} placeholder="Search" aria-label="Search" />
		</label>

		{#each shown as s (s.title)}
			<section>
				<h3>{s.title}</h3>
				<ul>
					{#each s.rows as r (r.key)}
						{@const checked = picked.includes(r.key)}
						<li>
							<label class="pick" class:checked>
								<input type="checkbox" {checked} onchange={() => toggle(r.key)} />
								<span class="badge" aria-hidden="true"><r.icon size={16} strokeWidth={2.2} /></span>
								<span class="text">
									<span class="name">{r.name}</span>
									{#if placed.has(r.key)}<span class="why">Already on this dashboard</span>{/if}
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
			<p class="hint">{query ? 'Nothing matches.' : EMPTY[kind]}</p>
		{/each}
	{/if}

	<div class="actions">
		{#if SIZES[kind].length}
			<Segmented label="Size" options={SIZES[kind]} bind:value={sizes[kind]} />
		{/if}
		<Button variant="primary" disabled={!picked.length} onclick={add}>
			Add {picked.length || ''}
			{noun}
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
		grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
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
	.lead {
		margin: 0;
		color: var(--text-2);
		font-size: var(--fs-sm);
	}
	.back {
		display: inline-flex;
		align-items: center;
		gap: var(--s-2);
		align-self: flex-start;
		padding: var(--s-1) var(--s-3) var(--s-1) var(--s-2);
		border: 0;
		border-radius: var(--r-pill);
		background: var(--surface-2);
		color: var(--text);
		font-weight: var(--fw-medium);
	}
	:global([dir='rtl']) .back :global(svg) {
		transform: scaleX(-1);
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
	button.pick {
		inline-size: 100%;
		border: 0;
		background: transparent;
		color: var(--text);
		text-align: start;
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
