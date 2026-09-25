<script lang="ts">
	import { ChevronRight, Sparkles } from '@lucide/svelte';

	interface Props {
		title: string;
		detail?: string;
		onclick?: () => void;
	}

	let { title, detail, onclick }: Props = $props();
</script>

<button class="banner" {onclick}>
	<span class="icon"><Sparkles size={18} strokeWidth={2.3} /></span>
	<span class="text">
		<span class="title">{title}</span>
		{#if detail}<span class="detail">{detail}</span>{/if}
	</span>
	<ChevronRight size={18} strokeWidth={2.3} />
</button>

<style>
	.banner {
		display: flex;
		align-items: center;
		gap: var(--s-3);
		inline-size: 100%;
		padding: var(--s-3) var(--s-4);
		border-radius: var(--r-lg);
		border: 1px solid color-mix(in oklab, var(--accent) 45%, var(--border));
		background: color-mix(in oklab, var(--accent) 14%, var(--surface));
		text-align: start;
		color: var(--text);
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
</style>
