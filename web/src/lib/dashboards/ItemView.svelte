<script lang="ts">
	// A Dashboard item other than a Tile or Heading, with its Device's or Group's live state:
	// a Big Control, a Remote Pad, a Single Button or a Clock. Or a Run Button, with its Automation's.
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { automations } from '$lib/automations/automations.svelte';
	import { home } from '$lib/home.svelte';
	import type { DashboardItem, StateChange } from '$lib/types';
	import BrightnessBar from './items/BrightnessBar.svelte';
	import { buttonIcon } from './items/buttons';
	import Card from './items/Card.svelte';
	import ClimateCard from './items/ClimateCard.svelte';
	import Clock from './items/Clock.svelte';
	import ColourWheel from './items/ColourWheel.svelte';
	import RemotePad from './items/RemotePad.svelte';
	import SingleButton from './items/SingleButton.svelte';
	import { padLook } from './layout';

	type Shown = Exclude<DashboardItem, { kind: 'tile' | 'heading' }>;

	interface Props {
		item: Shown;
		/** Arranging: shown, but not usable. */
		inert?: boolean;
		onopen?: (uid: string) => void;
	}

	let { item, inert = false, onopen }: Props = $props();

	const uid = $derived('target' in item && item.kind !== 'run' ? item.target : '');
	const reading = $derived(uid ? home.stateOf(uid) : undefined);
	const name = $derived(uid ? (home.nameOf(uid) ?? '') : '');
	const offline = $derived.by(() => {
		const group = home.groups.find((g) => g.uid === uid);
		if (group) return home.isGroupOffline(group);
		const device = home.devices.find((d) => d.uid === uid);
		return !!device && home.isOffline(device);
	});
	const change = (c: StateChange) => home.changeTarget(uid, c);
	const open = $derived(onopen && uid ? () => onopen(uid) : undefined);
</script>

{#if item.kind === 'clock'}
	<Clock withDate={item.w >= 3} />
{:else if item.kind === 'run'}
	{@const target = item.target}
	{@const automation = automations.get(target)}
	<SingleButton
		label={automation?.name ?? (automations.loaded ? 'Gone' : '…')}
		device={automation?.running ? 'Running…' : 'Automation'}
		lit={!!automation?.running}
		missing={automations.loaded && !automation}
		{inert}
		onpress={() => automations.run(target)}
		onopen={() => goto(resolve('/(app)/automations/[uid]', { uid: target }))}
	/>
{:else if !reading}
	{@render unavailable(name ? '…' : 'Gone')}
{:else if item.kind === 'big_control'}
	{#if reading.control === 'light' && item.control === 'brightness'}
		<BrightnessBar {name} value={reading.state} {offline} {inert} onchange={change} onopen={open} />
	{:else if reading.control === 'light' && item.control === 'colour' && reading.features.color}
		<ColourWheel
			{name}
			features={reading.features}
			value={reading.state}
			{offline}
			{inert}
			onchange={change}
			onopen={open}
		/>
	{:else if reading.control === 'climate' && item.control === 'climate'}
		<ClimateCard
			{name}
			features={reading.features}
			value={reading.state}
			assumed={reading.assumed}
			{offline}
			{inert}
			onchange={change}
			onopen={open}
		/>
	{:else}
		{@render unavailable(item.control === 'colour' ? 'No colours' : 'Not here')}
	{/if}
{:else if reading.control === 'remote' || reading.control === 'streamer'}
	{#if item.kind === 'pad'}
		<RemotePad {name} {reading} look={padLook(item)} {offline} {inert} onchange={change} onopen={open} />
	{:else if item.app}
		{@const app = reading.control === 'streamer' ? reading.features.apps.find((a) => a.app === item.app) : undefined}
		<SingleButton
			label={app?.name ?? item.app}
			device={name}
			lit={reading.control === 'streamer' && reading.state.on && reading.state.app === item.app}
			missing={!app}
			{offline}
			{inert}
			onpress={() => app && change({ open_app: app.link ?? app.app })}
			onopen={open}
		/>
	{:else if item.button}
		{@const press = item.button}
		{@const button = reading.features.buttons.find((b) => b.name === press)}
		<SingleButton
			label={button?.label ?? press}
			device={name}
			icon={buttonIcon(press)}
			missing={!button}
			{offline}
			{inert}
			onpress={() => change({ press })}
			onopen={open}
		/>
	{/if}
{:else}
	{@render unavailable('Not here')}
{/if}

{#snippet unavailable(why: string)}
	<Card name={name || 'Removed'} status={why} {inert} onopen={open}><span></span></Card>
{/snippet}
