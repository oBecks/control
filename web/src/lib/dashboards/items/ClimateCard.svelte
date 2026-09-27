<script lang="ts">
	// A Big Control: an AC's (or AC Group's) temperature with − and +, its mode, and On / Off.
	// An AC's state is an Assumed State: what Control last sent, marked ≈.
	import Droplets from '@lucide/svelte/icons/droplets';
	import Fan from '@lucide/svelte/icons/fan';
	import Minus from '@lucide/svelte/icons/minus';
	import Plus from '@lucide/svelte/icons/plus';
	import Power from '@lucide/svelte/icons/power';
	import RefreshCcw from '@lucide/svelte/icons/refresh-ccw';
	import Snowflake from '@lucide/svelte/icons/snowflake';
	import Sun from '@lucide/svelte/icons/sun';
	import type { Component } from 'svelte';
	import { glowFor } from '$lib/color';
	import type { ClimateFeatures, ClimateState, StateChange } from '$lib/types';
	import Card from './Card.svelte';

	interface Props {
		name: string;
		features: ClimateFeatures;
		value: ClimateState;
		assumed?: boolean;
		offline?: boolean;
		inert?: boolean;
		onchange: (change: StateChange) => void;
		onopen?: () => void;
	}

	let { name, features, value, assumed = false, offline = false, inert = false, onchange, onopen }: Props = $props();

	const MODES: Record<string, { label: string; icon: Component }> = {
		cool: { label: 'Cool', icon: Snowflake },
		heat: { label: 'Heat', icon: Sun },
		fan: { label: 'Fan', icon: Fan },
		fan_only: { label: 'Fan', icon: Fan },
		dry: { label: 'Dry', icon: Droplets },
		auto: { label: 'Auto', icon: RefreshCcw },
		heat_cool: { label: 'Auto', icon: RefreshCcw }
	};

	function step(dir: 1 | -1) {
		const t = Math.min(features.max_temp, Math.max(features.min_temp, value.target_temp + dir * features.step));
		if (t !== value.target_temp) onchange({ target_temp: t });
	}
</script>

<Card
	{name}
	status={(value.on ? (MODES[value.mode]?.label ?? value.mode) : 'Off') + (assumed ? ' ≈' : '')}
	glow={glowFor('climate', value)}
	on={value.on}
	{offline}
	{inert}
	{onopen}
>
	<div class="ac" class:off={!value.on}>
		<div class="temp">
			<button
				class="step"
				aria-label="Lower {name}'s temperature"
				disabled={offline || value.target_temp <= features.min_temp}
				onclick={() => step(-1)}
			>
				<Minus size={20} strokeWidth={2.4} />
			</button>
			<span class="value num" aria-live="polite">{value.target_temp}<span class="unit">°</span></span>
			<button
				class="step"
				aria-label="Raise {name}'s temperature"
				disabled={offline || value.target_temp >= features.max_temp}
				onclick={() => step(1)}
			>
				<Plus size={20} strokeWidth={2.4} />
			</button>
		</div>

		<div class="modes" role="radiogroup" aria-label="{name} mode">
			{#each features.modes as mode (mode)}
				{@const m = MODES[mode]}
				<button
					role="radio"
					aria-checked={value.on && value.mode === mode}
					aria-label={m?.label ?? mode}
					title={m?.label ?? mode}
					disabled={offline}
					onclick={() => onchange({ mode })}
				>
					{#if m}<m.icon size={18} strokeWidth={2.3} />{:else}{mode.slice(0, 1).toUpperCase()}{/if}
				</button>
			{/each}
		</div>

		<div class="power">
			<button class:lit={value.on} aria-pressed={value.on} disabled={offline} onclick={() => onchange({ on: true })}>
				<Power size={15} strokeWidth={2.5} /> On
			</button>
			<button class:lit={!value.on} aria-pressed={!value.on} disabled={offline} onclick={() => onchange({ on: false })}>
				Off
			</button>
		</div>
	</div>
</Card>

<style>
	.ac {
		flex: 1;
		min-block-size: 0;
		display: flex;
		flex-direction: column;
		justify-content: space-between;
		gap: var(--s-2);
	}
	.temp {
		flex: 1;
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--s-1);
	}
	.value {
		font-size: clamp(var(--fs-xl), 22cqi, var(--fs-display));
		font-weight: var(--fw-bold);
		line-height: 1;
		letter-spacing: -0.02em;
	}
	.off .value {
		color: var(--text-2);
	}
	.unit {
		font-weight: var(--fw-regular);
		color: var(--text-2);
	}
	button {
		border: 1px solid var(--border);
		background: var(--surface);
		color: var(--text);
		transition:
			background-color var(--dur-fast) var(--ease),
			transform var(--dur-fast) var(--ease);
	}
	button:active:not(:disabled) {
		transform: scale(0.94);
	}
	button:disabled {
		opacity: 0.4;
	}
	.step {
		display: grid;
		place-items: center;
		flex-shrink: 0;
		inline-size: 40px;
		block-size: 40px;
		border-radius: var(--r-pill);
		box-shadow: var(--shadow-1);
	}
	.modes {
		display: flex;
		flex-wrap: wrap;
		justify-content: center;
		gap: var(--s-1);
	}
	.modes button {
		display: grid;
		place-items: center;
		flex: 1 0 34px;
		max-inline-size: 48px;
		block-size: 34px;
		border-radius: var(--r-pill);
		font-weight: var(--fw-bold);
		font-size: var(--fs-sm);
	}
	.modes button[aria-checked='true'] {
		background: var(--glow);
		border-color: var(--glow);
		color: oklch(from var(--glow) clamp(0.2, (0.64 - l) * 1000, 0.98) calc(c * 0.25) h);
	}
	.power {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: var(--s-1);
	}
	.power button {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: var(--s-1);
		block-size: 34px;
		border-radius: var(--r-pill);
		font-weight: var(--fw-medium);
		font-size: var(--fs-sm);
	}
	.power button.lit {
		background: var(--surface-3);
		font-weight: var(--fw-bold);
	}
</style>
