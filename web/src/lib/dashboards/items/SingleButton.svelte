<script lang="ts">
	// A Single Button: one remote button, or one Streamer App Shortcut, on its own.
	// It flashes when pressed, since a remote can't say whether anything happened.
	import type { Component } from 'svelte';

	interface Props {
		/** What it says, e.g. "HDMI 1" or "Netflix"; with an icon, the Device's name goes under it. */
		label: string;
		/** The Device's name, under the label when there's room. */
		device: string;
		icon?: Component;
		/** An app that's open right now. */
		lit?: boolean;
		/** The button is gone from its Device (unlearned, or the App Shortcut removed). */
		missing?: boolean;
		offline?: boolean;
		inert?: boolean;
		onpress: () => void;
		onopen?: () => void;
	}

	let {
		label,
		device,
		icon: Icon,
		lit = false,
		missing = false,
		offline = false,
		inert = false,
		onpress,
		onopen
	}: Props = $props();

	let pulse = $state(0);

	function click() {
		pulse++;
		onpress();
	}

	function contextmenu(e: MouseEvent) {
		if (!onopen) return;
		e.preventDefault();
		onopen();
	}
</script>

<button
	class="single"
	class:lit
	class:offline
	{inert}
	disabled={missing || offline}
	aria-label="{label}, {device}{missing ? ' (no longer there)' : offline ? ' (offline)' : ''}"
	onclick={click}
	oncontextmenu={contextmenu}
>
	{#key pulse}{#if pulse}<span class="sent" aria-hidden="true"></span>{/if}{/key}
	{#if Icon}<Icon size={22} strokeWidth={2.3} />{/if}
	<span class="label">{missing ? 'Gone' : label}</span>
	<span class="device">{device}</span>
</button>

<style>
	.single {
		position: relative;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 2px;
		min-inline-size: 0;
		overflow: hidden;
		padding: var(--s-2);
		border-radius: var(--r-lg);
		border: 1px solid var(--border);
		background: var(--surface);
		box-shadow: var(--shadow-1);
		color: var(--text);
		text-align: center;
		container-type: size;
		touch-action: manipulation;
		transition:
			background-color var(--dur-fast) var(--ease),
			transform var(--dur-fast) var(--ease);
	}
	.single:active:not(:disabled) {
		transform: scale(0.95);
		background: color-mix(in oklab, var(--accent) 30%, var(--surface));
	}
	.single.lit {
		background: color-mix(in oklab, var(--accent) var(--glow-mix), var(--surface));
		border-color: color-mix(in oklab, var(--accent) 38%, var(--border));
	}
	.single:disabled {
		opacity: 0.6;
	}
	.single.offline {
		filter: grayscale(1);
	}
	.single[inert] {
		box-shadow: none;
	}
	.label {
		max-inline-size: 100%;
		overflow: hidden;
		font-weight: var(--fw-bold);
		font-size: var(--fs-md);
		line-height: 1.2;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.device {
		max-inline-size: 100%;
		overflow: hidden;
		color: var(--text-2);
		font-size: var(--fs-xs);
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	/* Too short for three lines: just the icon, or the label. */
	@container (max-height: 70px) {
		.device {
			display: none;
		}
		.single:has(:global(svg)) .label {
			display: none;
		}
	}
	.sent {
		position: absolute;
		inset: -1px;
		border-radius: inherit;
		pointer-events: none;
		box-shadow: inset 0 0 0 2px var(--accent);
		animation: sent 600ms var(--ease) forwards;
	}
	@keyframes sent {
		from {
			opacity: 1;
			background: color-mix(in oklab, var(--accent) 22%, transparent);
		}
		to {
			opacity: 0;
		}
	}
</style>
