<script lang="ts">
	// One Scene's page ("new" makes one): its name, icon, and how each Device in it should be.
	import { beforeNavigate, goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import ChevronLeft from '@lucide/svelte/icons/chevron-left';
	import Plus from '@lucide/svelte/icons/plus';
	import { api } from '$lib/api';
	import HotkeyEditor from '$lib/hotkeys/HotkeyEditor.svelte';
	import { hotkeys } from '$lib/hotkeys/hotkeys.svelte';
	import TargetHotkeys from '$lib/hotkeys/TargetHotkeys.svelte';
	import { home } from '$lib/home.svelte';
	import { SECTIONS } from '$lib/present';
	import type { ScenePart } from '$lib/types';
	import Button from '$lib/ui/Button.svelte';
	import ConfirmDialog from '$lib/ui/ConfirmDialog.svelte';
	import Sheet from '$lib/ui/Sheet.svelte';
	import { SCENE_ICONS } from './icons';
	import PartEditor from './PartEditor.svelte';

	let { uid }: { uid: string } = $props();

	const isNew = $derived(uid === 'new');
	const saved = $derived(isNew ? undefined : home.scenes.find((s) => s.uid === uid));

	interface Draft {
		name: string;
		icon: string;
		parts: ScenePart[];
	}
	const plain = (d: Draft) => ({ name: d.name.trim(), icon: d.icon, parts: d.parts });

	let draft = $state<Draft | null>(null);
	let adding = $state(false);
	let original = $state('');
	// Taken from the saved Scene once it's loaded (and again after Cancel).
	$effect.pre(() => {
		if (draft) return;
		if (isNew) {
			draft = { name: '', icon: 'sparkles', parts: [] };
			adding = true; // a new Scene starts by picking what's in it
		} else if (saved)
			draft = {
				name: saved.name,
				icon: saved.icon,
				parts: saved.parts.map((p) => ({ target: p.target, state: p.state }))
			};
		if (draft) original = JSON.stringify(plain(draft));
	});
	const changed = $derived(!!draft && JSON.stringify(plain(draft)) !== original);

	let saving = $state(false);
	/** The Hotkey editor, open on one of its Hotkeys (uid) or a new one (null). */
	let hotkeyEditor = $state<{ uid: string | null } | null>(null);
	const editingHotkey = $derived(hotkeyEditor?.uid ? hotkeys.list.find((h) => h.uid === hotkeyEditor?.uid) : undefined);
	const hotkeyCount = $derived(saved ? hotkeys.forTarget(saved.uid).length : 0);

	$effect(() => {
		hotkeys.load();
	});
	let ask = $state<{ title: string; detail: string; confirmLabel: string; onconfirm: () => void } | null>(null);

	async function save() {
		if (!draft) return;
		saving = true;
		const result = await home.saveScene(isNew ? null : uid, plain(draft));
		saving = false;
		if (!result) return;
		original = JSON.stringify(plain(draft));
		if (isNew) await goto(resolve('/(app)/scenes/[uid]', { uid: result.uid }), { replaceState: true });
		else draft = null; // taken again from the saved one
	}

	function cancel() {
		if (isNew) return goto(resolve('/scenes'));
		draft = null;
	}

	function confirmDelete() {
		if (!saved) return;
		ask = {
			title: `Delete ${saved.name}?`,
			detail:
				'Its devices stay as they are; only the scene goes, with its buttons on dashboards' +
				(hotkeyCount ? ` and its ${hotkeyCount === 1 ? 'Hotkey' : 'Hotkeys'}` : '') +
				'.',
			confirmLabel: 'Delete scene',
			onconfirm: async () => {
				ask = null;
				const kept = original;
				original = draft ? JSON.stringify(plain(draft)) : original; // nothing to lose any more
				if (!(await home.deleteScene(uid))) {
					original = kept; // still there, and so are the changes to it
					return;
				}
				hotkeys.load(); // its Hotkeys went with it
				await goto(resolve('/scenes'));
			}
		};
	}

	beforeNavigate((nav) => {
		if (!changed) return;
		nav.cancel();
		const to = nav.to?.url;
		if (nav.type === 'leave' || !to) return;
		ask = {
			title: 'Leave without saving your changes?',
			detail: "Your changes to this scene aren't saved yet.",
			confirmLabel: 'Leave without saving',
			onconfirm: () => {
				original = draft ? JSON.stringify(plain(draft)) : original;
				// eslint-disable-next-line svelte/no-navigation-without-resolve -- the app's own link, already resolved
				goto(to.pathname + to.search);
			}
		};
	});

	// --- Adding Devices and Groups ------------------------------------------------------

	let picked = $state<string[]>([]);
	let capturing = $state(false);
	const inScene = $derived(new Set(draft?.parts.map((p) => p.target) ?? []));
	// A Device with only a Power Toggle (or no power) can't be in a Scene, as in a Group.
	const choices = $derived([
		{
			title: 'Groups',
			items: home.groups.filter((g) => !inScene.has(g.uid)).map((g) => ({ uid: g.uid, name: g.name }))
		},
		...SECTIONS.map((s) => ({
			title: s.title,
			items: home.controllable
				.filter((d) => d.category === s.category && !d.group_problem && !inScene.has(d.uid))
				.map((d) => ({ uid: d.uid, name: d.name }))
		}))
	]);

	async function addPicked() {
		if (!draft || !picked.length) return;
		capturing = true;
		try {
			// Each starts as it is now; one that can't be read starts as just On.
			const got = await api.captureScene(picked);
			const parts = picked.map((t) => got.parts.find((p) => p.target === t) ?? { target: t, state: { on: true } });
			draft.parts = [...draft.parts, ...parts];
			const failed = Object.values(got.failed);
			if (failed.length === 1) home.notify(`${failed[0]}. It starts as just On.`);
			else if (failed.length) home.notify(`${failed.length} of them couldn't be read, so they start as just On.`);
		} catch (e) {
			home.notify(e instanceof Error ? e.message : String(e));
			return;
		} finally {
			capturing = false;
		}
		picked = [];
		adding = false;
	}

	function toggle(uid: string, checked: boolean) {
		picked = checked ? [...picked, uid] : picked.filter((p) => p !== uid);
	}
</script>

{#if ask}
	<ConfirmDialog
		title={ask.title}
		detail={ask.detail}
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

{#if adding && draft}
	<Sheet label="Add to the scene" onclose={() => ((adding = false), (picked = []))}>
		<div class="add">
			<p class="hint">Each one starts as it is right now. Change anything after.</p>
			{#each choices.filter((c) => c.items.length) as c (c.title)}
				<fieldset>
					<legend>{c.title}</legend>
					{#each c.items as item (item.uid)}
						<label class="pick">
							<input
								type="checkbox"
								checked={picked.includes(item.uid)}
								onchange={(e) => toggle(item.uid, e.currentTarget.checked)}
							/>
							{item.name}
						</label>
					{/each}
				</fieldset>
			{:else}
				<p class="hint">Everything that can be in a scene is in it already.</p>
			{/each}
			<Button variant="primary" disabled={!picked.length || capturing} onclick={addPicked}>
				{capturing ? 'Reading them…' : picked.length ? `Add ${picked.length}` : 'Add'}
			</Button>
		</div>
	</Sheet>
{/if}

<svelte:head><title>{draft?.name || 'New scene'} · Control</title></svelte:head>

<main>
	<a class="back" href={resolve('/scenes')}><ChevronLeft size={16} strokeWidth={2.4} /> Scenes</a>

	{#if !draft}
		{#if home.loaded}
			<div class="gone">
				<h1>This scene is gone</h1>
				<p>Someone deleted it.</p>
			</div>
		{/if}
	{:else}
		<header>
			<input
				class="title"
				bind:value={draft.name}
				placeholder="Name it, e.g. Movie night"
				aria-label="Name"
				maxlength="40"
			/>
		</header>

		{#if saved?.attention}<p class="attention">{saved.attention}. Add devices to it, or delete it.</p>{/if}
		{#if saved?.made_by === 'assistant'}<p class="note">Made by the Assistant.</p>{/if}

		<div class="icons" role="radiogroup" aria-label="Icon">
			{#each Object.entries(SCENE_ICONS) as [name, Icon] (name)}
				<button
					role="radio"
					aria-checked={draft.icon === name}
					aria-label={name}
					onclick={() => draft && (draft.icon = name)}
				>
					<Icon size={18} strokeWidth={2.2} />
				</button>
			{/each}
		</div>

		<section>
			<h2>Devices</h2>
			{#if draft.parts.length}
				<p class="hint">Each one is set only as ticked here; the rest of it stays as it is.</p>
				{#each draft.parts as part, i (part.target)}
					<PartEditor
						target={part.target}
						state={part.state}
						onchange={(state) => draft && (draft.parts[i] = { target: part.target, state })}
						onremove={() => draft && (draft.parts = draft.parts.filter((_, j) => j !== i))}
					/>
				{/each}
			{:else}
				<p class="hint">Nothing yet. Set things up the way you like them, then add them here.</p>
			{/if}
			<Button variant="ghost" size="sm" onclick={() => (adding = true)}>
				<Plus size={16} strokeWidth={2.4} /> Add devices
			</Button>
		</section>

		{#if changed || isNew}
			<div class="bar">
				<Button variant="primary" disabled={saving || !draft.name.trim() || !draft.parts.length} onclick={save}>
					{isNew ? 'Create scene' : 'Save'}
				</Button>
				<Button variant="ghost" onclick={cancel}>Cancel</Button>
			</div>
		{/if}

		{#if saved}
			<section>
				<Button
					variant="secondary"
					disabled={changed || !saved.parts.length || !!home.settingScene}
					title={changed ? 'Save your changes first' : undefined}
					onclick={() => home.setScene(saved.uid)}
				>
					{home.isSceneActive(saved) ? 'Set it again' : 'Set it now'}
				</Button>
			</section>

			<TargetHotkeys
				uid={saved.uid}
				onadd={() => (hotkeyEditor = { uid: null })}
				onopen={(h) => (hotkeyEditor = { uid: h })}
			/>

			<div class="danger">
				<Button variant="ghost" onclick={confirmDelete}>Delete scene</Button>
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
	:global([dir='rtl']) .back > :global(svg) {
		transform: scaleX(-1);
	}
	.title {
		inline-size: 100%;
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
	.icons {
		display: flex;
		flex-wrap: wrap;
		gap: var(--s-2);
	}
	.icons button {
		display: grid;
		place-items: center;
		inline-size: 40px;
		block-size: 40px;
		border: 1px solid var(--border);
		border-radius: var(--r-pill);
		background: var(--surface);
		color: var(--text-2);
		transition: background-color var(--dur-fast) var(--ease);
	}
	.icons button[aria-checked='true'] {
		border-color: transparent;
		background: var(--accent);
		color: var(--on-accent);
	}
	section {
		display: flex;
		flex-direction: column;
		align-items: stretch;
		gap: var(--s-3);
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
	.danger {
		padding-block-start: var(--s-4);
		border-block-start: 1px solid var(--border);
	}
	.danger :global(.btn) {
		color: var(--danger);
	}
	.add {
		display: flex;
		flex-direction: column;
		gap: var(--s-4);
	}
	fieldset {
		display: flex;
		flex-direction: column;
		gap: var(--s-1);
		margin: 0;
		padding: 0;
		border: 0;
	}
	legend {
		margin-block-end: var(--s-1);
		color: var(--text-2);
		font-size: var(--fs-xs);
		font-weight: var(--fw-bold);
		letter-spacing: 0.04em;
		text-transform: uppercase;
	}
	.pick {
		display: flex;
		align-items: center;
		gap: var(--s-3);
		min-block-size: 44px;
	}
	.pick input {
		inline-size: 20px;
		block-size: 20px;
		accent-color: var(--accent);
	}
	.gone h1 {
		font-size: var(--fs-xl);
	}
	.gone p {
		color: var(--text-2);
	}
</style>
