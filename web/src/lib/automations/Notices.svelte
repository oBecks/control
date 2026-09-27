<script lang="ts">
	// Automations' notifications (ADR 0012): cards at the top of every page, on any browser, that go
	// by themselves after SHOW_FOR (for every browser, like dismissing them). Each Automation's
	// history keeps what they said. The computer running Control also shows them as Windows
	// notifications.
	import { onDestroy } from 'svelte';
	import { fade } from 'svelte/transition';
	import { resolve } from '$app/paths';
	import { BellRing, X } from '@lucide/svelte';
	import { home } from '$lib/home.svelte';
	import { when } from './parts';

	/** Many at once (a night with the PC asleep): the latest few, and Dismiss all. */
	const SHOWN = 3;
	/** How long a card stays: counted only while the page is visible and nobody points at the cards. */
	const SHOW_FOR = 8000;
	const shown = $derived(home.notices.slice(-SHOWN).reverse());

	let visible = $state(typeof document === 'undefined' || document.visibilityState === 'visible');
	let held = $state(false); // the pointer or keyboard focus is on the cards: someone's reading
	const timers: Record<number, ReturnType<typeof setTimeout>> = {}; // not reactive: nothing shows them
	const reduced = typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches;

	function stopAll() {
		for (const id in timers) {
			clearTimeout(timers[id]);
			delete timers[id];
		}
	}

	$effect(() => {
		const onVisibility = () => (visible = document.visibilityState === 'visible');
		document.addEventListener('visibilitychange', onVisibility);
		return () => document.removeEventListener('visibilitychange', onVisibility);
	});

	// Each notice gets its own countdown, from when it arrived or the page came back into view (so the
	// hidden Window never clears one nobody saw); holding the cards starts them all again afterwards.
	$effect(() => {
		const ids = new Set(home.notices.map((n) => n.id));
		if (!visible || held) {
			stopAll();
			return;
		}
		for (const id in timers) {
			if (!ids.has(Number(id))) {
				clearTimeout(timers[id]);
				delete timers[id];
			}
		}
		for (const id of ids) {
			timers[id] ??= setTimeout(() => {
				delete timers[id];
				home.dismissNotices([id]);
			}, SHOW_FOR);
		}
	});

	onDestroy(stopAll);
</script>

{#if home.notices.length}
	<div
		class="notices"
		role="status"
		onpointerenter={() => (held = true)}
		onpointerleave={() => (held = false)}
		onfocusin={() => (held = true)}
		onfocusout={() => (held = false)}
	>
		{#each shown as n (n.id)}
			<div class="notice" out:fade={{ duration: reduced ? 0 : 200 }}>
				<BellRing size={16} strokeWidth={2.4} />
				<span class="text">
					{#if n.automation}
						<a href={resolve('/(app)/automations/[uid]', { uid: n.automation })}><b>{n.title}</b></a>
					{:else}
						<b>{n.title}</b>
					{/if}
					<span>{n.text}</span>
					<small>{when(n.time)}</small>
				</span>
				<button class="close" aria-label="Dismiss" onclick={() => home.dismissNotices([n.id])}>
					<X size={16} strokeWidth={2.4} />
				</button>
			</div>
		{/each}
		{#if home.notices.length > SHOWN}
			<button class="all" onclick={() => home.dismissNotices()}>Dismiss all {home.notices.length}</button>
		{/if}
	</div>
{/if}

<style>
	.notices {
		display: flex;
		flex-direction: column;
		gap: var(--s-2);
		margin-block-end: var(--s-4);
	}
	@media (min-width: 960px) {
		.notices {
			margin: 0;
			padding: var(--s-6) var(--s-8) 0;
		}
	}
	.notice {
		display: flex;
		align-items: flex-start;
		gap: var(--s-3);
		max-inline-size: 600px;
		padding: var(--s-3) var(--s-4);
		border-radius: var(--r-md);
		background: var(--surface);
		box-shadow: var(--shadow-1);
		border-inline-start: 3px solid var(--accent);
		color: var(--accent-ink);
		animation: in var(--dur) var(--ease);
	}
	.text {
		display: flex;
		flex-direction: column;
		flex: 1;
		min-inline-size: 0;
		color: var(--text);
		font-size: var(--fs-sm);
	}
	.text a {
		color: inherit;
		text-decoration: none;
	}
	.text b {
		font-weight: var(--fw-bold);
	}
	small {
		color: var(--text-2);
		font-size: var(--fs-xs);
	}
	.close {
		display: grid;
		place-items: center;
		flex-shrink: 0;
		inline-size: 28px;
		block-size: 28px;
		border: 0;
		border-radius: var(--r-pill);
		background: transparent;
		color: var(--text-2);
	}
	.close:hover {
		background: var(--surface-2);
	}
	.all {
		align-self: flex-start;
		padding: var(--s-1) var(--s-3);
		border: 0;
		border-radius: var(--r-pill);
		background: transparent;
		color: var(--text-2);
		font-size: var(--fs-sm);
		font-weight: var(--fw-medium);
	}
	.all:hover {
		background: var(--surface-2);
	}
	@keyframes in {
		from {
			opacity: 0;
			translate: 0 -4px;
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.notice {
			animation: none;
		}
	}
</style>
