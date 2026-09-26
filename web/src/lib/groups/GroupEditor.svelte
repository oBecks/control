<script lang="ts">
	import { Check, Trash2, X } from '@lucide/svelte';
	import type { Device, Group } from '$lib/api';
	import { iconFor, SECTIONS } from '$lib/present';
	import Button from '$lib/ui/Button.svelte';

	interface Props {
		/** The Group to edit; none to create one. */
		group?: Group;
		/** Every Device on Home, in the order to list them. */
		devices: Device[];
		/** Resolves true when the Group was saved. */
		onsave: (name: string, members: string[]) => Promise<boolean>;
		ondelete?: () => Promise<boolean>;
		onclose: () => void;
	}

	let { group, devices, onsave, ondelete, onclose }: Props = $props();

	// The form starts from the Group once; polling hands over fresh objects that mustn't reset it.
	const initial = (() => group)();
	let name = $state(initial?.name ?? '');
	let picked = $state<string[]>(initial ? [...initial.members] : []);
	let saving = $state(false);
	let confirmDelete = $state(false);

	const order = SECTIONS.map((s) => s.category);
	const listed = $derived([...devices].sort((a, b) => order.indexOf(a.category) - order.indexOf(b.category)));

	// What the Group's Device Controls will offer, so the choice isn't a surprise.
	const offers = $derived.by(() => {
		const kinds = new Set(devices.filter((d) => picked.includes(d.uid)).map((d) => d.control));
		if (!kinds.size) return '';
		if (kinds.size === 1 && kinds.has('light')) return 'Brightness and colour, like a light.';
		if (kinds.size === 1 && kinds.has('climate')) return 'Mode and temperature, like an AC.';
		return 'On and off.';
	});

	function toggle(uid: string) {
		picked = picked.includes(uid) ? picked.filter((u) => u !== uid) : [...picked, uid];
	}

	async function save(e: SubmitEvent) {
		e.preventDefault();
		saving = true;
		if (await onsave(name.trim(), picked)) onclose();
		saving = false;
	}

	async function remove() {
		saving = true;
		if (await ondelete?.()) onclose();
		saving = false;
	}
</script>

