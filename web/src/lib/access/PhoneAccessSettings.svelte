<script lang="ts">
	// Settings → Phone access: open Control to the home Wi-Fi, and manage Approved Browsers (ADR 0003).
	import { Smartphone } from '@lucide/svelte';
	import QRCode from 'qrcode';
	import { api, type ApprovedBrowser, type PhoneAccess } from '$lib/api';
	import { home } from '$lib/home.svelte';
	import Button from '$lib/ui/Button.svelte';
	import Segmented from '$lib/ui/Segmented.svelte';

	const BROWSERS_POLL_MS = 4000;

	let status = $state<PhoneAccess | null>(null);
	let browsers = $state<ApprovedBrowser[]>([]);
	let busy = $state(false);
	let qr = $state('');
	/** Browsers whose Revoke is in flight. */
	let revoking = $state<Record<string, boolean>>({});

	async function load() {
		try {
			[status, browsers] = await Promise.all([api.phoneAccess(), api.approvedBrowsers()]);
		} catch {
			// The layout already tells the user when the Engine is unreachable.
		}
	}

	$effect(() => {
		load();
		// A phone joins a few seconds after it's approved, from wherever it was approved.
		const timer = setInterval(() => document.visibilityState === 'visible' && load(), BROWSERS_POLL_MS);
		return () => clearInterval(timer);
	});

	$effect(() => {
		const url = status?.url;
		if (!url) return;
		QRCode.toString(url, { type: 'svg', margin: 1, color: { dark: '#000', light: '#fff' } }).then((svg) => (qr = svg));
	});

	async function setOn(on: boolean) {
		busy = true;
		try {
			status = await api.setPhoneAccess(on);
		} catch (e) {
			home.notify(e instanceof Error ? e.message : String(e));
		} finally {
			busy = false;
		}
	}

	async function revoke(b: ApprovedBrowser) {
		revoking[b.id] = true;
		try {
			await api.revokeBrowser(b.id);
			browsers = browsers.filter((x) => x.id !== b.id);
			if (b.current) home.refresh();
		} catch (e) {
			home.notify(e instanceof Error ? e.message : String(e));
		} finally {
			delete revoking[b.id];
		}
	}

	function ago(seconds: number) {
		const s = Date.now() / 1000 - seconds;
		if (s < 120) return 'just now';
		if (s < 3600) return `${Math.round(s / 60)} min ago`;
		if (s < 86400) return `${Math.round(s / 3600)} h ago`;
		const days = Math.round(s / 86400);
		return days === 1 ? 'yesterday' : `${days} days ago`;
	}
</script>

<section>
	<h2>Phone access</h2>
	<p class="lead">Use Control from phones on your home Wi-Fi. Each phone needs your approval once.</p>

	{#if status}
		{#if status.can_change}
			<Segmented
				label="Phone access"
				options={[
					{ value: 'off', label: 'Off' },
					{ value: 'on', label: 'On' }
				]}
				value={status.on ? 'on' : 'off'}
				onchange={(v) => !busy && setOn(v === 'on')}
			/>
		{/if}

		{#if status.error}
			<p class="error" role="alert">{status.error}</p>
		{:else if status.on && status.url}
			<div class="join">
				{#if status.can_change && qr}
					<!-- eslint-disable-next-line svelte/no-at-html-tags -- SVG generated locally by the qrcode library -->
					<div class="qr">{@html qr}</div>
				{/if}
				<div>
					<p>On a phone connected to the home Wi-Fi, {status.can_change ? 'scan this or ' : ''}open</p>
					<p class="url">{status.url}</p>
					<p class="hint">The phone then shows a code. Approve it in the banner that appears here.</p>
				</div>
			</div>
			{#if status.can_change}
				<p class="hint">
					If Windows asks whether to allow Python on networks, allow <strong>Private networks</strong>, or phones can't
					connect.
				</p>
			{/if}
		{:else if status.on}
			<p class="hint">
				Phone access is on. Restart Control with <code>control serve</code> to open it to the home Wi-Fi.
			</p>
		{/if}
	{/if}

	{#if browsers.length}
		<h3>Approved phones</h3>
		<ul>
			{#each browsers as b (b.id)}
				<li>
					<Smartphone size={18} strokeWidth={2.2} />
					<span class="name">
						{b.name}
						{#if b.current}<span class="this">This phone</span>{/if}
						<small>Last used {ago(b.last_seen)}</small>
					</span>
					<Button size="sm" variant="ghost" disabled={revoking[b.id]} onclick={() => revoke(b)}>Revoke</Button>
				</li>
			{/each}
		</ul>
	{/if}
</section>

<style>
	section {
		display: flex;
		flex-direction: column;
		gap: var(--s-3);
	}
	h2 {
		margin: 0;
		font-size: var(--fs-lg);
	}
	h3 {
		margin: var(--s-3) 0 0;
		font-size: var(--fs-md);
	}
	p {
		margin: 0;
	}
	.lead,
	.hint {
		color: var(--text-2);
	}
	.hint {
		font-size: var(--fs-sm);
	}
	.error {
		color: var(--danger);
		font-weight: var(--fw-medium);
	}
	.join {
		display: flex;
		align-items: center;
		gap: var(--s-4);
		padding: var(--s-4);
		border-radius: var(--r-lg);
		background: var(--surface);
		box-shadow: var(--shadow-1);
	}
	.join > div:last-child {
		display: flex;
		flex-direction: column;
		gap: var(--s-1);
		min-inline-size: 0;
	}
	.qr {
		flex: none;
		inline-size: 132px;
		padding: var(--s-1);
		border-radius: var(--r-sm);
		background: #fff;
	}
	.qr :global(svg) {
		display: block;
	}
	.url {
		font-size: var(--fs-lg);
		font-weight: var(--fw-bold);
		overflow-wrap: anywhere;
		user-select: all;
	}
	ul {
		display: flex;
		flex-direction: column;
		gap: var(--s-1);
		margin: 0;
		padding: 0;
		list-style: none;
	}
	li {
		display: flex;
		align-items: center;
		gap: var(--s-3);
		padding: var(--s-2) var(--s-3);
		border-radius: var(--r-sm);
		background: var(--surface);
		color: var(--text-2);
	}
	.name {
		flex: 1;
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		column-gap: var(--s-2);
		color: var(--text);
		font-weight: var(--fw-medium);
	}
	.name small {
		flex-basis: 100%;
		color: var(--text-3);
		font-weight: normal;
	}
	.this {
		padding: 0 var(--s-2);
		border-radius: var(--r-pill);
		background: color-mix(in oklab, var(--accent) 22%, var(--surface));
		color: var(--accent-ink);
		font-size: var(--fs-xs);
	}
</style>
