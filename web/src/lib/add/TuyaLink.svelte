<script lang="ts">
	import { Check, QrCode } from '@lucide/svelte';
	import QRCode from 'qrcode';
	import { api } from '$lib/api';
	import Button from '$lib/ui/Button.svelte';

	interface Props {
		/** How many Tuya devices are waiting for a Link. */
		waiting: number;
		onlinked: () => void;
	}

	let { waiting, onlinked }: Props = $props();

	type Step = { kind: 'intro' } | { kind: 'qr'; svg: string; token: string } | { kind: 'done'; names: string[] };
	let step = $state<Step>({ kind: 'intro' });
	let userCode = $state('');
	let busy = $state(false);
	let error = $state<string | null>(null);

	async function start(e: SubmitEvent) {
		e.preventDefault();
		busy = true;
		error = null;
		try {
			const { token, qr_content } = await api.tuyaStart(userCode.trim());
			// Always dark-on-white: phone cameras need the contrast, whatever the theme.
			const svg = await QRCode.toString(qr_content, {
				type: 'svg',
				margin: 1,
				color: { dark: '#111111', light: '#ffffff' }
			});
			step = { kind: 'qr', svg, token };
		} catch (err) {
			error = err instanceof Error ? err.message : String(err);
		} finally {
			busy = false;
		}
	}

	// While the QR is shown, ask the Engine every 2s whether it was confirmed in Smart Life.
	$effect(() => {
		if (step.kind !== 'qr') return;
		const token = step.token;
		let stopped = false;
		const deadline = Date.now() + 3 * 60_000;
		const tick = async () => {
			if (stopped) return;
			if (Date.now() > deadline) {
				step = { kind: 'intro' };
				error = 'The QR code expired. Start again.';
				return;
			}
			try {
				const r = await api.tuyaPoll(token);
				if (r.status === 'linked') {
					step = { kind: 'done', names: r.devices.map((d) => d.name) };
					onlinked();
					return;
				}
			} catch (err) {
				error = err instanceof Error ? err.message : String(err);
				step = { kind: 'intro' };
				return;
			}
			setTimeout(tick, 2000);
		};
		setTimeout(tick, 2000);
		return () => (stopped = true);
	});
</script>

<div class="card">
	<div class="title">
		<span class="icon"><QrCode size={18} strokeWidth={2.3} /></span>
		<div>
			<h3>Link Tuya / Smart Life</h3>
			<p>
				{waiting} device{waiting === 1 ? '' : 's'} need{waiting === 1 ? 's' : ''} a one-time sign-in to unlock local control.
			</p>
		</div>
	</div>

	{#if step.kind === 'intro'}
		<ol>
			<li>Open <b>Smart Life</b>, tap <b>Me</b>, the <b>⚙ gear</b>, then <b>Account and Security › User Code</b>.</li>
			<li>Type that code here.</li>
		</ol>
		<form onsubmit={start}>
			<input
				bind:value={userCode}
				placeholder="User Code"
				autocomplete="off"
				spellcheck="false"
				aria-label="Smart Life User Code"
			/>
			<Button variant="primary" type="submit" disabled={busy || !userCode.trim()}
				>{busy ? 'Starting…' : 'Show QR code'}</Button
			>
		</form>
		{#if error}<p class="error" role="alert">{error}</p>{/if}
	{:else if step.kind === 'qr'}
		<div class="qr-step">
			<!-- eslint-disable-next-line svelte/no-at-html-tags -- SVG generated locally by the qrcode library -->
			<div class="qr">{@html step.svg}</div>
			<div>
				<p>
					In Smart Life, on the <b>Home</b> tab, tap the <b>scan</b> icon (top right), scan this code, and tap
					<b>Confirm login</b>.
				</p>
				<p class="muted waiting"><span class="pulse"></span> Waiting for you to confirm…</p>
				<Button variant="ghost" size="sm" onclick={() => (step = { kind: 'intro' })}>Cancel</Button>
			</div>
		</div>
	{:else}
		<p class="done">
			<Check size={18} strokeWidth={2.6} /> Linked {step.names.join(', ')}. {step.names.length === 1 ? 'It' : 'They'}'re
			on Home now.
		</p>
	{/if}
</div>

<style>
	.card {
		display: flex;
		flex-direction: column;
		gap: var(--s-4);
		padding: var(--s-5);
		border-radius: var(--r-lg);
		background: var(--surface);
		border: 1px solid var(--border);
		box-shadow: var(--shadow-1);
	}
	.title {
		display: flex;
		gap: var(--s-3);
	}
	.icon {
		display: grid;
		place-items: center;
		flex-shrink: 0;
		inline-size: 36px;
		block-size: 36px;
		border-radius: var(--r-pill);
		background: var(--accent);
		color: var(--on-accent);
	}
	h3 {
		margin: 0;
		font-size: var(--fs-lg);
	}
	p {
		margin: 0;
	}
	.title p,
	.muted {
		color: var(--text-2);
		font-size: var(--fs-sm);
	}
	ol {
		margin: 0;
		padding-inline-start: var(--s-5);
		display: flex;
		flex-direction: column;
		gap: var(--s-1);
	}
	form {
		display: flex;
		flex-wrap: wrap;
		gap: var(--s-2);
	}
	input {
		flex: 1 1 180px;
		min-block-size: 44px;
		padding-inline: var(--s-4);
		border-radius: var(--r-pill);
		border: 1px solid var(--border);
		background: var(--surface-2);
	}
	.error {
		color: var(--danger);
		font-size: var(--fs-sm);
	}
	.qr-step {
		display: flex;
		flex-wrap: wrap;
		gap: var(--s-5);
		align-items: center;
	}
	.qr-step > div:last-child {
		flex: 1 1 200px;
		display: flex;
		flex-direction: column;
		align-items: flex-start;
		gap: var(--s-3);
	}
	.qr {
		inline-size: 200px;
		padding: var(--s-2);
		border-radius: var(--r-md);
		background: #fff;
	}
	.qr :global(svg) {
		display: block;
		inline-size: 100%;
		block-size: auto;
	}
	.waiting {
		display: flex;
		align-items: center;
		gap: var(--s-2);
	}
	.pulse {
		inline-size: 8px;
		block-size: 8px;
		border-radius: var(--r-pill);
		background: var(--accent);
		animation: blink 1s var(--ease) infinite alternate;
	}
	@keyframes blink {
		to {
			opacity: 0.2;
		}
	}
	.done {
		display: flex;
		align-items: center;
		gap: var(--s-2);
		font-weight: var(--fw-medium);
	}
</style>
