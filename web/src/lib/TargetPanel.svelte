<script lang="ts">
	// The panel's content for a Device or Group: its controls and Hotkeys, the Group editor, the Hotkey editor.
	// Home and each Dashboard put it in their side panel (desktop) or a sheet (phone).
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import DeviceControls from '$lib/DeviceControls.svelte';
	import GroupControls from '$lib/groups/GroupControls.svelte';
	import GroupEditor from '$lib/groups/GroupEditor.svelte';
	import HotkeyEditor from '$lib/hotkeys/HotkeyEditor.svelte';
	import { hotkeys } from '$lib/hotkeys/hotkeys.svelte';
	import TargetHotkeys from '$lib/hotkeys/TargetHotkeys.svelte';
	import { home } from '$lib/home.svelte';
	import type { Panel } from '$lib/panel.svelte';
	import { iconFor, isOn, statusFor } from '$lib/present';

	let { panel }: { panel: Panel } = $props();

	const editing = $derived(panel.editor?.uid ? home.groups.find((g) => g.uid === panel.editor?.uid) : undefined);
	const editingHotkey = $derived(
		panel.hotkeyEditor?.uid ? hotkeys.list.find((h) => h.uid === panel.hotkeyEditor?.uid) : undefined
	);
	$effect(() => {
		hotkeys.load();
	});

	const memberRows = $derived(
		(panel.selectedGroup?.members ?? []).flatMap((uid) => {
			const d = home.devices.find((x) => x.uid === uid);
			if (!d) return [];
			const st = home.states[uid];
			return [
				{ uid, name: d.name, status: statusFor(st), icon: iconFor(d, st), on: isOn(st), offline: home.isOffline(d) }
			];
		})
	);

	async function saveGroup(name: string, members: string[]) {
		if (editing) {
			const same = members.join() === editing.members.join();
			return home.editGroup(editing.uid, { name, members: same ? undefined : members });
		}
		const g = await home.createGroup(name, members);
		if (g) panel.selectedUid = g.uid;
		return !!g;
	}

	async function deleteGroup() {
		const uid = panel.editor?.uid;
		if (!uid || !(await home.deleteGroup(uid))) return false;
		if (panel.selectedUid === uid) panel.selectedUid = null;
		return true;
	}
</script>

{#if panel.hotkeyEditor}
	{#key panel.hotkeyEditor.uid}
		<HotkeyEditor
			hotkey={editingHotkey}
			target={panel.hotkeyEditor.target}
			onclose={() => (panel.hotkeyEditor = null)}
		/>
	{/key}
{:else if panel.editor}
	{#key panel.editor.uid}
		<GroupEditor
			group={editing}
			devices={home.controllable}
			onsave={saveGroup}
			ondelete={editing ? deleteGroup : undefined}
			onclose={() => (panel.editor = null)}
		/>
	{/key}
{:else if panel.selectedGroup}
	{@const group = panel.selectedGroup}
	<GroupControls
		{group}
		value={home.groupStates[group.uid]}
		members={memberRows}
		offline={home.isGroupOffline(group)}
		onchange={(c) => home.changeGroup(group.uid, c)}
		onclose={() => panel.close()}
		onedit={() => panel.openEditor(group.uid)}
		onopenmember={(uid) => (panel.selectedUid = uid)}
	/>
	{@render targetHotkeys(group.uid)}
{:else if panel.selected}
	{@const device = panel.selected}
	<DeviceControls
		{device}
		value={home.states[device.uid]}
		offline={home.isOffline(device)}
		scanning={home.scanning}
		onchange={(c) => home.change(device.uid, c)}
		onfindagain={() => home.findAgain()}
		onclose={() => panel.close()}
		onteach={() => {
			home.teachTarget = device.uid;
			goto(resolve('/add'));
		}}
		onrename={(name) => home.rename(device.uid, name)}
		onapps={(apps) => home.setStreamer(device.uid, { apps })}
	/>
	{@render targetHotkeys(device.uid)}
{/if}

{#snippet targetHotkeys(target: string)}
	<TargetHotkeys
		uid={target}
		onadd={() => (panel.hotkeyEditor = { uid: null, target })}
		onopen={(uid) => (panel.hotkeyEditor = { uid, target })}
	/>
{/snippet}
