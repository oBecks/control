<script lang="ts">
	// A Big Control: a colour wheel for a light or light Group, with a strip of whites under it.
	// Drag on the wheel to pick a colour (sent on release); the edge is the fullest colour, the middle white.
	import { glowFor, hsToRgb, kelvinToRgb, rgbCss, rgbToHs, type RGB } from '$lib/color';
	import type { LightFeatures, LightState } from '$lib/types';
	import Card from './Card.svelte';

	interface Props {
		name: string;
		features: LightFeatures;
		value: LightState;
		offline?: boolean;
		inert?: boolean;
		onchange: (change: { rgb?: RGB; kelvin?: number }) => void;
		onopen?: () => void;
	}

	let { name, features, value, offline = false, inert = false, onchange, onopen }: Props = $props();

	/** Where the pointer is on the wheel while dragging, before it's sent. */
	let dragging = $state<{ hue: number; sat: number } | null>(null);
	/** The white while its slider moves. */
	let white = $state<number | null>(null);

	const point = $derived(dragging ?? (value.mode === 'color' && value.rgb ? rgbToHs(value.rgb) : null));
	const kelvin = $derived(white ?? value.kelvin ?? Math.round((features.min_kelvin + features.max_kelvin) / 2));
	const whites = $derived(
		`linear-gradient(to right, ${[features.min_kelvin, 2700, 4000, 5500, features.max_kelvin]
			.map((k) => rgbCss(kelvinToRgb(k)))
			.join(', ')})`
	);

	function at(e: PointerEvent, wheel: HTMLElement) {
		const box = wheel.getBoundingClientRect();
		const dx = e.clientX - (box.left + box.width / 2);
		const dy = e.clientY - (box.top + box.height / 2);
		const hue = ((Math.atan2(dx, -dy) * 180) / Math.PI + 360) % 360;
		return { hue, sat: Math.min(1, Math.hypot(dx, dy) / (box.width / 2)) };
	}

	function down(e: PointerEvent) {
		if (e.button !== 0) return;
		const wheel = e.currentTarget as HTMLElement;
		wheel.setPointerCapture(e.pointerId);
		dragging = at(e, wheel);
	}

	function move(e: PointerEvent) {
		if (dragging) dragging = at(e, e.currentTarget as HTMLElement);
	}

	function up() {
		if (!dragging) return;
		const { hue, sat } = dragging;
		dragging = null;
		onchange({ rgb: hsToRgb(hue, sat) });
	}

	/** Arrow keys: left and right turn the hue, up and down change how full the colour is. */
	function key(e: KeyboardEvent) {
		const now = point ?? { hue: 0, sat: 1 };
		const turn = { ArrowLeft: [-10, 0], ArrowRight: [10, 0], ArrowUp: [0, 0.1], ArrowDown: [0, -0.1] }[e.key];
		if (!turn) return;
		e.preventDefault();
		const hue = (now.hue + turn[0] + 360) % 360;
		const sat = Math.max(0, Math.min(1, now.sat + turn[1]));
		onchange({ rgb: hsToRgb(hue, sat) });
	}
</script>

<Card
	{name}
	status={offline ? undefined : value.on ? undefined : 'Off'}
	glow={glowFor('light', value)}
	on={value.on}
	{offline}
	{inert}
	{onopen}
>
	<div class="colour">
		<div class="well">
			<div
				class="wheel"
				role="slider"
				tabindex={offline ? -1 : 0}
				aria-label="{name} colour"
				aria-valuemin={0}
				aria-valuemax={360}
				aria-valuenow={Math.round(point?.hue ?? 0)}
				aria-valuetext={point ? `hue ${Math.round(point.hue)}°, ${Math.round(point.sat * 100)}% colour` : 'white'}
				onpointerdown={down}
				onpointermove={move}
				onpointerup={up}
				onpointercancel={() => (dragging = null)}
				onkeydown={key}
			>
				{#if point}
					{@const rad = (point.hue * Math.PI) / 180}
					<span
						class="marker"
						style:left="{50 + Math.sin(rad) * point.sat * 50}%"
						style:top="{50 - Math.cos(rad) * point.sat * 50}%"
						style:background={rgbCss(hsToRgb(point.hue, point.sat))}
					></span>
				{/if}
			</div>
		</div>
		{#if features.color_temp}
			<input
				class="whites"
				class:picked={value.mode === 'white' && !dragging}
				type="range"
				min={features.min_kelvin}
				max={features.max_kelvin}
				step="100"
				value={kelvin}
				aria-label="{name} white"
				aria-valuetext="{kelvin}K"
				disabled={offline}
				style:--track={whites}
				oninput={(e) => (white = Number(e.currentTarget.value))}
				onchange={() => {
					if (white !== null) onchange({ kelvin: white });
					white = null;
				}}
			/>
		{/if}
	</div>
</Card>

<style>
	.colour {
		flex: 1;
		min-block-size: 0;
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: var(--s-3);
	}
	.well {
		flex: 1;
		min-block-size: 0;
		align-self: stretch;
		display: grid;
		place-items: center;
		container-type: size;
	}
	.wheel {
		position: relative;
		inline-size: min(100cqi, 100cqh);
		aspect-ratio: 1;
		border-radius: 50%;
		background:
			radial-gradient(closest-side, white, transparent), conic-gradient(red, yellow, lime, cyan, blue, magenta, red);
		box-shadow: inset 0 0 0 1px oklch(0% 0 0 / 0.08);
		cursor: crosshair;
		touch-action: none;
	}
	.wheel:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 3px;
	}
	.marker {
		position: absolute;
		inline-size: 22px;
		block-size: 22px;
		border: 3px solid white;
		border-radius: 50%;
		box-shadow: 0 1px 4px oklch(0% 0 0 / 0.4);
		translate: -50% -50%;
		pointer-events: none;
	}
	.whites {
		appearance: none;
		flex-shrink: 0;
		inline-size: 100%;
		block-size: 28px;
		margin: 0;
		border-radius: var(--r-pill);
		background: var(--track);
		box-shadow: inset 0 0 0 1px oklch(0% 0 0 / 0.08);
		cursor: pointer;
	}
	.whites.picked {
		outline: 2px solid var(--text);
		outline-offset: 2px;
	}
	.whites::-webkit-slider-thumb {
		appearance: none;
		inline-size: 8px;
		block-size: 22px;
		border-radius: var(--r-pill);
		background: white;
		box-shadow: 0 1px 4px oklch(0% 0 0 / 0.35);
	}
	.whites::-moz-range-thumb {
		inline-size: 8px;
		block-size: 22px;
		border: 0;
		border-radius: var(--r-pill);
		background: white;
		box-shadow: 0 1px 4px oklch(0% 0 0 / 0.35);
	}
</style>
