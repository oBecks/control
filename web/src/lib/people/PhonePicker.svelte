<script lang="ts">
	// Pick a Person's phone from what answers on the home network now (ADR 0014). Looking takes a
	// few seconds: Control wakes every address, then reads who answered.
	import { RefreshCw, Smartphone, X } from '@lucide/svelte';
	import { api } from '$lib/api';
	import type { Nearby, Person } from '$lib/types';
	import Button from '$lib/ui/Button.svelte';

	interface Props {
		person: Person;
		onpick: (phone: { mac: string; ip: string; name: string }) => void;
		onclose: () => void;
	}

	let { person, onpick, onclose }: Props = $props();

	let found = $state<Nearby[] | null>(null);
	let error = $state('');
	let showAll = $state(false);

	/** Phones use private addresses; the rest (TVs, printers, the router) are hidden until asked. */
	const likely = $derived((found ?? []).filter((n) => n.private || n.browser));
	const listed = $derived(showAll ? (found ?? []) : likely);

	async function look() {
		found = null;
		error = '';
		try {
			found = await api.nearby();
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
			found = [];
		}
	}

	$effect(() => {
		look();
	});

	function label(n: Nearby) {
		return n.browser ?? n.name ?? (n.private ? 'Phone' : 'Device');
	}
</script>

<div class="head">
	<h2>Add a phone for {person.name}</h2>
	<button type="button" class="close" aria-label="Close" onclick={onclose}><X size={18} strokeWidth={2.4} /></button>
</div>
<p class="hint">
	Make sure the phone is on the home Wi-Fi and its screen is on. Easiest: open Control on the phone itself and tap
	<strong>This is my phone</strong> in Settings → People.
</p>

{#if found === null}
	<p class="looking" role="status">Looking for phones on your Wi-Fi…</p>
{:else}
	{#if error}<p class="error" role="alert">{error}</p>{/if}
	{#if listed.length}
		<ul>
			{#each listed as n (n.mac)}
				<li>
					<button class="pick" onclick={() => onpick({ mac: n.mac, ip: n.ip, name: n.name ?? label(n) })}>
						<Smartphone size={18} strokeWidth={2.2} />
						<span>
							{label(n)}
							<small>
								{n.ip}{n.browser && n.name ? ` · ${n.name}` : ''}{n.private ? ' · private address' : ''}
							</small>
						</span>
					</button>
				</li>
			{/each}
		</ul>
	{:else if !error}
		<p class="hint">
			No phones answered. Wake the phone (turn its screen on), check it's on the home Wi-Fi, then look again.
		</p>
	{/if}
	<div class="actions">
		<Button size="sm" onclick={look}><RefreshCw size={14} strokeWidth={2.4} /> Look again</Button>
		{#if (found ?? []).length > likely.length}
			<Button size="sm" variant="ghost" onclick={() => (showAll = !showAll)}>
				{showAll ? 'Only likely phones' : `Show everything (${(found ?? []).length})`}
			</Button>
		{/if}
	</div>
{/if}

<style>
	.head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--s-3);
		margin-block-end: var(--s-2);
	}
	h2 {
		margin: 0;
		font-size: var(--fs-lg);
	}
	.close {
		display: grid;
		place-items: center;
		flex-shrink: 0;
		inline-size: 32px;
		block-size: 32px;
		border: 0;
		border-radius: var(--r-pill);
		background: var(--surface-2);
		color: var(--text-2);
	}
	p {
		margin: 0 0 var(--s-3);
	}
	.hint,
	.looking {
		color: var(--text-2);
		font-size: var(--fs-sm);
	}
	.looking {
		animation: pulse 1.4s var(--ease) infinite alternate;
	}
	@keyframes pulse {
		to {
			opacity: 0.45;
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.looking {
			animation: none;
		}
	}
	.error {
		color: var(--danger);
		font-weight: var(--fw-medium);
	}
	ul {
		display: flex;
		flex-direction: column;
		gap: var(--s-1);
		margin: 0 0 var(--s-3);
		padding: 0;
		list-style: none;
	}
	.pick {
		display: flex;
		align-items: center;
		gap: var(--s-3);
		inline-size: 100%;
		padding: var(--s-3);
		border: 0;
		border-radius: var(--r-md);
		background: var(--surface-2);
		color: var(--text-2);
		text-align: start;
	}
	.pick:hover {
		background: color-mix(in oklab, var(--accent) 14%, var(--surface-2));
	}
	.pick span {
		display: flex;
		flex-direction: column;
		color: var(--text);
		font-weight: var(--fw-medium);
	}
	.pick small {
		color: var(--text-3);
		font-weight: normal;
	}
	.actions {
		display: flex;
		flex-wrap: wrap;
		gap: var(--s-2);
	}
</style>
