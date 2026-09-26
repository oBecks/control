<script lang="ts">
	// Hotkeys: every Hotkey, and making new ones. Only on the computer running Control (ADR 0007).
	import { Plus } from '@lucide/svelte';
	import HotkeyEditor from '$lib/hotkeys/HotkeyEditor.svelte';
	import HotkeyList from '$lib/hotkeys/HotkeyList.svelte';
	import { hotkeys } from '$lib/hotkeys/hotkeys.svelte';
	import Button from '$lib/ui/Button.svelte';

	/** The editor, open on a Hotkey (uid) or a new one (null). */
	let editor = $state<{ uid: string | null } | null>(null);
	const editing = $derived(editor?.uid ? hotkeys.list.find((h) => h.uid === editor?.uid) : undefined);

	$effect(() => {
		hotkeys.load();
	});
</script>

<svelte:head><title>Hotkeys · Control</title></svelte:head>

<main>
	<header>
		<h1>Hotkeys</h1>
		{#if hotkeys.canChange && !editor}
			<Button variant="ghost" size="sm" onclick={() => (editor = { uid: null })}>
				<Plus size={16} strokeWidth={2.4} /> Add Hotkey
			</Button>
		{/if}
	</header>

	{#if !hotkeys.loaded}
		<p class="hint">Loading…</p>
	{:else if !hotkeys.canChange}
		<p class="hint">Hotkeys are keys on the computer running Control. Set them up there.</p>
	{:else if editor}
		{#key editor.uid}
			<div class="editor"><HotkeyEditor hotkey={editing} onclose={() => (editor = null)} /></div>
		{/key}
	{:else}
		<p class="hint">
			Keys on this computer that switch a device or group, dim a light, or press a remote button, in any app.
		</p>
		{#if !hotkeys.listening}
			<p class="note">
				Hotkeys work while the Control app runs on this computer. It isn't running now, so they're off.
			</p>
		{/if}
		{#if hotkeys.list.length}
			<HotkeyList list={hotkeys.list} showTarget onopen={(uid) => (editor = { uid })} />
		{:else}
			<div class="empty">
				<p>No Hotkeys yet. Make one here, or with <b>Add Hotkey</b> in a device's or group's controls.</p>
				<Button variant="primary" onclick={() => (editor = { uid: null })}>
					<Plus size={16} strokeWidth={2.4} /> Add Hotkey
				</Button>
			</div>
		{/if}
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
	.note {
		padding: var(--s-3);
		border-radius: var(--r-md);
		background: var(--surface-2);
		color: var(--text-2);
		font-size: var(--fs-sm);
	}
	.empty {
		display: flex;
		flex-direction: column;
		align-items: flex-start;
		gap: var(--s-4);
		padding-block: var(--s-6);
	}
	.editor {
		padding: var(--s-5);
		border-radius: var(--r-lg);
		border: 1px solid var(--border);
		background: var(--surface);
	}
</style>
