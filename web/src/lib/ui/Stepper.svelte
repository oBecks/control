<script lang="ts">
	// A number picked with − and +, e.g. a Dashboard item's width in columns.
	import { Minus, Plus } from '@lucide/svelte';

	interface Props {
		label: string;
		value: number;
		min: number;
		max: number;
		onchange: (value: number) => void;
	}

	let { label, value, min, max, onchange }: Props = $props();
</script>

<div class="stepper" role="group" aria-label={label}>
	<span class="label">{label}</span>
	<button
		type="button"
		aria-label="Less {label.toLowerCase()}"
		disabled={value <= min}
		onclick={() => onchange(value - 1)}
	>
		<Minus size={14} strokeWidth={2.6} />
	</button>
	<output class="num" aria-live="polite">{value}</output>
	<button
		type="button"
		aria-label="More {label.toLowerCase()}"
		disabled={value >= max}
		onclick={() => onchange(value + 1)}
	>
		<Plus size={14} strokeWidth={2.6} />
	</button>
</div>

<style>
	.stepper {
		display: inline-flex;
		align-items: center;
		gap: 2px;
		padding: 3px 3px 3px var(--s-3);
		border-radius: var(--r-pill);
		background: var(--surface-2);
		border: 1px solid var(--border);
	}
	.label {
		margin-inline-end: var(--s-1);
		color: var(--text-2);
		font-size: var(--fs-sm);
	}
	button {
		display: grid;
		place-items: center;
		inline-size: 30px;
		block-size: 30px;
		border: 0;
		border-radius: var(--r-pill);
		background: transparent;
		color: var(--text);
		transition: background-color var(--dur-fast) var(--ease);
	}
	button:hover:not(:disabled) {
		background: var(--surface);
	}
	button:disabled {
		color: var(--text-3);
	}
	output {
		min-inline-size: 2ch;
		font-weight: var(--fw-bold);
		text-align: center;
	}
</style>
