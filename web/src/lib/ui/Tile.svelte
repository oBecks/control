<script lang="ts">
	import type { Component } from 'svelte';
	import { ChevronRight, WifiOff } from '@lucide/svelte';

	interface Props {
		name: string;
		status: string;
		icon: Component;
		on?: boolean;
		/** CSS colour the Tile takes when on (device's real colour). */
		glow?: string;
		offline?: boolean;
		assumed?: boolean;
		isNew?: boolean;
		selected?: boolean;
		/** Increment to flash a "sent" confirmation (remotes, whose state can't be shown). */
		pulse?: number;
		/** On a Dashboard: small is icon and name only (opened by holding it or right-clicking); large is 2×2. */
		size?: 'small' | 'normal' | 'large';
		/** Shown but not usable, e.g. while a Dashboard is being arranged. */
		inert?: boolean;
		ontoggle?: () => void;
		onopen?: () => void;
	}

	let {
		name,
		status,
		icon: Icon,
		on = false,
		glow = 'var(--accent)',
		offline = false,
		assumed = false,
		isNew = false,
		selected = false,
		pulse = 0,
		size = 'normal',
		inert = false,
		ontoggle,
		onopen
	}: Props = $props();

	const small = $derived(size === 'small');
	const large = $derived(size === 'large');

	// Press-and-hold opens Device Controls (phone); the click that follows is swallowed.
	const HOLD_MS = 450;
	let holdTimer: ReturnType<typeof setTimeout> | undefined;
	let held = false;

	function pointerdown(e: PointerEvent) {
		if (e.button !== 0) return;
		held = false;
		holdTimer = setTimeout(() => {
			held = true;
			navigator.vibrate?.(10);
			onopen?.();
		}, HOLD_MS);
	}

	function cancelHold() {
		clearTimeout(holdTimer);
	}

	function click() {
		if (held) {
			held = false;
			return;
		}
		// An Offline device can't be toggled; tapping it offers help instead.
		if (offline) onopen?.();
		else ontoggle?.();
	}

	function contextmenu(e: MouseEvent) {
		e.preventDefault();
		cancelHold();
		onopen?.();
	}
</script>

<div
	class="tile"
	class:on={on && !offline}
	class:offline
	class:selected
	class:small
	class:large
	{inert}
	style:--glow={glow}
