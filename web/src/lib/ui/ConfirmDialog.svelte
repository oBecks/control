<script lang="ts">
	// Control's own "are you sure?". The browser's confirm() doesn't show everywhere Control runs
	// (it can count as "no" without asking), so Control asks itself.
	import Button from './Button.svelte';

	interface Props {
		title: string;
		detail?: string;
		/** The button that goes ahead, e.g. "Leave without saving". */
		confirmLabel: string;
		/** The button that stays, e.g. "Keep editing". */
		cancelLabel?: string;
		onconfirm: () => void;
		oncancel: () => void;
	}

	let { title, detail, confirmLabel, cancelLabel = 'Cancel', onconfirm, oncancel }: Props = $props();
</script>

<svelte:window onkeydown={(e) => e.key === 'Escape' && oncancel()} />

<button class="scrim" aria-label={cancelLabel} onclick={oncancel}></button>
<div class="dialog" role="alertdialog" aria-modal="true" aria-labelledby="confirm-title">
	<h2 id="confirm-title">{title}</h2>
	{#if detail}<p>{detail}</p>{/if}
	<div class="actions">
		<Button variant="primary" autofocus onclick={oncancel}>{cancelLabel}</Button>
		<Button variant="ghost" onclick={onconfirm}>{confirmLabel}</Button>
	</div>
</div>

<style>
	.scrim {
		position: fixed;
		inset: 0;
		z-index: 40;
		border: 0;
		background: var(--scrim);
		animation: fade var(--dur) var(--ease);
	}
	.dialog {
		position: fixed;
		inset-block-start: 50%;
		inset-inline-start: 50%;
		translate: -50% -50%;
		z-index: 41;
		display: flex;
		flex-direction: column;
		gap: var(--s-3);
		inline-size: min(400px, calc(100vw - 32px));
		padding: var(--s-6);
		border-radius: var(--r-lg);
		background: var(--surface);
		box-shadow: var(--shadow-2);
		animation: pop var(--dur) var(--ease);
	}
	h2 {
		margin: 0;
		font-size: var(--fs-lg);
		font-weight: var(--fw-bold);
	}
	p {
		margin: 0;
		color: var(--text-2);
	}
	.actions {
		display: flex;
		flex-wrap: wrap;
		gap: var(--s-2);
		margin-block-start: var(--s-2);
	}
	.actions :global(.btn.ghost) {
		color: var(--danger);
	}
	@keyframes fade {
		from {
			opacity: 0;
		}
	}
	@keyframes pop {
		from {
			opacity: 0;
			scale: 0.96;
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.scrim,
		.dialog {
			animation: none;
		}
	}
</style>
