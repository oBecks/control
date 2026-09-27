<script lang="ts">
	// The When → Only if → Then builder: each part is a sentence card, tapped to edit in a sheet.
	// Changes are a draft until Save; the Engine checks and words each part as it's kept.
	import { beforeNavigate, goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { ChevronLeft, ChevronRight, GripVertical, Play, Plus, Trash2 } from '@lucide/svelte';
	import { flip } from 'svelte/animate';
	import { MediaQuery } from 'svelte/reactivity';
	import { api } from '$lib/api';
	import { moveItem } from '$lib/dashboards/layout';
	import { reorder } from '$lib/dashboards/reorder';
	import HotkeyEditor from '$lib/hotkeys/HotkeyEditor.svelte';
	import { hotkeys } from '$lib/hotkeys/hotkeys.svelte';
	import TargetHotkeys from '$lib/hotkeys/TargetHotkeys.svelte';
	import type { AutomationAction, Condition, HomeLocation, Labelled, Run, Trigger } from '$lib/types';
	import Button from '$lib/ui/Button.svelte';
	import ConfirmDialog from '$lib/ui/ConfirmDialog.svelte';
	import Segmented from '$lib/ui/Segmented.svelte';
	import Sheet from '$lib/ui/Sheet.svelte';
	import Switch from '$lib/ui/Switch.svelte';
	import ActionEditor from './ActionEditor.svelte';
	import { automations } from './automations.svelte';
	import ConditionEditor from './ConditionEditor.svelte';
	import { when } from './parts';
	import RunHistory from './RunHistory.svelte';
	import TriggerEditor from './TriggerEditor.svelte';

	interface Props {
		/** The Automation's uid, or "new". */
		uid: string;
	}

	let { uid }: Props = $props();

	interface Draft {
		name: string;
		match: 'all' | 'any';
		triggers: Labelled<Trigger>[];
		conditions: Labelled<Condition>[];
		actions: Labelled<AutomationAction>[];
	}
	type Part = 'triggers' | 'conditions' | 'actions';

	const reduceMotion = new MediaQuery('prefers-reduced-motion: reduce');
	const isNew = (() => uid === 'new')();
	const saved = $derived(isNew ? undefined : automations.get(uid));

	const empty: Draft = { name: '', match: 'all', triggers: [], conditions: [], actions: [] };
	let draft = $state<Draft | null>(isNew ? empty : null);
	let original = $state(isNew ? JSON.stringify(plain(empty)) : '');
	let editing = $state<{ part: Part; index: number | null } | null>(null);
	let location = $state<HomeLocation | null>(null);
	let runs = $state<Run[]>([]);
	let saving = $state(false);
	let confirmDelete = $state(false);
	let ask = $state<{ title: string; confirmLabel: string; onconfirm: () => void } | null>(null);
	/** The Actions' order while one is dragged. */
	let dragged = $state<Labelled<AutomationAction>[] | null>(null);
	/** The Hotkey editor, open on one of its Hotkeys (uid) or a new one (null). */
	let hotkeyEditor = $state<{ uid: string | null } | null>(null);
	const editingHotkey = $derived(hotkeyEditor?.uid ? hotkeys.list.find((h) => h.uid === hotkeyEditor?.uid) : undefined);
	const hotkeyCount = $derived(saved ? hotkeys.forTarget(saved.uid).length : 0);

	const changed = $derived(!!draft && JSON.stringify(plain(draft)) !== original);
	const actions = $derived(dragged ?? draft?.actions ?? []);

	$effect(() => automations.start());
	$effect(() => {
		hotkeys.load();
	});
	$effect(() => {
		api.location().then(
			(l) => (location = l),
			() => {}
		);
	});

	// The saved Automation becomes the draft once it's loaded; polling mustn't reset it after.
	$effect(() => {
		if (draft || !saved) return;
		draft = {
			name: saved.name,
			match: saved.match,
			triggers: saved.triggers,
			conditions: saved.conditions,
			actions: saved.actions
		};
		original = JSON.stringify(plain(draft));
	});

	// The history, read again whenever the latest Run changes (and while it runs, its steps do).
	$effect(() => {
		const key = JSON.stringify(saved?.last_run ?? null);
		if (!saved || !key) return;
		api.runs(saved.uid).then(
			(r) => (runs = r),
			() => {}
		);
	});

	function plain(d: Draft) {
		const strip = <T,>(parts: Labelled<T>[]): T[] => parts.map(({ label: _, ...rest }) => rest as T);
		return {
			name: d.name.trim(),
			match: d.match,
			triggers: strip(d.triggers),
			conditions: strip(d.conditions),
			actions: strip(d.actions)
		};
	}

	/** Keep a part: the Engine checks it and says it in words; answers why not, or null. */
	async function keep(part: Part, index: number | null, value: Trigger | Condition | AutomationAction) {
		if (!draft) return null;
		const next = plain(draft);
		const list: unknown[] = [...next[part]];
		if (index === null) list.push(value);
		else list[index] = value;
		try {
			const checked = await api.previewAutomation({ ...next, [part]: list, uid: isNew ? undefined : uid });
			draft = { ...draft, triggers: checked.triggers, conditions: checked.conditions, actions: checked.actions };
			editing = null;
			return null;
		} catch (e) {
			// "Action 2: it has no power to toggle" → the sheet already shows which one.
			return (e instanceof Error ? e.message : String(e)).replace(/^(Trigger|Condition|Action) \d+: /, '');
		}
	}

	function remove(part: Part, index: number) {
		if (!draft) return;
		draft = { ...draft, [part]: draft[part].filter((_, i) => i !== index) };
		editing = null;
	}

	async function save() {
		if (!draft) return;
		saving = true;
		const body = plain(draft);
		const done = await automations.save(isNew ? null : uid, body);
		saving = false;
		if (!done) return;
		original = JSON.stringify(body);
		if (isNew) await goto(resolve('/(app)/automations/[uid]', { uid: done.uid }), { replaceState: true });
	}

	function cancel() {
		if (isNew) return goto(resolve('/automations'));
		if (!saved) return;
		draft = null; // taken again from the saved one
	}

	async function run() {
		if (saved) await automations.run(saved.uid);
	}

	async function deleteIt() {
		if (!saved) return;
		original = draft ? JSON.stringify(plain(draft)) : original; // nothing to lose any more
		if (!(await automations.remove(saved.uid))) return;
		hotkeys.load(); // its Hotkeys went with it
		await goto(resolve('/automations'));
	}

	beforeNavigate((nav) => {
		if (!changed) return;
		nav.cancel();
		const to = nav.to?.url;
		if (nav.type === 'leave' || !to) return;
		ask = {
			title: 'Leave without saving your changes?',
			confirmLabel: 'Leave without saving',
			onconfirm: () => {
				original = draft ? JSON.stringify(plain(draft)) : original;
				// eslint-disable-next-line svelte/no-navigation-without-resolve -- the app's own link, already resolved
				goto(to.pathname + to.search);
			}
		};
	});

	const editingTrigger = $derived(
		editing?.part === 'triggers' && editing.index !== null ? draft?.triggers[editing.index] : undefined
	);
	const editingCondition = $derived(
		editing?.part === 'conditions' && editing.index !== null ? draft?.conditions[editing.index] : undefined
	);
	const editingAction = $derived(
		editing?.part === 'actions' && editing.index !== null ? draft?.actions[editing.index] : undefined
	);
	const SHEET_LABELS: Record<Part, string> = { triggers: 'When', conditions: 'Only if', actions: 'Then' };
</script>

{#if ask}
	<ConfirmDialog
		title={ask.title}
		detail="Your changes to this automation aren't saved yet."
		confirmLabel={ask.confirmLabel}
		cancelLabel="Keep editing"
		onconfirm={ask.onconfirm}
		oncancel={() => (ask = null)}
	/>
{/if}

{#if hotkeyEditor && saved}
	<Sheet label="Hotkey" onclose={() => (hotkeyEditor = null)}>
		{#key hotkeyEditor.uid}
			<HotkeyEditor hotkey={editingHotkey} target={saved.uid} onclose={() => (hotkeyEditor = null)} />
		{/key}
	</Sheet>
{/if}

{#if editing && draft}
	{@const at = editing.index}
	<Sheet label={SHEET_LABELS[editing.part]} onclose={() => (editing = null)}>
		{#if editing.part === 'triggers'}
			<TriggerEditor
				trigger={editingTrigger}
				{location}
				onlocation={(l) => (location = l)}
				onsave={(t) => keep('triggers', at, t)}
				onremove={at === null ? undefined : () => remove('triggers', at)}
				onclose={() => (editing = null)}
			/>
		{:else if editing.part === 'conditions'}
			<ConditionEditor
				condition={editingCondition}
				{location}
				onlocation={(l) => (location = l)}
				onsave={(c) => keep('conditions', at, c)}
				onremove={at === null ? undefined : () => remove('conditions', at)}
				onclose={() => (editing = null)}
			/>
		{:else}
			<ActionEditor
				action={editingAction}
				self={isNew ? undefined : uid}
				onsave={(a) => keep('actions', at, a)}
				onremove={at === null ? undefined : () => remove('actions', at)}
				onclose={() => (editing = null)}
			/>
		{/if}
	</Sheet>
{/if}

<svelte:head><title>{draft?.name || 'New automation'} · Control</title></svelte:head>

<main>
	<a class="back" href={resolve('/automations')}><ChevronLeft size={16} strokeWidth={2.4} /> Automations</a>

	{#if !draft}
		{#if automations.loaded}
			<div class="gone">
				<h1>This automation is gone</h1>
				<p>Someone deleted it.</p>
			</div>
		{/if}
	{:else}
		<header>
			<input
				class="title"
				bind:value={draft.name}
				placeholder="Name it, e.g. Evening lights"
				aria-label="Name"
				maxlength="60"
			/>
			{#if saved}
				<Switch checked={saved.enabled} label="On" onchange={(on) => automations.setEnabled(saved.uid, on)} />
			{/if}
		</header>

		{#if saved?.attention}
			<p class="attention">{saved.attention}. Check it, then switch it back on.</p>
		{:else if saved && !saved.enabled && saved.triggers.length}
			<p class="note">It's off: it runs only when you press Run.</p>
		{/if}
		{#if saved?.made_by === 'assistant'}<p class="note">Made by the Assistant.</p>{/if}

		<section>
			<h2>When</h2>
			{#if draft.triggers.length}
				<ul>
					{#each draft.triggers as t, i (i)}
						<li>
							<button type="button" class="card" onclick={() => (editing = { part: 'triggers', index: i })}>
								<span>{t.label}</span>
								<ChevronRight size={16} strokeWidth={2.4} />
							</button>
						</li>
					{/each}
				</ul>
				{#if saved?.enabled && saved.next_run && !changed}<p class="hint">Next: {when(saved.next_run)}</p>{/if}
			{:else}
				<p class="hint">Nothing yet, so it runs only when you press Run.</p>
			{/if}
			<Button variant="ghost" size="sm" onclick={() => (editing = { part: 'triggers', index: null })}>
				<Plus size={16} strokeWidth={2.4} /> Add a When
			</Button>
		</section>

		<section>
			<h2>Only if</h2>
			{#if draft.conditions.length > 1}
				<Segmented
					label="Only if"
					options={[
						{ value: 'all', label: 'All of these' },
						{ value: 'any', label: 'Any of these' }
					]}
					bind:value={draft.match}
				/>
			{/if}
			{#if draft.conditions.length}
				<ul>
					{#each draft.conditions as c, i (i)}
						<li>
							<button type="button" class="card" onclick={() => (editing = { part: 'conditions', index: i })}>
								<span>{c.label}</span>
								<ChevronRight size={16} strokeWidth={2.4} />
							</button>
						</li>
					{/each}
				</ul>
			{:else}
				<p class="hint">Nothing: it always goes ahead.</p>
			{/if}
			<Button variant="ghost" size="sm" onclick={() => (editing = { part: 'conditions', index: null })}>
				<Plus size={16} strokeWidth={2.4} /> Add an Only if
			</Button>
		</section>

		<section>
			<h2>Then</h2>
			{#if actions.length}
				<ol
					{@attach reorder(() => ({
						onmove: (from, to) => (dragged = moveItem(actions, from, to)),
						onend: () => {
							if (dragged && draft) draft = { ...draft, actions: dragged };
							dragged = null;
						}
					}))}
				>
					{#each actions as a, i (a)}
						<li data-index={i} animate:flip={{ duration: reduceMotion.current ? 0 : 200 }}>
							{#if actions.length > 1}
								<span class="handle" data-handle aria-hidden="true"><GripVertical size={16} strokeWidth={2.4} /></span>
							{/if}
							<button type="button" class="card" onclick={() => (editing = { part: 'actions', index: i })}>
								<span>{a.label}</span>
								<ChevronRight size={16} strokeWidth={2.4} />
							</button>
						</li>
					{/each}
				</ol>
			{:else}
				<p class="hint">Add at least one thing for it to do.</p>
			{/if}
			<Button variant="ghost" size="sm" onclick={() => (editing = { part: 'actions', index: null })}>
				<Plus size={16} strokeWidth={2.4} /> Add a Then
			</Button>
		</section>

		{#if changed || isNew}
			<div class="bar">
				<Button variant="primary" disabled={saving || !draft.name.trim() || !draft.actions.length} onclick={save}>
					{isNew ? 'Create automation' : 'Save'}
				</Button>
				<Button variant="ghost" onclick={cancel}>Cancel</Button>
			</div>
		{/if}

		{#if saved}
			<section>
				<div class="history-head">
					<h2>History</h2>
					<Button
						variant="secondary"
						size="sm"
						disabled={changed}
						title={changed ? 'Save your changes first' : 'Run it now, whatever its Only if says'}
						onclick={run}
					>
						<Play size={15} strokeWidth={2.4} /> Run now
					</Button>
				</div>
				<RunHistory {runs} />
			</section>

			<TargetHotkeys
				uid={saved.uid}
				onadd={() => (hotkeyEditor = { uid: null })}
				onopen={(h) => (hotkeyEditor = { uid: h })}
			/>

			<div class="danger">
				{#if confirmDelete}
					<p>
						Delete {saved.name} and its history{hotkeyCount
							? `, with its ${hotkeyCount === 1 ? 'Hotkey' : 'Hotkeys'}`
							: ''}?
					</p>
					<div class="row">
						<Button variant="secondary" size="sm" onclick={deleteIt}
							><Trash2 size={15} strokeWidth={2.4} /> Delete</Button
						>
						<Button variant="ghost" size="sm" onclick={() => (confirmDelete = false)}>Keep it</Button>
					</div>
				{:else}
					<Button variant="ghost" size="sm" onclick={() => (confirmDelete = true)}>
						<Trash2 size={15} strokeWidth={2.4} /> Delete automation
					</Button>
				{/if}
			</div>
		{/if}
	{/if}
</main>

<style>
	main {
		display: flex;
		flex-direction: column;
		gap: var(--s-5);
		max-inline-size: 600px;
		padding: var(--s-2) 0;
	}
	@media (min-width: 960px) {
		main {
			padding: var(--s-8);
		}
	}
	.back {
		display: inline-flex;
		align-items: center;
		gap: var(--s-1);
		align-self: flex-start;
		color: var(--text-2);
		text-decoration: none;
		font-weight: var(--fw-medium);
	}
	:global([dir='rtl']) .back > :global(svg),
	:global([dir='rtl']) .card > :global(svg) {
		transform: scaleX(-1);
	}
	header {
		display: flex;
		align-items: center;
		gap: var(--s-3);
	}
	.title {
		flex: 1;
		min-inline-size: 0;
		padding: var(--s-1) 0;
		border: 0;
		border-block-end: 2px solid transparent;
		background: transparent;
		font-size: var(--fs-2xl);
		font-weight: var(--fw-bold);
	}
	.title:focus {
		border-block-end-color: var(--accent);
		outline: none;
	}
	.title::placeholder {
		color: var(--text-3);
	}
	section {
		display: flex;
		flex-direction: column;
		align-items: stretch;
		gap: var(--s-2);
	}
	section > :global(.btn) {
		align-self: flex-start;
	}
	h2 {
		margin: 0;
		font-size: var(--fs-sm);
		font-weight: var(--fw-bold);
		letter-spacing: 0.04em;
		text-transform: uppercase;
		color: var(--text-2);
	}
	ul,
	ol {
		display: flex;
		flex-direction: column;
		gap: var(--s-2);
		margin: 0;
		padding: 0;
		list-style: none;
	}
	li {
		display: flex;
		align-items: center;
		gap: var(--s-1);
	}
	.card {
		display: flex;
		align-items: center;
		gap: var(--s-3);
		flex: 1;
		min-inline-size: 0;
		min-block-size: 52px;
		padding: var(--s-3) var(--s-4);
		border: 1px solid var(--border);
		border-radius: var(--r-md);
		background: var(--surface);
		color: var(--text-3);
		text-align: start;
		box-shadow: var(--shadow-1);
		transition: background-color var(--dur-fast) var(--ease);
	}
	.card:hover {
		background: var(--surface-2);
	}
	.card span {
		flex: 1;
		color: var(--text);
		font-size: var(--fs-md);
	}
	.handle {
		display: grid;
		place-items: center;
		inline-size: 28px;
		block-size: 44px;
		color: var(--text-3);
		cursor: grab;
		touch-action: none;
	}
	:global([data-dragging]) .handle {
		cursor: grabbing;
	}
	.hint,
	.note {
		margin: 0;
		color: var(--text-2);
		font-size: var(--fs-sm);
	}
	.attention {
		margin: 0;
		padding: var(--s-3);
		border-radius: var(--r-md);
		background: color-mix(in oklab, var(--danger) 12%, var(--surface));
		color: var(--text);
		font-size: var(--fs-sm);
	}
	.bar {
		position: sticky;
		inset-block-end: calc(80px + env(safe-area-inset-bottom));
		z-index: 5;
		display: flex;
		gap: var(--s-2);
		padding: var(--s-3);
		border-radius: var(--r-lg);
		background: color-mix(in oklab, var(--surface) 92%, transparent);
		backdrop-filter: blur(12px);
		box-shadow: var(--shadow-2);
	}
	@media (min-width: 960px) {
		.bar {
			inset-block-end: var(--s-4);
		}
	}
	.history-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--s-3);
	}
	.danger {
		display: flex;
		flex-direction: column;
		align-items: flex-start;
		gap: var(--s-3);
		padding-block-start: var(--s-4);
		border-block-start: 1px solid var(--border);
	}
	.danger p {
		margin: 0;
		color: var(--text-2);
	}
	.danger .row {
		display: flex;
		gap: var(--s-2);
	}
	.danger :global(.btn) {
		color: var(--danger);
	}
	.gone h1 {
		font-size: var(--fs-xl);
	}
	.gone p {
		color: var(--text-2);
	}
</style>