<form onsubmit={save}>
	<div class="head">
		<h2>{group ? 'Edit group' : 'New group'}</h2>
		<button type="button" class="close" aria-label="Close" onclick={onclose}><X size={18} strokeWidth={2.4} /></button>
	</div>

	<label class="field">
		<span>Name</span>
		<input bind:value={name} placeholder="e.g. Living room lights" maxlength="40" required />
	</label>

	<fieldset>
		<legend>Devices</legend>
		<p class="hint">The Group's Tile turns them all off when any is on, otherwise all on.</p>
		<ul>
			{#each listed as d (d.uid)}
				{@const Icon = iconFor(d)}
				{@const checked = picked.includes(d.uid)}
				<li>
					<label class="pick" class:checked class:disabled={!!d.group_problem}>
						<input type="checkbox" {checked} disabled={!!d.group_problem && !checked} onchange={() => toggle(d.uid)} />
						<span class="badge" aria-hidden="true"><Icon size={16} strokeWidth={2.2} /></span>
						<span class="text">
							<span class="dev">{d.name}</span>
							{#if d.group_problem}<span class="why">Can't join: {d.group_problem}</span>{/if}
						</span>
						<span class="box" aria-hidden="true"
							>{#if checked}<Check size={14} strokeWidth={3} />{/if}</span
						>
					</label>
				</li>
			{/each}
		</ul>
	</fieldset>

	{#if offers}<p class="offers">Its controls: {offers}</p>{/if}

	<div class="actions">
		<Button type="submit" variant="primary" disabled={saving || !name.trim() || !picked.length}>
			{group ? 'Save' : 'Create group'}
		</Button>
		<Button type="button" variant="ghost" onclick={onclose}>Cancel</Button>
	</div>

	{#if group && ondelete}
		<div class="danger">
			{#if confirmDelete}
				<p>Delete {group.name}? Its devices stay as they are.</p>
				<div class="actions">
					<Button type="button" variant="secondary" disabled={saving} onclick={remove}>
						<Trash2 size={16} strokeWidth={2.4} /> Delete
					</Button>
					<Button type="button" variant="ghost" onclick={() => (confirmDelete = false)}>Keep it</Button>
				</div>
			{:else}
				<Button type="button" variant="ghost" size="sm" onclick={() => (confirmDelete = true)}>
					<Trash2 size={15} strokeWidth={2.4} /> Delete group
				</Button>
			{/if}
		</div>
	{/if}
</form>

<style>
	form {
		display: flex;
		flex-direction: column;
		gap: var(--s-5);
	}
	.head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--s-3);
	}
	h2 {
		margin: 0;
		font-size: var(--fs-xl);
		font-weight: var(--fw-bold);
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
	.field {
		display: flex;
		flex-direction: column;
		gap: var(--s-2);
		font-weight: var(--fw-medium);
	}
	.field input {
		min-block-size: 44px;
		padding-inline: var(--s-3);
		border-radius: var(--r-md);
		border: 1px solid var(--border);
		background: var(--surface-2);
		font-size: var(--fs-md);
	}
	.field input:focus {
		border-color: var(--accent);
		outline: none;
	}
	fieldset {
		margin: 0;
		padding: 0;
		border: 0;
	}
	legend {
		padding: 0;
		font-weight: var(--fw-medium);
	}
	.hint,
	.offers {
		margin: var(--s-1) 0 var(--s-3);
		font-size: var(--fs-sm);
		color: var(--text-2);
	}
	.offers {
		margin: 0;
	}
	ul {
		display: flex;
		flex-direction: column;
		gap: var(--s-1);
		margin: 0;
		padding: 0;
		list-style: none;
	}
	.pick {
		position: relative;
		display: flex;
		align-items: center;
		gap: var(--s-3);
		padding: var(--s-2);
		border-radius: var(--r-md);
		cursor: pointer;
		transition: background-color var(--dur-fast) var(--ease);
	}
	.pick:hover:not(.disabled) {
		background: var(--surface-2);
	}
	.pick.disabled:not(.checked) {
		cursor: not-allowed;
	}
	.pick.disabled:not(.checked) .badge,
	.pick.disabled:not(.checked) .dev {
		opacity: 0.5;
	}
	/* The real checkbox stays for keyboards and screen readers; .box draws it. */
	.pick input {
		position: absolute;
		opacity: 0;
		pointer-events: none;
	}
	.pick:has(input:focus-visible) {
		outline: 2px solid var(--accent);
		outline-offset: 1px;
	}
	.badge {
		display: grid;
		place-items: center;
		flex-shrink: 0;
		inline-size: 32px;
		block-size: 32px;
		border-radius: var(--r-pill);
		background: var(--surface-2);
		color: var(--text-2);
	}
	.text {
		display: flex;
		flex-direction: column;
		flex: 1;
		min-inline-size: 0;
	}
	.dev {
		overflow: hidden;
		font-weight: var(--fw-medium);
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.why {
		font-size: var(--fs-xs);
		color: var(--text-3);
	}
	.box {
		display: grid;
		place-items: center;
		flex-shrink: 0;
		inline-size: 22px;
		block-size: 22px;
		border-radius: 6px;
		border: 2px solid var(--border);
		background: var(--surface);
		color: var(--on-accent);
		transition:
			background-color var(--dur-fast) var(--ease),
			border-color var(--dur-fast) var(--ease);
	}
	.checked .box {
		border-color: var(--accent);
		background: var(--accent);
	}
	.actions {
		display: flex;
		flex-wrap: wrap;
		gap: var(--s-2);
	}
	.danger {
		display: flex;
		flex-direction: column;
		align-items: flex-start;
		gap: var(--s-3);
		padding-block-start: var(--s-4);
		border-block-start: 1px solid var(--border);
	}
	.danger p {
		margin: 0;
		color: var(--text-2);
	}
	.danger :global(.btn) {
		color: var(--danger);
	}
</style>
