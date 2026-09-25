<script lang="ts">
	import type { Component } from 'svelte';

	interface Props {
		label: string;
		icon: Component;
		active?: boolean;
		dashed?: boolean;
		onclick?: () => void;
	}

	let { label, icon: Icon, active = false, dashed = false, onclick }: Props = $props();
</script>

<button class="chip" class:active class:dashed {onclick}>
	<Icon size={16} strokeWidth={2.3} />
	<span>{label}</span>
</button>

<style>
	.chip {
		display: inline-flex;
		align-items: center;
		gap: var(--s-2);
		flex-shrink: 0;
		min-block-size: 40px;
		padding-inline: var(--s-4);
		border-radius: var(--r-pill);
		border: 1px solid var(--border);
		background: var(--surface);
		box-shadow: var(--shadow-1);
		font-weight: var(--fw-medium);
		font-size: var(--fs-sm);
		transition:
			background-color var(--dur) var(--ease),
			transform var(--dur-fast) var(--ease);
	}
	.chip:active {
		transform: scale(0.96);
	}
	.chip.active {
		background: var(--accent);
		border-color: transparent;
		color: var(--on-accent);
	}
	.chip.dashed {
		border-style: dashed;
		background: transparent;
		box-shadow: none;
		color: var(--text-2);
	}
</style>
