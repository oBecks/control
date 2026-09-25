<script lang="ts">
	import type { Snippet } from 'svelte';

	interface Props {
		label: string;
		onclose: () => void;
		children: Snippet;
	}

	let { label, onclose, children }: Props = $props();
</script>

<svelte:window onkeydown={(e) => e.key === 'Escape' && onclose()} />

<button class="scrim" aria-label="Close" onclick={onclose}></button>
<div class="sheet" role="dialog" aria-modal="true" aria-label={label}>
	<div class="grabber" aria-hidden="true"></div>
	{@render children()}
</div>

<style>
	.scrim {
		position: fixed;
		inset: 0;
		z-index: 20;
		border: 0;
		background: var(--scrim);
		animation: fade var(--dur) var(--ease);
	}
	.sheet {
		position: fixed;
		inset-inline: 0;
		inset-block-end: 0;
		z-index: 21;
		max-block-size: 88dvh;
		overflow-y: auto;
		overscroll-behavior: contain;
		padding: var(--s-3) var(--s-5) calc(var(--s-8) + env(safe-area-inset-bottom));
		border-start-start-radius: 28px;
		border-start-end-radius: 28px;
		background: var(--surface);
		box-shadow: var(--shadow-2);
		animation: rise var(--dur-slow) var(--ease);
	}
	.grabber {
		inline-size: 40px;
		block-size: 5px;
		margin: 0 auto var(--s-4);
		border-radius: var(--r-pill);
		background: var(--surface-3);
	}
	@keyframes rise {
		from {
			transform: translateY(40%);
			opacity: 0;
		}
	}
	@keyframes fade {
		from {
			opacity: 0;
		}
	}
</style>
