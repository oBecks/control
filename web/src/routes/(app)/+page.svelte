<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { Plus, Radar } from '@lucide/svelte';
	import { MediaQuery } from 'svelte/reactivity';
	import DeviceControls from '$lib/DeviceControls.svelte';
	import GroupControls from '$lib/groups/GroupControls.svelte';
	import GroupEditor from '$lib/groups/GroupEditor.svelte';
	import { home } from '$lib/home.svelte';
	import {
		glowOf,
		greeting,
		groupGlow,
		groupIcon,
		groupStatus,
		iconFor,
		isOn,
		SECTIONS,
		statusFor
	} from '$lib/present';
	import Banner from '$lib/ui/Banner.svelte';
	import Button from '$lib/ui/Button.svelte';
	import SectionHeader from '$lib/ui/SectionHeader.svelte';
	import Sheet from '$lib/ui/Sheet.svelte';
	import Tile from '$lib/ui/Tile.svelte';

	const desktop = new MediaQuery('min-width: 960px');

	/** A Device's or a Group's uid. */
	let selectedUid = $state<string | null>(null);
	const selected = $derived(home.controllable.find((d) => d.uid === selectedUid));
	const selectedGroup = $derived(home.groups.find((g) => g.uid === selectedUid));
	/** The Group editor, open on a Group (uid) or on a new one (null). */
	let editor = $state<{ uid: string | null } | null>(null);
	const editing = $derived(editor?.uid ? home.groups.find((g) => g.uid === editor?.uid) : undefined);
	const canGroup = $derived(home.controllable.filter((d) => !d.group_problem).length >= 2);

	const groupSummary = $derived.by(() => {
		const on = home.groups.filter((g) => !home.isGroupOffline(g) && home.groupStates[g.uid]?.state.on).length;
		return on ? `${on} on` : undefined;
	});

	const memberRows = $derived(
		(selectedGroup?.members ?? []).flatMap((uid) => {
			const d = home.devices.find((x) => x.uid === uid);
			if (!d) return [];
			const st = home.states[uid];
			return [
				{ uid, name: d.name, status: statusFor(st), icon: iconFor(d, st), on: isOn(st), offline: home.isOffline(d) }
			];
		})
	);

	function openEditor(uid: string | null) {
		editor = { uid };
	}

	async function saveGroup(name: string, members: string[]) {
		if (editing) {
			const same = members.join() === editing.members.join();
			return home.editGroup(editing.uid, { name, members: same ? undefined : members });
		}
		const g = await home.createGroup(name, members);
		if (g) selectedUid = g.uid;
		return !!g;
	}

	async function deleteGroup() {
		const uid = editor?.uid;
		if (!uid || !(await home.deleteGroup(uid))) return false;
		if (selectedUid === uid) selectedUid = null;
		return true;
	}

	function close() {
		editor = null;
		selectedUid = null;
	}

	const sections = $derived(
		SECTIONS.map((s) => {
			const devices = home.controllable.filter((d) => d.category === s.category);
			const on = devices.filter((d) => !home.isOffline(d) && isOn(home.states[d.uid])).length;
			return { ...s, devices, summary: on ? `${on} on` : undefined };
		}).filter((s) => s.devices.length)
	);

	// A Transmitter that nothing is set up behind yet: ask what it controls.
	const idleHub = $derived(
		home.devices.find(
			(h) => h.category === 'transmitter' && h.readiness === 'ready' && !home.devices.some((d) => d.via === h.uid)
		)
	);
</script>

<svelte:head><title>Home · Control</title></svelte:head>

