<script lang="ts">
	// Settings → People (ADR 0014): who lives here, their phones, and who's home now.
	import { Smartphone, Trash2, UserPlus, X } from '@lucide/svelte';
	import { tick } from 'svelte';
	import { api, type Access } from '$lib/api';
	import { home } from '$lib/home.svelte';
	import type { Person } from '$lib/types';
	import { people } from './people.svelte';
	import Button from '$lib/ui/Button.svelte';
	import ConfirmDialog from '$lib/ui/ConfirmDialog.svelte';
	import Sheet from '$lib/ui/Sheet.svelte';
	import PhonePicker from './PhonePicker.svelte';

	let access = $state<Access>('local');
	let newName = $state('');
	let adding = $state(false);
	let nameInput = $state<HTMLInputElement>();
	/** The Person whose "Add a phone" sheet is open. */
	let picking = $state<Person | null>(null);
	let deleting = $state<Person | null>(null);
	let busy = $state<Record<string, boolean>>({});

	/** On a phone that isn't marked yet: it can say "This is my phone". */
	const onPhone = $derived(access === 'approved');
	const thisPhoneMarked = $derived(people.list.some((p) => p.phones.some((ph) => ph.current)));

	// Presence changes on its own (someone walks in), so the list stays fresh while it's shown.
	$effect(() => people.watch());

	$effect(() => {
		api.access().then(
			(a) => (access = a.access),
			() => {}
		);
	});

	async function act(key: string, work: () => Promise<unknown>) {
		busy[key] = true;
		try {
			await work();
			await people.refresh();
		} catch (e) {
			home.notify(e instanceof Error ? e.message : String(e));
		} finally {
			delete busy[key];
		}
	}

	async function addPerson(e: SubmitEvent) {
		e.preventDefault();
		const name = newName.trim();
		if (!name) return;
		await act('new', async () => {
			await api.addPerson(name);
			newName = '';
			adding = false;
		});
	}

	function rename(p: Person, name: string) {
		name = name.trim();
		if (name && name !== p.name) act(p.uid, () => api.renamePerson(p.uid, name));
	}

	function presence(p: Person): { text: string; tone: 'home' | 'away' | 'unknown' } {
		if (!p.phones.length) return { text: 'Add a phone to see when they’re home', tone: 'unknown' };
		if (p.home === true) return { text: 'Home', tone: 'home' };
		if (p.home === false) return { text: 'Away', tone: 'away' };
		return { text: 'Looking for their phone…', tone: 'unknown' };
	}

	function seen(at: number | null) {
		if (at === null) return 'Not seen yet';
		const s = Date.now() / 1000 - at;
		if (s < 90) return 'Seen just now';
		if (s < 3600) return `Seen ${Math.round(s / 60)} min ago`;
		return `Seen ${Math.round(s / 3600)} h ago`;
	}
</script>

