<script lang="ts">
	// The Tile of a Device or Group, by uid, with its live state. Used by Home and Dashboards.
	import { home } from '$lib/home.svelte';
	import { glowOf, groupGlow, groupIcon, groupStatus, iconFor, isOn, statusFor } from '$lib/present';
	import Tile from '$lib/ui/Tile.svelte';

	interface Props {
		uid: string;
		small?: boolean;
		selected?: boolean;
		/** Arranging a Dashboard: the Tile shows but doesn't toggle or open. */
		inert?: boolean;
		onopen?: (uid: string) => void;
	}

	let { uid, small = false, selected = false, inert = false, onopen }: Props = $props();

	const group = $derived(home.groups.find((g) => g.uid === uid));
	const device = $derived(group ? undefined : home.controllable.find((d) => d.uid === uid));
</script>

{#if group}
	{@const st = home.groupStates[group.uid]}
	<Tile
		name={group.name}
		status={groupStatus(st)}
		icon={groupIcon(group, st)}
		on={!!st?.state.on}
		glow={groupGlow(st)}
		offline={home.isGroupOffline(group)}
		assumed={!!st?.assumed}
		{small}
		{selected}
		{inert}
		ontoggle={() => home.toggleGroup(group.uid)}
		onopen={() => onopen?.(group.uid)}
	/>
{:else if device}
	{@const st = home.states[device.uid]}
	<Tile
		name={device.name}
		status={statusFor(st)}
		icon={iconFor(device, st)}
		on={isOn(st)}
		glow={glowOf(device, st)}
		pulse={home.pulses[device.uid] ?? 0}
		offline={home.isOffline(device)}
		assumed={device.kind === 'remote'}
		isNew={device.is_new}
		{small}
		{selected}
		{inert}
		ontoggle={() => home.toggle(device.uid)}
		onopen={() => onopen?.(device.uid)}
	/>
{/if}
