<script lang="ts">
	// Which days of the week: a chip per day, in the order this browser's language starts the week.
	import type { Weekday } from '$lib/types';
	import { dayNames, weekOrder } from './parts';

	interface Props {
		days: Weekday[];
		label?: string;
	}

	let { days = $bindable(), label = 'Days' }: Props = $props();

	const names = dayNames();
	const order = weekOrder();

	function toggle(d: Weekday) {
		// At least one day stays picked.
		if (days.includes(d)) {
			if (days.length > 1) days = days.filter((x) => x !== d);
		} else {
			days = [...days, d].sort() as Weekday[];
		}
	}
</script>

<div class="days" role="group" aria-label={label}>
	{#each order as d (d)}
		<button type="button" aria-pressed={days.includes(d)} onclick={() => toggle(d)}>{names[d]}</button>
	{/each}
</div>

<style>
	.days {
		display: grid;
		grid-template-columns: repeat(7, minmax(0, 1fr));
		gap: var(--s-1);
	}
	button {
		min-block-size: 40px;
		padding: 0;
		border: 1px solid var(--border);
		border-radius: var(--r-md);
		background: var(--surface-2);
		color: var(--text-2);
		font-size: var(--fs-sm);
		font-weight: var(--fw-medium);
		transition: background-color var(--dur-fast) var(--ease);
	}
	button[aria-pressed='true'] {
		border-color: transparent;
		background: var(--accent);
		color: var(--on-accent);
	}
</style>
