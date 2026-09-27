<script lang="ts">
	// A Big Control: a light's or light Group's brightness as one wide bar, filled in the light's colour.
	// Drag or tap along it to set the brightness (sent on release); the bulb at its start turns it on or off.
	import ChevronRight from '@lucide/svelte/icons/chevron-right';
	import Lightbulb from '@lucide/svelte/icons/lightbulb';
	import LightbulbOff from '@lucide/svelte/icons/lightbulb-off';
	import WifiOff from '@lucide/svelte/icons/wifi-off';
	import { glowFor } from '$lib/color';
	import type { LightState } from '$lib/types';

	interface Props {
		name: string;
		value: LightState;
		offline?: boolean;
		inert?: boolean;
		onchange: (change: { on?: boolean; brightness?: number }) => void;
		onopen?: () => void;
	}

	let { name, value, offline = false, inert = false, onchange, onopen }: Props = $props();

	/** The brightness while dragging, before it's sent. */
	let dragging = $state<number | null>(null);
	const level = $derived(dragging ?? value.brightness);
	const on = $derived(value.on && !offline);
	const glow = $derived(glowFor('light', value));

	function release() {
		if (dragging === null) return;
		const brightness = dragging;
		dragging = null;
		if (brightness !== value.brightness || !value.on) onchange({ brightness });
	}

	function contextmenu(e: MouseEvent) {
		if (!onopen) return;
		e.preventDefault();
		onopen();
	}
</script>

<div
	role="group"
	class="bar"
	class:on
	class:offline
	{inert}
	style:--glow={glow}
	style:--pct="{on ? level : 0}%"
	oncontextmenu={contextmenu}
>
	<span class="fill" aria-hidden="true"></span>
	<input
		type="range"
		min="1"
		max="100"
		value={value.brightness}
		disabled={offline}
		aria-label="{name} brightness"
		aria-valuetext={on ? `${level}%` : 'Off'}
		oninput={(e) => (dragging = Number(e.currentTarget.value))}
		onchange={release}
	/>
	<button
		class="power"
		aria-label={on ? `Turn ${name} off` : `Turn ${name} on`}
		aria-pressed={on}
		disabled={offline}
		onclick={() => onchange({ on: !value.on })}
	>
		{#if offline}<WifiOff size={18} strokeWidth={2.2} />{:else if on}<Lightbulb
				size={20}
				strokeWidth={2.2}
			/>{:else}<LightbulbOff size={20} strokeWidth={2.2} />{/if}
	</button>
	<span class="text" aria-hidden="true">
		<span class="name">{name}</span>
		<span class="value num">{offline ? 'Offline' : on ? `${level}%` : 'Off'}</span>
	</span>
	{#if onopen}
		<button class="more" aria-label="Open {name} controls" onclick={onopen}>
			<ChevronRight size={16} strokeWidth={2.4} />
		</button>
	{/if}
</div>

<style>
	.bar {
		position: relative;
		display: flex;
		align-items: center;
		gap: var(--s-3);
		min-inline-size: 0;
		overflow: hidden;
		padding-inline: var(--s-2) var(--s-3);
		border-radius: var(--r-lg);
		background: var(--surface);
		border: 1px solid var(--border);
		box-shadow: var(--shadow-1);
		user-select: none;
		-webkit-user-select: none;
		transition: border-color var(--dur) var(--ease);
	}
	.bar.on {
		border-color: color-mix(in oklab, var(--glow) 38%, var(--border));
	}
	.bar.offline {
		opacity: 0.6;
		filter: grayscale(1);
	}
	.bar[inert] {
		box-shadow: none;
	}
	.fill {
		position: absolute;
		inset-block: 0;
		inset-inline-start: 0;
		inline-size: var(--pct);
		background: color-mix(in oklab, var(--glow) 55%, var(--surface));
		pointer-events: none;
	}
	/* The whole bar is the slider; the bulb and › sit on top of it. */
	input {
		position: absolute;
		inset: 0;
		inline-size: 100%;
		block-size: 100%;
		margin: 0;
		opacity: 0;
		cursor: pointer;
		touch-action: pan-y;
	}
	.bar:has(input:focus-visible) {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}
	.power,
	.more {
		position: relative;
		display: grid;
		place-items: center;
		flex-shrink: 0;
		border: 0;
		border-radius: var(--r-pill);
	}
	.power {
		inline-size: 40px;
		block-size: 40px;
		background: var(--surface-2);
		color: var(--text-2);
	}
	.on .power {
		background: var(--glow);
		color: oklch(from var(--glow) clamp(0.2, (0.64 - l) * 1000, 0.98) calc(c * 0.25) h);
	}
	.more {
		inline-size: 28px;
		block-size: 28px;
		background: color-mix(in oklab, var(--text) 8%, transparent);
		color: var(--text-2);
	}
	.bar[inert] .more {
		visibility: hidden;
	}
	:global([dir='rtl']) .more :global(svg) {
		transform: scaleX(-1);
	}
	.text {
		position: relative;
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		gap: var(--s-2);
		flex: 1;
		min-inline-size: 0;
		pointer-events: none;
	}
	.name {
		overflow: hidden;
		font-weight: var(--fw-medium);
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.value {
		flex-shrink: 0;
		font-weight: var(--fw-bold);
	}
</style>
