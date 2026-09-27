<script lang="ts">
	// An on/off switch, e.g. whether an Automation is on.
	interface Props {
		checked: boolean;
		label: string;
		disabled?: boolean;
		onchange: (on: boolean) => void;
	}

	let { checked, label, disabled = false, onchange }: Props = $props();
</script>

<button
	type="button"
	role="switch"
	class="switch"
	aria-checked={checked}
	aria-label={label}
	{disabled}
	onclick={() => onchange(!checked)}
>
	<span class="knob"></span>
</button>

<style>
	.switch {
		position: relative;
		flex-shrink: 0;
		inline-size: 44px;
		block-size: 26px;
		padding: 0;
		border: 0;
		border-radius: var(--r-pill);
		background: var(--surface-3);
		transition: background-color var(--dur-fast) var(--ease);
	}
	.switch[aria-checked='true'] {
		background: var(--accent);
	}
	.switch:disabled {
		opacity: 0.45;
	}
	.knob {
		position: absolute;
		inset-block-start: 3px;
		inset-inline-start: 3px;
		inline-size: 20px;
		block-size: 20px;
		border-radius: var(--r-pill);
		background: oklch(99% 0 0); /* light in both themes, like a physical switch */
		box-shadow: var(--shadow-1);
		transition: translate var(--dur-fast) var(--ease);
	}
	.switch[aria-checked='true'] .knob {
		translate: 18px 0;
	}
	:global([dir='rtl']) .switch[aria-checked='true'] .knob {
		translate: -18px 0;
	}
	@media (prefers-reduced-motion: reduce) {
		.switch,
		.knob {
			transition: none;
		}
	}
</style>
