<script lang="ts">
	// A phone showing a code, waiting for someone here to approve it (ADR 0003).
	import { Smartphone } from '@lucide/svelte';
	import type { AccessRequest } from '$lib/api';
	import Button from '$lib/ui/Button.svelte';

	interface Props {
		request: AccessRequest;
		ondecide: (approve: boolean) => void;
	}

	let { request, ondecide }: Props = $props();
</script>

<section class="ask" aria-label="Access request from {request.name}">
	<span class="icon"><Smartphone size={18} strokeWidth={2.3} /></span>
	<span class="text">
		<span class="title">{request.name} wants to use Control</span>
		<span class="detail">Approve only if the phone shows this code</span>
	</span>
	<span class="code">{request.code.slice(0, 3)} {request.code.slice(3)}</span>
	<span class="actions">
		<Button size="sm" onclick={() => ondecide(false)}>Deny</Button>
		<Button size="sm" variant="primary" onclick={() => ondecide(true)}>Approve</Button>
	</span>
</section>

<style>
	.ask {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: var(--s-3);
		padding: var(--s-3) var(--s-4);
		border-radius: var(--r-lg);
		border: 1px solid color-mix(in oklab, var(--accent) 45%, var(--border));
		background: color-mix(in oklab, var(--accent) 14%, var(--surface));
		animation: drop var(--dur) var(--ease);
	}
	.icon {
		display: grid;
		place-items: center;
		inline-size: 34px;
		block-size: 34px;
		border-radius: var(--r-pill);
		background: var(--accent);
		color: var(--on-accent);
	}
	.text {
		flex: 1;
		min-inline-size: 180px;
		display: flex;
		flex-direction: column;
	}
	.title {
		font-weight: var(--fw-bold);
	}
	.detail {
		font-size: var(--fs-sm);
		color: var(--text-2);
	}
	.code {
		font-size: var(--fs-xl);
		font-weight: var(--fw-bold);
		letter-spacing: 0.06em;
		font-variant-numeric: tabular-nums;
	}
	.actions {
		display: flex;
		gap: var(--s-2);
	}
	@keyframes drop {
		from {
			opacity: 0;
			translate: 0 -6px;
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.ask {
			animation: none;
		}
	}
</style>
