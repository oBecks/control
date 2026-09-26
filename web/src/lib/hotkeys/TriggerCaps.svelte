<script lang="ts">
	// A Hotkey's keys as key caps: "Ctrl+Alt+L (double)" shows the caps and "twice",
	// "Ctrl+Alt+L, then 1" the first caps, "then" and the second.
	import { keyCaps, parseTrigger } from './keys';

	let { keys }: { keys: string } = $props();

	const t = $derived(parseTrigger(keys));
	const PRESS_WORDS = { double: 'twice', long: 'hold' } as const;
</script>

<span class="caps" aria-label={keys}>
	{#each keyCaps(t.keys) as k, i (i)}<kbd>{k}</kbd>{/each}
	{#if t.press === 'then'}
		<span class="word">then</span>
		{#each keyCaps(t.then) as k, i (i)}<kbd>{k}</kbd>{/each}
	{:else if t.press !== 'once'}
		<span class="word">{PRESS_WORDS[t.press]}</span>
	{/if}
</span>

<style>
	.caps {
		display: flex;
		flex-shrink: 0;
		align-items: center;
		gap: 3px;
	}
	kbd {
		min-inline-size: 26px;
		padding: 2px 6px;
		border-radius: var(--r-sm);
		border: 1px solid var(--border);
		border-block-end-width: 2px;
		background: var(--surface);
		color: var(--text);
		font-family: inherit;
		font-size: var(--fs-xs);
		font-weight: var(--fw-bold);
		text-align: center;
	}
	.word {
		padding-inline: 3px;
		color: var(--text-2);
		font-size: var(--fs-xs);
		font-weight: var(--fw-medium);
	}
</style>
