<script lang="ts">
	interface Props {
		title: string;
		summary?: string;
	}

	let { title, summary }: Props = $props();
</script>

<h2 class="section">
	{title}
	{#if summary}<span>· {summary}</span>{/if}
</h2>

<style>
	.section {
		margin: 0 0 var(--s-3);
		font-size: var(--fs-lg);
		font-weight: var(--fw-bold);
	}
	span {
		font-weight: var(--fw-regular);
		color: var(--text-2);
		font-size: var(--fs-md);
	}
</style>