<div class="home" class:with-panel={desktop.current}>
	<main>
		<header>
			<div>
				<span class="greet">{greeting()}</span>
				<h1>Home</h1>
			</div>
			{#if canGroup}
				<Button variant="ghost" size="sm" onclick={() => openEditor(null)}
					><Plus size={16} strokeWidth={2.4} /> New group</Button
				>
			{/if}
		</header>

		{#if idleHub}
			<Banner
				title="What does {idleHub.name} control?"
				detail="Tell Control about your AC, TV or fan to use them here"
				onclick={() => goto(resolve('/add'))}
			/>
		{/if}

		{#if home.newCount}
			<Banner
				title="{home.newCount} new device{home.newCount > 1 ? 's' : ''} found"
				detail="Tap to set {home.newCount > 1 ? 'them' : 'it'} up"
				onclick={() => goto(resolve('/add'))}
			/>
		{/if}

		{#if !home.loaded}
			<div class="grid" aria-busy="true">
				{#each Array(4) as _, i (i)}<div class="skeleton"></div>{/each}
			</div>
		{:else if !sections.length}
			<div class="empty">
				<h2>No devices yet</h2>
				<p>Scan your wifi to find lights, plugs and more.</p>
				<Button variant="primary" onclick={() => goto(resolve('/add'))}
					><Radar size={16} strokeWidth={2.4} /> Add devices</Button
				>
			</div>
		{:else}
			{#if home.groups.length}
				<section aria-label="Groups">
					<SectionHeader title="Groups" summary={groupSummary} />
					<div class="grid">
						{#each home.groups as g (g.uid)}
							{@const st = home.groupStates[g.uid]}
							<Tile
								name={g.name}
								status={groupStatus(st)}
								icon={groupIcon(g, st)}
								on={!!st?.state.on}
								glow={groupGlow(st)}
								offline={home.isGroupOffline(g)}
								assumed={!!st?.assumed}
								selected={desktop.current && g.uid === selectedUid && !editor}
								ontoggle={() => home.toggleGroup(g.uid)}
								onopen={() => {
									editor = null;
									selectedUid = g.uid;
								}}
							/>
						{/each}
					</div>
				</section>
			{/if}
			{#each sections as s (s.category)}
				<section>
					<SectionHeader title={s.title} summary={s.summary} />
					<div class="grid">
						{#each s.devices as d (d.uid)}
							{@const st = home.states[d.uid]}
							<Tile
								name={d.name}
								status={statusFor(st)}
								icon={iconFor(d, st)}
								on={isOn(st)}
								glow={glowOf(d, st)}
								pulse={home.pulses[d.uid] ?? 0}
								offline={home.isOffline(d)}
								assumed={d.kind === 'remote'}
								isNew={d.is_new}
								selected={desktop.current && d.uid === selectedUid && !editor}
								ontoggle={() => home.toggle(d.uid)}
								onopen={() => {
									editor = null;
									selectedUid = d.uid;
								}}
							/>
						{/each}
					</div>
				</section>
			{/each}
		{/if}
	</main>

	{#snippet panel()}
		{#if editor}
			{#key editor.uid}
				<GroupEditor
					group={editing}
					devices={home.controllable}
					onsave={saveGroup}
					ondelete={editing ? deleteGroup : undefined}
					onclose={() => (editor = null)}
				/>
			{/key}
		{:else if selectedGroup}
			<GroupControls
				group={selectedGroup}
				value={home.groupStates[selectedGroup.uid]}
				members={memberRows}
				offline={home.isGroupOffline(selectedGroup)}
				onchange={(c) => home.changeGroup(selectedGroup.uid, c)}
				onclose={close}
				onedit={() => openEditor(selectedGroup.uid)}
				onopenmember={(uid) => (selectedUid = uid)}
			/>
		{:else if selected}
			<DeviceControls
				device={selected}
				value={home.states[selected.uid]}
				offline={home.isOffline(selected)}
				scanning={home.scanning}
				onchange={(c) => home.change(selected.uid, c)}
				onfindagain={() => home.findAgain()}
				onclose={close}
				onteach={() => {
					home.teachTarget = selected.uid;
					goto(resolve('/add'));
				}}
				onrename={(name) => home.rename(selected.uid, name)}
			/>
		{/if}
	{/snippet}

	{#if desktop.current}
		<aside class="panel" aria-label="Device controls">
			{#if editor || selectedGroup || selected}
				{@render panel()}
			{:else}
				<p class="hint">Select a device's <b>›</b> to see all its controls here.</p>
			{/if}
		</aside>
	{:else if editor || selectedGroup || selected}
		<Sheet label={editor ? 'Group' : `${(selectedGroup ?? selected)?.name} controls`} onclose={close}>
			{@render panel()}
		</Sheet>
	{/if}
</div>

<style>
	main {
		display: flex;
		flex-direction: column;
		gap: var(--s-6);
		max-inline-size: 1100px;
	}
	header {
		display: flex;
		align-items: flex-end;
		justify-content: space-between;
		gap: var(--s-3);
	}
	header > div {
		display: flex;
		flex-direction: column;
	}
	.greet {
		font-size: var(--fs-sm);
		color: var(--text-2);
	}
	h1 {
		margin: 0;
		font-size: var(--fs-2xl);
		font-weight: var(--fw-bold);
		line-height: 1.1;
	}
	.grid {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: var(--s-3);
	}
	.skeleton {
		block-size: var(--tile-h);
		border-radius: var(--r-lg);
		background: var(--surface-2);
		animation: pulse 1.2s var(--ease) infinite alternate;
	}
	@keyframes pulse {
		to {
			opacity: 0.5;
		}
	}
	.empty {
		display: flex;
		flex-direction: column;
		align-items: flex-start;
		gap: var(--s-2);
		padding: var(--s-8) 0;
	}
	.empty h2 {
		margin: 0;
		font-size: var(--fs-xl);
	}
	.empty p {
		margin: 0 0 var(--s-3);
		color: var(--text-2);
	}

	@media (min-width: 560px) {
		.grid {
			grid-template-columns: repeat(auto-fill, minmax(var(--tile-min), 1fr));
		}
	}

	/* Desktop: grid + side panel that stays open */
	.with-panel {
		display: grid;
		grid-template-columns: minmax(0, 1fr) 360px;
		min-block-size: 100dvh;
	}
	.with-panel main {
		padding: var(--s-8);
	}
	.panel {
		position: sticky;
		inset-block-start: 0;
		block-size: 100dvh;
		overflow-y: auto;
		padding: var(--s-8) var(--s-6);
		border-inline-start: 1px solid var(--border);
		background: var(--surface);
	}
	.hint {
		margin: var(--s-10) 0 0;
		color: var(--text-3);
		text-align: center;
	}
</style>