>
	{#key pulse}{#if pulse}<span class="sent" aria-hidden="true"></span>{/if}{/key}
	<button
		class="hit"
		aria-pressed={offline ? undefined : on}
		aria-label="{name}, {offline ? 'offline' : status}"
		onclick={click}
		oncontextmenu={contextmenu}
		onpointerdown={pointerdown}
		onpointerup={cancelHold}
		onpointerleave={cancelHold}
		onpointercancel={cancelHold}
	></button>

	<div class="top">
		<span class="badge" aria-hidden="true">
			{#if offline}<WifiOff size={18} strokeWidth={2.2} />{:else}<Icon size={large ? 30 : 20} strokeWidth={2.2} />{/if}
		</span>
		{#if isNew}<span class="new">New</span>{/if}
	</div>

	<div class="text">
		<span class="name">{name}</span>
		{#if !small}
			<span class="status num">
				{offline ? 'Offline' : status}
				{#if assumed && !offline}<span class="assumed" title="Assumed state: last set by Control">≈</span>{/if}
			</span>
		{/if}
	</div>

	{#if !small}
		<button class="more" aria-label="Open {name} controls" onclick={() => onopen?.()}>
			<ChevronRight size={16} strokeWidth={2.4} />
		</button>
	{/if}
</div>

<style>
	.tile {
		position: relative;
		display: flex;
		flex-direction: column;
		justify-content: space-between;
		min-block-size: var(--tile-h);
		padding: var(--s-4);
		border-radius: var(--r-lg);
		background: var(--surface);
		border: 1px solid var(--border);
		box-shadow: var(--shadow-1);
		user-select: none;
		-webkit-user-select: none;
		-webkit-touch-callout: none;
		transition:
			background-color var(--dur) var(--ease),
			border-color var(--dur) var(--ease),
			box-shadow var(--dur) var(--ease),
			transform var(--dur-fast) var(--ease),
			opacity var(--dur) var(--ease);
	}

	.tile:has(.hit:active) {
		transform: scale(0.97);
	}

	.tile.on {
		background: color-mix(in oklab, var(--glow) var(--glow-mix), var(--surface));
		border-color: color-mix(in oklab, var(--glow) 38%, var(--border));
		box-shadow: 0 12px 32px -10px color-mix(in oklab, var(--glow) var(--glow-shadow), transparent);
	}

	.sent {
		position: absolute;
		inset: -1px;
		border-radius: inherit;
		pointer-events: none;
		box-shadow: 0 0 0 2px var(--glow);
		animation: sent 600ms var(--ease) forwards;
	}
	@keyframes sent {
		from {
			opacity: 1;
			background: color-mix(in oklab, var(--glow) 22%, transparent);
		}
		to {
			opacity: 0;
		}
	}

	.tile.selected {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}

	.tile.offline {
		opacity: 0.6;
		filter: grayscale(1);
	}

	/* Full-tile invisible button: the toggle target */
	.hit {
		position: absolute;
		inset: 0;
		border: 0;
		background: transparent;
		border-radius: inherit;
		touch-action: manipulation;
	}

	.top,
	.text {
		position: relative;
		pointer-events: none;
	}

	.top {
		display: flex;
		align-items: center;
		gap: var(--s-2);
	}

	.badge {
		display: grid;
		place-items: center;
		inline-size: 40px;
		block-size: 40px;
		border-radius: var(--r-pill);
		background: var(--surface-2);
		color: var(--text-2);
		transition:
			background-color var(--dur) var(--ease),
			color var(--dur) var(--ease);
	}

	.on .badge {
		background: var(--glow);
		/* Dark icon on light glows, light icon on dark glows */
		color: oklch(from var(--glow) clamp(0.2, (0.64 - l) * 1000, 0.98) calc(c * 0.25) h);
	}

	.new {
		padding: 2px var(--s-2);
		border-radius: var(--r-pill);
		background: var(--accent);
		color: var(--on-accent);
		font-size: var(--fs-xs);
		font-weight: var(--fw-bold);
		letter-spacing: 0.02em;
	}

	.text {
		display: flex;
		flex-direction: column;
		gap: 1px;
		padding-inline-end: var(--s-6);
	}

	.name {
		font-weight: var(--fw-medium);
		font-size: var(--fs-md);
		line-height: 1.25;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.status {
		font-size: var(--fs-sm);
		color: var(--text-2);
	}

	.assumed {
		margin-inline-start: 2px;
		font-weight: var(--fw-bold);
		color: var(--text-3);
		cursor: help;
		pointer-events: auto;
	}

	.more {
		position: absolute;
		inset-block-end: var(--s-3);
		inset-inline-end: var(--s-3);
		display: grid;
		place-items: center;
		inline-size: 28px;
		block-size: 28px;
		border: 0;
		border-radius: var(--r-pill);
		background: color-mix(in oklab, var(--text) 6%, transparent);
		color: var(--text-2);
		transition: background-color var(--dur-fast) var(--ease);
	}

	.more:hover {
		background: color-mix(in oklab, var(--text) 12%, transparent);
	}

	/* Large: the same Tile, read from across the room */
	.large {
		min-block-size: calc(var(--tile-h) * 2 + var(--s-3));
		padding: var(--s-5);
	}
	.large .badge {
		inline-size: 60px;
		block-size: 60px;
	}
	.large .name {
		font-size: var(--fs-xl);
		font-weight: var(--fw-bold);
	}
	.large .status {
		font-size: var(--fs-lg);
	}

	/* Small: icon above a name of up to two lines */
	.small {
		align-items: center;
		justify-content: center;
		gap: var(--s-2);
		padding: var(--s-3) var(--s-2);
		text-align: center;
	}
	.small .top {
		justify-content: center;
	}
	.small .new {
		position: absolute;
		inset-block-start: calc(-1 * var(--s-2));
		inset-inline-end: calc(-1 * var(--s-2));
	}
	.small .text {
		padding: 0;
		max-inline-size: 100%;
	}
	.small .name {
		display: -webkit-box;
		-webkit-box-orient: vertical;
		-webkit-line-clamp: 2;
		line-clamp: 2;
		white-space: normal;
		font-size: var(--fs-sm);
		overflow-wrap: anywhere;
	}

	.tile[inert] {
		box-shadow: none;
	}
	.tile[inert] .more {
		visibility: hidden;
	}

	/* RTL: the chevron points toward the end edge */
	:global([dir='rtl']) .more :global(svg) {
		transform: scaleX(-1);
	}
</style>
