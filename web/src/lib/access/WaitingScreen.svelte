<script lang="ts">
	// What an unapproved browser sees (ADR 0003): a code to approve on the computer running Control.
	import { Share, Smartphone } from '@lucide/svelte';
	import { api } from '$lib/api';
	import { home } from '$lib/home.svelte';
	import Button from '$lib/ui/Button.svelte';

	const CLAIM_POLL_MS = 2000;

	const ua = navigator.userAgent;
	const ios = /iPhone|iPad/.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
	const android = /Android/.test(ua);
	const installed =
		matchMedia('(display-mode: standalone)').matches ||
		(navigator as Navigator & { standalone?: boolean }).standalone === true;

	type Step =
		| { kind: 'install' }
		| { kind: 'asking' }
		| { kind: 'code'; code: string; claim: string }
		| { kind: 'denied' }
		| { kind: 'error'; message: string };

	// On iPhone the Home Screen app has its own cookies, so approving Safari wouldn't carry over.
	const installFirst = ios && !installed;
	let step = $state<Step>(installFirst ? { kind: 'install' } : { kind: 'asking' });

	async function ask() {
		step = { kind: 'asking' };
		try {
			const { code, claim } = await api.askAccess();
			step = { kind: 'code', code, claim };
		} catch (e) {
			step = { kind: 'error', message: e instanceof Error ? e.message : String(e) };
		}
	}

	if (!installFirst) ask();

	$effect(() => {
		if (step.kind !== 'code') return;
		const { claim } = step;
		const timer = setInterval(async () => {
			try {
				const { status } = await api.claimAccess(claim);
				if (status === 'approved') home.refresh();
				else if (status === 'denied') step = { kind: 'denied' };
				else if (status === 'expired') ask();
			} catch {
				// The Engine blinked; keep asking.
			}
		}, CLAIM_POLL_MS);
		return () => clearInterval(timer);
	});
</script>

<main>
	<span class="icon"><Smartphone size={26} strokeWidth={2} /></span>

	{#if step.kind === 'install'}
		<h1>Add Control to your Home Screen</h1>
		<p>It then opens full screen like an app. Approve it from there, since the app and Safari keep separate logins.</p>
		<ol>
			<li>Tap <Share size={16} strokeWidth={2.3} aria-label="Share" /> at the bottom of Safari.</li>
			<li>Choose <strong>Add to Home Screen</strong>.</li>
			<li>Open Control from its new icon.</li>
		</ol>
		<Button variant="ghost" size="sm" onclick={ask}>Use it in Safari instead</Button>
	{:else if step.kind === 'code'}
		<h1>Approve this phone</h1>
		<p>On the computer running Control, a banner shows this code. Check it matches and click Approve.</p>
		<output class="code" aria-label="Code {step.code}">{step.code.slice(0, 3)} {step.code.slice(3)}</output>
		<p class="wait">Waiting for approval…</p>
		{#if android && !installed}
			<p class="tip">
				Tip: in Chrome's <strong>⋮</strong> menu, <strong>Add to Home screen</strong> gives Control an icon.
			</p>
		{/if}
	{:else if step.kind === 'denied'}
		<h1>Not approved</h1>
		<p>The request was denied on the computer running Control.</p>
		<Button variant="primary" onclick={ask}>Ask again</Button>
	{:else if step.kind === 'error'}
		<h1>Couldn't ask for access</h1>
		<p>{step.message}</p>
		<Button variant="primary" onclick={ask}>Try again</Button>
	{:else}
		<h1>Approve this phone</h1>
		<p class="wait">Getting a code…</p>
	{/if}
</main>

<style>
	main {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: var(--s-4);
		max-inline-size: 420px;
		margin: 0 auto;
		padding: 12vh var(--s-5) var(--s-8);
		text-align: center;
	}
	.icon {
		display: grid;
		place-items: center;
		inline-size: 56px;
		block-size: 56px;
		border-radius: var(--r-pill);
		background: color-mix(in oklab, var(--accent) 22%, var(--surface));
		color: var(--accent-ink);
	}
	h1 {
		margin: 0;
		font-size: var(--fs-xl);
	}
	p {
		margin: 0;
		color: var(--text-2);
	}
	.code {
		margin-block: var(--s-4);
		font-size: 3rem;
		font-weight: var(--fw-bold);
		letter-spacing: 0.08em;
		font-variant-numeric: tabular-nums;
	}
	.wait {
		color: var(--text-3);
		animation: breathe 1.6s var(--ease) infinite alternate;
	}
	@keyframes breathe {
		to {
			opacity: 0.45;
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.wait {
			animation: none;
		}
	}
	ol {
		display: flex;
		flex-direction: column;
		gap: var(--s-2);
		margin: var(--s-2) 0;
		padding: var(--s-4) var(--s-5) var(--s-4) var(--s-8);
		border-radius: var(--r-lg);
		background: var(--surface);
		box-shadow: var(--shadow-1);
		text-align: start;
	}
	ol :global(svg) {
		vertical-align: -3px;
	}
	.tip {
		margin-block-start: var(--s-6);
		font-size: var(--fs-sm);
		color: var(--text-3);
	}
</style>
