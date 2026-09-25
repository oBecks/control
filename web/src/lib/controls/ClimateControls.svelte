<script lang="ts">
	import { Info, Minus, Plus, Power } from '@lucide/svelte';
	import type { ClimateFeatures, ClimateState, StateChange } from '$lib/types';
	import Button from '$lib/ui/Button.svelte';
	import Segmented from '$lib/ui/Segmented.svelte';

	interface Props {
		features: ClimateFeatures;
		value: ClimateState;
		assumed?: boolean;
		onchange: (change: StateChange) => void;
	}

	let { features, value, assumed = false, onchange }: Props = $props();

	const LABELS: Record<string, string> = {
		cool: 'Cool',
		heat: 'Heat',
		fan: 'Fan',
		fan_only: 'Fan',
		dry: 'Dry',
		auto: 'Auto',
		heat_cool: 'Auto',
		low: 'Low',
		mid: 'Mid',
		med: 'Mid',
		high: 'High',
		static: 'Fixed',
		swing: 'Swing'
	};
	const opts = (list: string[]) => list.map((v) => ({ value: v, label: LABELS[v] ?? v }));

	const tint = $derived(
		value.mode === 'heat' ? 'var(--heat)' : value.mode.startsWith('fan') ? 'var(--fan)' : 'var(--cool)'
	);

	function step(dir: 1 | -1) {
		const t = Math.min(features.max_temp, Math.max(features.min_temp, value.target_temp + dir * features.step));
		if (t !== value.target_temp) onchange({ target_temp: t });
	}
</script>

<div class="controls">
	<div class="temp" class:off={!value.on} style:--tint={tint}>
		<button
			class="stepper"
			aria-label="Lower temperature"
			onclick={() => step(-1)}
			disabled={value.target_temp <= features.min_temp}
		>
			<Minus size={22} strokeWidth={2.4} />
		</button>
		<div class="reading">
			<span class="value num">{value.target_temp}<span class="unit">°</span></span>
			<span class="sub">{value.on ? (LABELS[value.mode] ?? value.mode) : 'Off'}</span>
		</div>
		<button
			class="stepper"
			aria-label="Raise temperature"
			onclick={() => step(1)}
			disabled={value.target_temp >= features.max_temp}
		>
			<Plus size={22} strokeWidth={2.4} />
		</button>
	</div>

	<div class="power">
		<Button variant={value.on ? 'secondary' : 'primary'} onclick={() => onchange({ on: true })}>
			<Power size={16} strokeWidth={2.4} /> On
		</Button>
		<Button variant="secondary" onclick={() => onchange({ on: false })}>Off</Button>
	</div>

	<Segmented label="Mode" options={opts(features.modes)} value={value.mode} onchange={(mode) => onchange({ mode })} />
	{#if features.fan_modes.length}
		<Segmented label="Fan" options={opts(features.fan_modes)} value={value.fan} onchange={(fan) => onchange({ fan })} />
	{/if}
	{#if features.swing_modes.length && value.swing}
		<Segmented
			label="Swing"
			options={opts(features.swing_modes)}
			value={value.swing}
			onchange={(swing) => onchange({ swing })}
		/>
	{/if}

	{#if assumed}
		<p class="assumed">
			<Info size={16} strokeWidth={2.3} />
			<span
				>Last set by Control. If someone used the AC's own remote, this may differ. Use On or Off to put them back in
				sync.</span
			>
		</p>
	{/if}
</div>

<style>
	.controls {
		display: flex;
		flex-direction: column;
		gap: var(--s-5);
	}
	.temp {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: var(--s-5) var(--s-4);
		border-radius: var(--r-lg);
		background: color-mix(in oklab, var(--tint) 20%, var(--surface));
		transition: background-color var(--dur) var(--ease);
	}
	.temp.off {
		background: var(--surface-2);
	}
	.reading {
		display: flex;
		flex-direction: column;
		align-items: center;
	}
	.value {
		font-size: var(--fs-display);
		font-weight: var(--fw-bold);
		line-height: 1;
		letter-spacing: -0.02em;
	}
	.unit {
		font-weight: var(--fw-regular);
		color: var(--text-2);
	}
	.sub {
		margin-block-start: var(--s-1);
		color: var(--text-2);
		font-weight: var(--fw-medium);
	}
	.stepper {
		display: grid;
		place-items: center;
		inline-size: 52px;
		block-size: 52px;
		border-radius: var(--r-pill);
		border: 1px solid var(--border);
		background: var(--surface);
		box-shadow: var(--shadow-1);
		transition: transform var(--dur-fast) var(--ease);
	}
	.stepper:active:not(:disabled) {
		transform: scale(0.94);
	}
	.stepper:disabled {
		opacity: 0.4;
	}
	.power {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: var(--s-2);
	}
	.assumed {
		display: flex;
		gap: var(--s-2);
		margin: 0;
		padding: var(--s-3);
		border-radius: var(--r-md);
		background: var(--surface-2);
		color: var(--text-2);
		font-size: var(--fs-sm);
	}
	.assumed :global(svg) {
		flex-shrink: 0;
		margin-block-start: 2px;
	}
</style>
