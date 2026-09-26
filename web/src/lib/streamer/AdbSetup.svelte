<script lang="ts">
	// The Link's optional second step (ADR 0008): let Control open any app and see what's installed,
	// through the box's developer mode (adb). Used by the setup and by Edit in a Streamer's controls.
	import { Check, Wrench } from '@lucide/svelte';
	import { api, type AppChoices } from '$lib/api';
	import Button from '$lib/ui/Button.svelte';

	interface Props {
		uid: string;
		/** Why this is offered, e.g. an app without a link was picked. */
		reason?: string;
		onallowed: (choices: AppChoices) => void;
		onskip?: () => void;
	}

	let { uid, reason, onallowed, onskip }: Props = $props();

	let open = $state(false);
	let busy = $state(false);
	let done = $state(false);
	let error = $state<string | null>(null);

	async function allow() {
		busy = true;
		error = null;
		try {
			onallowed(await api.streamerAllowAdb(uid));
			done = true;
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		} finally {
			busy = false;
		}
	}
</script>

<div class="adb">
	{#if done}
		<p class="done"><Check size={16} strokeWidth={2.6} /> Control can open any app and sees what's installed.</p>
	{:else}
		<div class="head">
			<Wrench size={16} strokeWidth={2.4} />
			<div>
				<b>Open any app, and see what's installed</b>
				<p class="muted">
					{reason ??
						"Optional. Some apps, like yes+, can't be opened directly otherwise; Control then goes through their Play Store page."}
				</p>
			</div>
		</div>
		{#if open}
			<ol>
				<li>On the box, open <b>Settings → Device Preferences → About</b>.</li>
				<li>Press OK on <b>Build</b> 7 times, until it says you're a developer.</li>
				<li>
					Go back to <b>Device Preferences → Developer options</b> and turn on <b>Network debugging</b> (or USB debugging).
				</li>
				<li>Press <b>Connect</b> here, then choose <b>Allow</b> when the TV asks.</li>
			</ol>
			<div class="actions">
				<Button variant="primary" size="sm" onclick={allow} disabled={busy}
					>{busy ? 'Waiting for Allow on the TV…' : 'Connect'}</Button
				>
				<Button variant="ghost" size="sm" onclick={() => (open = false)} disabled={busy}>Not now</Button>
			</div>
		{:else}
			<div class="actions">
				<Button variant="secondary" size="sm" onclick={() => (open = true)}>Set it up</Button>
				{#if onskip}<Button variant="ghost" size="sm" onclick={onskip}>Use the Play Store</Button>{/if}
			</div>
		{/if}
		{#if error}<p class="error" role="alert">{error}</p>{/if}
	{/if}
</div>

<style>
	.adb {
		display: flex;
		flex-direction: column;
		gap: var(--s-3);
		padding: var(--s-4);
		border-radius: var(--r-md);
		background: var(--surface-2);
	}
	.head {
		display: flex;
		gap: var(--s-3);
	}
	.head :global(svg) {
		flex-shrink: 0;
		margin-block-start: 3px;
		color: var(--text-2);
	}
	p {
		margin: 0;
	}
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
		font-size: var(--fs-sm);
	}
	.actions {
		display: flex;
		flex-wrap: wrap;
		gap: var(--s-2);
	}
	.done {
		display: flex;
		align-items: center;
		gap: var(--s-2);
		font-weight: var(--fw-medium);
	}
	.error {
		color: var(--danger);
		font-size: var(--fs-sm);
	}
</style>