<section>
	<h2>People</h2>
	<p class="lead">
		Who lives here. Control tells who's home from their phones on the home Wi-Fi, for Automations like “when the last
		person leaves”. Nothing leaves the house.
	</p>

	{#if people.loaded}
		<ul class="people">
			{#each people.list as p (p.uid)}
				{@const state = presence(p)}
				<li class="person">
					<div class="top">
						<span class="dot {state.tone}" aria-hidden="true"></span>
						<input
							class="name"
							aria-label="Name"
							value={p.name}
							maxlength="40"
							onchange={(e) => rename(p, e.currentTarget.value)}
							onkeydown={(e) => e.key === 'Enter' && e.currentTarget.blur()}
						/>
						<button class="icon" aria-label="Remove {p.name}" onclick={() => (deleting = p)}>
							<Trash2 size={16} strokeWidth={2.2} />
						</button>
					</div>
					<p class="state {state.tone}">{state.text}</p>

					{#if p.phones.length}
						<ul class="phones">
							{#each p.phones as ph (ph.mac)}
								<li>
									<Smartphone size={16} strokeWidth={2.2} />
									<span class="phone">
										{ph.name}
										{#if ph.current}<span class="this">This phone</span>{/if}
										<small>{seen(ph.seen)}{ph.ip ? ` · ${ph.ip}` : ''}</small>
									</span>
									<button
										class="icon"
										aria-label="Remove {ph.name}"
										disabled={busy[ph.mac]}
										onclick={() => act(ph.mac, () => api.removePhone(p.uid, ph.mac))}
									>
										<X size={16} strokeWidth={2.4} />
									</button>
								</li>
							{/each}
						</ul>
					{/if}

					<div class="actions">
						{#if onPhone && !thisPhoneMarked}
							<Button
								size="sm"
								variant="primary"
								disabled={busy[p.uid]}
								onclick={() => act(p.uid, () => api.addPhone(p.uid, { this_phone: true }))}
							>
								This is my phone
							</Button>
						{/if}
						<Button size="sm" onclick={() => (picking = p)}>Add a phone</Button>
					</div>
				</li>
			{/each}
		</ul>

		{#if adding || !people.list.length}
			<form class="add" onsubmit={addPerson}>
				<input
					bind:value={newName}
					placeholder="Name, e.g. Dana"
					aria-label="Name"
					maxlength="40"
					bind:this={nameInput}
				/>
				<Button type="submit" variant="primary" disabled={!newName.trim() || busy.new}>Add</Button>
				{#if people.list.length}
					<Button type="button" variant="ghost" onclick={() => ((adding = false), (newName = ''))}>Cancel</Button>
				{/if}
			</form>
		{:else}
			<div>
				<Button
					onclick={async () => {
						adding = true;
						await tick();
						nameInput?.focus();
					}}><UserPlus size={16} strokeWidth={2.2} /> Add a person</Button
				>
			</div>
		{/if}
		<p class="hint">
			A phone is known by its Wi-Fi address. If a phone uses a <em>rotating</em> private address for your Wi-Fi, set it
			to
			<em>fixed</em> (iPhone) or <em>per-network</em> (Android), or Control loses track of it.
		</p>
	{/if}
</section>

{#if picking}
	{@const person = picking}
	<Sheet label="Add a phone for {person.name}" onclose={() => (picking = null)}>
		<PhonePicker
			{person}
			onpick={(phone) =>
				act(person.uid, async () => {
					await api.addPhone(person.uid, phone);
					picking = null;
				})}
			onclose={() => (picking = null)}
		/>
	</Sheet>
{/if}

{#if deleting}
	{@const person = deleting}
	<ConfirmDialog
		title="Remove {person.name}?"
		detail="Automations stop reacting to them arriving or leaving; the parts that name them are removed."
		confirmLabel="Remove"
		cancelLabel="Keep"
		onconfirm={() => {
			deleting = null;
			act(person.uid, () => api.deletePerson(person.uid));
		}}
		oncancel={() => (deleting = null)}
	/>
{/if}

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
	ul {
		display: flex;
		flex-direction: column;
		margin: 0;
		padding: 0;
		list-style: none;
	}
	.people {
		gap: var(--s-3);
	}
	.person {
		display: flex;
		flex-direction: column;
		gap: var(--s-2);
		padding: var(--s-4);
		border-radius: var(--r-lg);
		background: var(--surface);
		box-shadow: var(--shadow-1);
	}
	.top {
		display: flex;
		align-items: center;
		gap: var(--s-2);
	}
	.dot {
		flex: none;
		inline-size: 10px;
		block-size: 10px;
		border-radius: var(--r-pill);
		background: var(--text-3);
		transition: background var(--dur) var(--ease);
	}
	.dot.home {
		background: var(--accent);
	}
	.dot.unknown {
		background: transparent;
		box-shadow: inset 0 0 0 2px var(--text-3);
	}
	.name {
		flex: 1;
		min-inline-size: 0;
		padding: var(--s-1) var(--s-2);
		border: 1px solid transparent;
		border-radius: var(--r-sm);
		background: transparent;
		font-size: var(--fs-md);
		font-weight: var(--fw-bold);
	}
	.name:hover,
	.name:focus {
		border-color: var(--border);
		background: var(--surface-2);
		outline: none;
	}
	.state {
		padding-inline-start: calc(10px + var(--s-2) + var(--s-2));
		color: var(--text-2);
		font-size: var(--fs-sm);
	}
	.state.home {
		color: var(--accent-ink);
		font-weight: var(--fw-medium);
	}
	.phones {
		gap: var(--s-1);
	}
	.phones li {
		display: flex;
		align-items: center;
		gap: var(--s-3);
		padding: var(--s-2) var(--s-3);
		border-radius: var(--r-sm);
		background: var(--surface-2);
		color: var(--text-2);
	}
	.phone {
		flex: 1;
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		column-gap: var(--s-2);
		min-inline-size: 0;
		color: var(--text);
		font-weight: var(--fw-medium);
	}
	.phone small {
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
	.icon {
		flex: none;
		display: grid;
		place-items: center;
		inline-size: 32px;
		block-size: 32px;
		border: 0;
		border-radius: var(--r-pill);
		background: transparent;
		color: var(--text-3);
	}
	.icon:hover {
		background: var(--surface-2);
		color: var(--text);
	}
	.actions {
		display: flex;
		flex-wrap: wrap;
		gap: var(--s-2);
	}
	.add {
		display: flex;
		gap: var(--s-2);
	}
	.add input {
		flex: 1;
		min-inline-size: 0;
		min-block-size: 44px;
		padding-inline: var(--s-3);
		border-radius: var(--r-md);
		border: 1px solid var(--border);
		background: var(--surface-2);
		font-size: var(--fs-md);
	}
	.add input:focus {
		border-color: var(--accent);
		outline: none;
	}
</style>
