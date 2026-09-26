<script lang="ts">
	// A Device's or Group's Hotkeys, at the end of its controls. Only on the computer running Control.
	import { Keyboard } from '@lucide/svelte';
	import Button from '$lib/ui/Button.svelte';
	import HotkeyList from './HotkeyList.svelte';
	import { hotkeys } from './hotkeys.svelte';

	interface Props {
		/** The Device's or Group's uid. */
		uid: string;
		onadd: () => void;
		onopen: (uid: string) => void;
	}

	let { uid, onadd, onopen }: Props = $props();

	const list = $derived(hotkeys.forTarget(uid));
</script>

{#if hotkeys.canChange}
	<section>
		<h3>Hotkeys</h3>
		{#if list.length}<HotkeyList {list} {onopen} />{/if}
		<div>
			<Button variant="ghost" size="sm" onclick={onadd}><Keyboard size={16} strokeWidth={2.4} /> Add Hotkey</Button>
		</div>
	</section>
{/if}

<style>
	section {
		display: flex;
		flex-direction: column;
		gap: var(--s-2);
		margin-block-start: var(--s-6);
		padding-block-start: var(--s-4);
		border-block-start: 1px solid var(--border);
	}
	h3 {
		margin: 0;
		font-size: var(--fs-md);
		font-weight: var(--fw-bold);
	}
</style>
