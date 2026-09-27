<script lang="ts">
	import type { Component } from 'svelte';

	interface Props {
		label: string;
		icon: Component;
		active?: boolean;
		dashed?: boolean;
		/** Says what a tap does, e.g. "Set Movie night". */
		title?: string;
		onclick?: () => void;
		/** Holding it or right-clicking it, like a Tile opens Device Controls. */
		onopen?: () => void;
	}

	let { label, icon: Icon, active = false, dashed = false, title, onclick, onopen }: Props = $props();

	// Press-and-hold opens it (phone); the click that follows is swallowed.
	const HOLD_MS = 450;
	let holdTimer: ReturnType<typeof setTimeout> | undefined;
	let held = false;

	function pointerdown(e: PointerEvent) {
		if (e.button !== 0 || !onopen) return;
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
		onclick?.();
	}

	function contextmenu(e: MouseEvent) {
		if (!onopen) return;
		e.preventDefault();
		cancelHold();
		onopen();
	}
</script>

<button
	class="chip"
	class:active
	class:dashed
	aria-pressed={dashed ? undefined : active}
	{title}
	onclick={click}
	oncontextmenu={contextmenu}
	onpointerdown={pointerdown}
	onpointerup={cancelHold}
	onpointerleave={cancelHold}
	onpointercancel={cancelHold}
>
	<Icon size={16} strokeWidth={2.3} />
	<span>{label}</span>
</button>

<style>
	.chip {
		display: inline-flex;
		align-items: center;
		gap: var(--s-2);
		flex-shrink: 0;
		min-block-size: 40px;
		padding-inline: var(--s-4);
		border-radius: var(--r-pill);
		border: 1px solid var(--border);
		background: var(--surface);
		box-shadow: var(--shadow-1);
		font-weight: var(--fw-medium);
		font-size: var(--fs-sm);
		-webkit-touch-callout: none;
		user-select: none;
		transition:
			background-color var(--dur) var(--ease),
			transform var(--dur-fast) var(--ease);
	}
	.chip:active {
		transform: scale(0.96);
	}
	.chip.active {
		background: var(--accent);
		border-color: transparent;
		color: var(--on-accent);
	}
	.chip.dashed {
		border-style: dashed;
		background: transparent;
		box-shadow: none;
		color: var(--text-2);
	}
</style>
