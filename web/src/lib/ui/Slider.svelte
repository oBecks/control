<script lang="ts">
	interface Props {
		label: string;
		min: number;
		max: number;
		step?: number;
		value: number;
		/** CSS background for the track, e.g. a kelvin gradient. Defaults to a filled accent track. */
		track?: string;
		format?: (v: number) => string;
		/** Fires on release, so devices aren't flooded while dragging. */
		onchange?: (value: number) => void;
	}

	let { label, min, max, step = 1, value = $bindable(), track, format = String, onchange }: Props = $props();

	const pct = $derived(((value - min) / (max - min)) * 100);
</script>

<label class="slider">
	<span class="head">
		<span class="label">{label}</span>
		<span class="value num">{format(value)}</span>
	</span>
	<input
		type="range"
		{min}
		{max}
		{step}
		bind:value
		onchange={() => onchange?.(value)}
		style:--pct="{pct}%"
		style:--track={track ?? null}
		class:custom={!!track}
	/>
</label>

<style>
	.slider {
		display: flex;
		flex-direction: column;
		gap: var(--s-2);
	}
	.head {
		display: flex;
		justify-content: space-between;
		font-size: var(--fs-sm);
	}
	.label {
		color: var(--text-2);
		font-weight: var(--fw-medium);
	}
	.value {
		font-weight: var(--fw-bold);
	}
	input {
		appearance: none;
		inline-size: 100%;
		block-size: 36px;
		margin: 0;
		border-radius: var(--r-md);
		background: linear-gradient(to right, var(--accent) var(--pct), var(--surface-3) var(--pct));
		cursor: pointer;
	}
	input.custom {
		background: var(--track);
	}
	:global([dir='rtl']) input:not(.custom) {
		background: linear-gradient(to left, var(--accent) var(--pct), var(--surface-3) var(--pct));
	}
	input::-webkit-slider-thumb {
		appearance: none;
		inline-size: 8px;
		block-size: 26px;
		border-radius: var(--r-pill);
		background: white;
		box-shadow: 0 1px 4px oklch(0% 0 0 / 0.35);
	}
	input::-moz-range-thumb {
		inline-size: 8px;
		block-size: 26px;
		border: 0;
		border-radius: var(--r-pill);
		background: white;
		box-shadow: 0 1px 4px oklch(0% 0 0 / 0.35);
	}
</style>
