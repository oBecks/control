<script lang="ts">
	import { Power } from '@lucide/svelte';
	import type { PlugState, StateChange } from '$lib/types';

	interface Props {
		value: PlugState;
		onchange: (change: StateChange) => void;
	}

	let { value, onchange }: Props = $props();
</script>

<button class="power" class:on={value.on} aria-pressed={value.on} onclick={() => onchange({ on: !value.on })}>
	<Power size={40} strokeWidth={2.2} />
	<span>{value.on ? 'On' : 'Off'}</span>
</button>

<style>
	.power {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: var(--s-2);
		inline-size: 100%;
		block-size: 180px;
		border-radius: var(--r-lg);
		border: 1px solid var(--border);
		background: var(--surface-2);
		color: var(--text-2);
		font-size: var(--fs-xl);
		font-weight: var(--fw-bold);
		transition:
			background-color var(--dur) var(--ease),
			color var(--dur) var(--ease),
			transform var(--dur-fast) var(--ease);
	}
	.power:active {
		transform: scale(0.98);
	}
	.power.on {
		background: color-mix(in oklab, var(--accent) 28%, var(--surface));
		border-color: color-mix(in oklab, var(--accent) 45%, var(--border));
		color: var(--text);
	}
</style>
