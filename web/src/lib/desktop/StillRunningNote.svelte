<script lang="ts">
	// Said once, in the Window, after the user first closed it with Windows notifications off: closing
	// only hides the Window (ADR 0004). With notifications on, the tray icon's notification says it instead.
	import { MonitorUp } from '@lucide/svelte';
	import { api } from '$lib/api';
	import Button from '$lib/ui/Button.svelte';

	let show = $state(false);

	async function check() {
		try {
			show = (await api.desktop()).close_note;
		} catch {
			// The layout already tells the user when the Engine is unreachable.
		}
	}

	$effect(() => {
		check();
		// The Desktop App fires this each time it brings the Window back.
		window.addEventListener('control:window-shown', check);
		return () => window.removeEventListener('control:window-shown', check);
	});

	async function dismiss() {
		show = false;
		await api.dismissCloseNote().catch(() => {});
	}
</script>

{#if show}
	<section class="note" aria-label="Control is still running">
		<span class="icon"><MonitorUp size={18} strokeWidth={2.3} /></span>
		<span class="text">
			<span class="title">Control kept running</span>
			<span class="detail">
				Closing the window leaves it in the tray next to the clock, so phones keep working. To stop it, right-click its
				icon and choose Quit Control.
			</span>
		</span>
		<Button size="sm" variant="primary" onclick={dismiss}>Got it</Button>
	</section>
{/if}

<style>
	.note {
		display: flex;
		align-items: center;
		gap: var(--s-3);
		margin-block-end: var(--s-4);
		padding: var(--s-3) var(--s-4);
		border-radius: var(--r-lg);
		border: 1px solid color-mix(in oklab, var(--accent) 45%, var(--border));
		background: color-mix(in oklab, var(--accent) 14%, var(--surface));
	}
	@media (min-width: 960px) {
		.note {
			margin: var(--s-6) var(--s-8) 0; /* lined up with the page, like the layout's access requests */
		}
	}
	.icon {
		flex: none;
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
		min-inline-size: 0;
	}
	.title {
		font-weight: var(--fw-bold);
	}
	.detail {
		color: var(--text-2);
		font-size: var(--fs-sm);
	}
</style>
