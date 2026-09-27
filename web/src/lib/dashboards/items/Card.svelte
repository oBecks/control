<script lang="ts">
	// The frame of a Big Control or Remote Pad: its Device's or Group's name, a › that opens its controls,
	// and dimmed when Offline. Right-clicking it opens the controls too, like a Tile.
	import ChevronRight from '@lucide/svelte/icons/chevron-right';
	import WifiOff from '@lucide/svelte/icons/wifi-off';
	import type { Snippet } from 'svelte';

	interface Props {
		name: string;
		/** Beside the name, e.g. "Cool" or "Off". */
		status?: string;
		/** CSS colour the card takes while on. */
		glow?: string;
		on?: boolean;
		offline?: boolean;
		/** Shown but not usable, e.g. while a Dashboard is being arranged. */
		inert?: boolean;
		onopen?: () => void;
		children: Snippet;
	}

	let {
		name,
		status,
		glow = 'var(--accent)',
		on = false,
		offline = false,
		inert = false,
		onopen,
		children
	}: Props = $props();

	function contextmenu(e: MouseEvent) {
		if (!onopen) return;
		e.preventDefault();
		onopen();
	}
</script>

<section
	class="card"
	class:on={on && !offline}
	class:offline
	{inert}
	style:--glow={glow}
	aria-label={name}
	oncontextmenu={contextmenu}
>
	<header>
		<span class="name">{name}</span>
		{#if offline}
			<span class="status"><WifiOff size={13} strokeWidth={2.4} /> Offline</span>
		{:else if status}
			<span class="status num">{status}</span>
		{/if}
		{#if onopen}
			<button class="more" aria-label="Open {name} controls" onclick={onopen}>
				<ChevronRight size={16} strokeWidth={2.4} />
			</button>
		{/if}
	</header>
	<div class="body">{@render children()}</div>
</section>

<style>
	.card {
		display: flex;
		flex-direction: column;
		gap: var(--s-2);
		min-inline-size: 0;
		min-block-size: 0;
		overflow: hidden;
		padding: var(--s-3);
		border-radius: var(--r-lg);
		background: var(--surface);
		border: 1px solid var(--border);
		box-shadow: var(--shadow-1);
		container-type: size;
		transition:
			background-color var(--dur) var(--ease),
			border-color var(--dur) var(--ease);
	}
	.card.on {
		background: color-mix(in oklab, var(--glow) calc(var(--glow-mix) / 2), var(--surface));
		border-color: color-mix(in oklab, var(--glow) 30%, var(--border));
	}
	.card.offline {
		opacity: 0.6;
		filter: grayscale(1);
	}
	.card[inert] {
		box-shadow: none;
	}
	header {
		display: flex;
		align-items: center;
		gap: var(--s-2);
		min-block-size: 28px;
		padding-inline-start: var(--s-1);
	}
	/* The name keeps at least half the room; the status gives way first. */
	.name {
		flex: 1 0 auto;
		max-inline-size: 100%;
		min-inline-size: 50%;
		inline-size: 0;
		overflow: hidden;
		font-weight: var(--fw-medium);
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.status {
		display: inline-flex;
		align-items: center;
		gap: var(--s-1);
		flex: 0 1 auto;
		min-inline-size: 0;
		overflow: hidden;
		white-space: nowrap;
		color: var(--text-2);
		font-size: var(--fs-sm);
	}
	.more {
		display: grid;
		place-items: center;
		flex-shrink: 0;
		inline-size: 28px;
		block-size: 28px;
		border: 0;
		border-radius: var(--r-pill);
		background: color-mix(in oklab, var(--text) 6%, transparent);
		color: var(--text-2);
	}
	.more:hover {
		background: color-mix(in oklab, var(--text) 12%, transparent);
	}
	.card[inert] .more {
		visibility: hidden;
	}
	:global([dir='rtl']) .more :global(svg) {
		transform: scaleX(-1);
	}
	.body {
		position: relative;
		flex: 1;
		min-block-size: 0;
		display: flex;
		flex-direction: column;
	}
</style>
