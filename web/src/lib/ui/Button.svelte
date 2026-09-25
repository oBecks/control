<script lang="ts">
	import type { Snippet } from 'svelte';
	import type { HTMLButtonAttributes } from 'svelte/elements';

	interface Props extends HTMLButtonAttributes {
		variant?: 'primary' | 'secondary' | 'ghost';
		size?: 'md' | 'sm';
		children: Snippet;
	}

	let { variant = 'secondary', size = 'md', children, ...rest }: Props = $props();
</script>

<button class="btn {variant} {size}" {...rest}>{@render children()}</button>

<style>
	.btn {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: var(--s-2);
		border: 1px solid transparent;
		border-radius: var(--r-pill);
		font-weight: var(--fw-medium);
		white-space: nowrap;
		transition:
			background-color var(--dur-fast) var(--ease),
			transform var(--dur-fast) var(--ease),
			opacity var(--dur-fast) var(--ease);
	}
	.btn:active:not(:disabled) {
		transform: scale(0.97);
	}
	.btn:disabled {
		opacity: 0.45;
		cursor: not-allowed;
	}
	.md {
		min-block-size: 44px;
		padding-inline: var(--s-5);
	}
	.sm {
		min-block-size: 34px;
		padding-inline: var(--s-4);
		font-size: var(--fs-sm);
	}
	.primary {
		background: var(--accent);
		color: var(--on-accent);
	}
	.primary:hover:not(:disabled) {
		background: color-mix(in oklab, var(--accent) 90%, var(--text));
	}
	.secondary {
		background: var(--surface-2);
		border-color: var(--border);
	}
	.secondary:hover:not(:disabled) {
		background: var(--surface-3);
	}
	.ghost {
		background: transparent;
		color: var(--text-2);
	}
	.ghost:hover:not(:disabled) {
		background: var(--surface-2);
		color: var(--text);
	}
</style>
