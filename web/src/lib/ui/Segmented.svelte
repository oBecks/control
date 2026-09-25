<script lang="ts" generics="T extends string">
	interface Props {
		label: string;
		options: { value: T; label: string }[];
		value: T;
		onchange?: (value: T) => void;
	}

	let { label, options, value = $bindable(), onchange }: Props = $props();

	function pick(v: T) {
		value = v;
		onchange?.(v);
	}
</script>

<div class="seg" role="radiogroup" aria-label={label}>
	{#each options as o (o.value)}
		<button
			role="radio"
			aria-checked={value === o.value}
			class:active={value === o.value}
			onclick={() => pick(o.value)}
		>
			{o.label}
		</button>
	{/each}
</div>

<style>
	.seg {
		display: flex;
		gap: 2px;
		padding: 3px;
		border-radius: var(--r-pill);
		background: var(--surface-2);
		border: 1px solid var(--border);
	}
	button {
		flex: 1;
		min-block-size: 36px;
		padding-inline: var(--s-3);
		border: 0;
		border-radius: var(--r-pill);
		background: transparent;
		color: var(--text-2);
		font-size: var(--fs-sm);
		font-weight: var(--fw-medium);
		transition:
			background-color var(--dur-fast) var(--ease),
			color var(--dur-fast) var(--ease);
	}
	button.active {
		background: var(--surface);
		color: var(--text);
		box-shadow: var(--shadow-1);
	}
</style>
