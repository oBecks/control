<script lang="ts">
	import { hexToRgb, kelvinToRgb, rgbCss, type RGB } from '$lib/color';
	import type { LightFeatures, LightState, StateChange } from '$lib/types';
	import Segmented from '$lib/ui/Segmented.svelte';
	import Slider from '$lib/ui/Slider.svelte';

	interface Props {
		features: LightFeatures;
		value: LightState;
		onchange: (change: StateChange) => void;
	}

	let { features, value, onchange }: Props = $props();

	const SWATCHES = ['#ff3b30', '#ff9500', '#ffcc00', '#34c759', '#00c7be', '#007aff', '#5856d6', '#af52de', '#ff2d95'];

	// Local copies so sliders move smoothly; the device is told on release.
	let brightness = $state(0);
	let kelvin = $state(4000);
	let mode = $state<'white' | 'color'>('white');
	// Re-sync when the device's state changes (only reads `value`, so local drags don't retrigger it).
	$effect.pre(() => {
		brightness = value.brightness;
		if (value.kelvin != null) kelvin = value.kelvin;
		mode = value.mode;
	});

	const kelvinTrack = $derived(
		`linear-gradient(to right, ${[features.min_kelvin, 2700, 4000, 5500, features.max_kelvin]
			.map((k) => rgbCss(kelvinToRgb(k)))
			.join(', ')})`
	);

	const sameRgb = (a: RGB | null, b: RGB) => !!a && a.every((v, i) => v === b[i]);
</script>

<div class="controls">
	<Slider
		label="Brightness"
		min={1}
		max={100}
		bind:value={brightness}
		format={(v) => `${v}%`}
		onchange={(v) => onchange({ brightness: v })}
	/>

	{#if features.color && features.color_temp}
		<Segmented
			label="Light mode"
			options={[
				{ value: 'white', label: 'White' },
				{ value: 'color', label: 'Colour' }
			]}
			bind:value={mode}
		/>
	{/if}

	{#if mode === 'white' && features.color_temp}
		<Slider
			label="White"
			min={features.min_kelvin}
			max={features.max_kelvin}
			step={100}
			bind:value={kelvin}
			track={kelvinTrack}
			format={(v) => `${v}K`}
			onchange={(v) => onchange({ kelvin: v })}
		/>
	{:else if features.color}
		<div class="swatches" role="radiogroup" aria-label="Colour">
			{#each SWATCHES as hex (hex)}
				{@const rgb = hexToRgb(hex)}
				<button
					role="radio"
					aria-checked={value.mode === 'color' && sameRgb(value.rgb, rgb)}
					aria-label={hex}
					style:--sw={hex}
					onclick={() => onchange({ rgb })}
				></button>
			{/each}
		</div>
	{/if}
</div>

<style>
	.controls {
		display: flex;
		flex-direction: column;
		gap: var(--s-6);
	}
	.swatches {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(40px, 1fr));
		gap: var(--s-3);
	}
	.swatches button {
		aspect-ratio: 1;
		border-radius: var(--r-pill);
		border: 2px solid transparent;
		background: var(--sw);
		box-shadow: inset 0 0 0 1px oklch(0% 0 0 / 0.08);
		transition: transform var(--dur-fast) var(--ease);
	}
	.swatches button:active {
		transform: scale(0.92);
	}
	.swatches button[aria-checked='true'] {
		outline: 2px solid var(--text);
		outline-offset: 3px;
	}
</style>
