<script lang="ts">
	import { Check, Pencil, Radar, X } from '@lucide/svelte';
	import type { Device, DeviceState } from './api';
	import ClimateControls from './controls/ClimateControls.svelte';
	import LightControls from './controls/LightControls.svelte';
	import PlugControls from './controls/PlugControls.svelte';
	import RemoteControls from './controls/RemoteControls.svelte';
	import type { StateChange } from './types';
	import Button from './ui/Button.svelte';

	interface Props {
		device: Device;
		value?: DeviceState;
		offline: boolean;
		scanning?: boolean;
		onchange: (change: StateChange) => void;
		onfindagain: () => void;
		onclose: () => void;
		/** Remote Devices: open Learning to teach more buttons. */
		onteach?: () => void;
		/** Resolves true when the rename was saved. */
		onrename?: (name: string) => Promise<boolean>;
	}

	let { device, value, offline, scanning = false, onchange, onfindagain, onclose, onteach, onrename }: Props = $props();

	let editing = $state(false);
	let draft = $state('');
	let saving = $state(false);

	function startEdit() {
		draft = device.name;
		editing = true;
	}

	async function save(e: SubmitEvent) {
		e.preventDefault();
		if (!onrename || draft.trim() === device.name) {
			editing = false;
			return;
		}
		saving = true;
		if (await onrename(draft)) editing = false;
		saving = false;
	}

	// Switching to another device abandons an unsaved rename.
	$effect(() => {
		const _uid = device.uid; // re-run on device change
		editing = false;
	});

	const subtitle = $derived(
		device.kind === 'remote'
			? 'Infrared · via your Broadlink'
			: [device.brand, device.model].filter(Boolean).join(' · ')
	);
</script>

<div class="head">
	<div class="name">
		{#if editing}
			<form onsubmit={save} class="rename">
				<!-- svelte-ignore a11y_autofocus -->
				<input
					bind:value={draft}
					aria-label="Device name"
					autofocus
					maxlength="40"
					onkeydown={(e) => e.key === 'Escape' && (editing = false)}
				/>
				<button type="submit" aria-label="Save name" disabled={saving}><Check size={18} strokeWidth={2.6} /></button>
			</form>
			{#if device.kind === 'network'}<p>Leave empty to use the device's own name.</p>{/if}
		{:else}
			<h2>
				{device.name}
				{#if onrename}
					<button class="edit" aria-label="Rename {device.name}" onclick={startEdit}
						><Pencil size={15} strokeWidth={2.4} /></button
					>
				{/if}
			</h2>
			<p>{subtitle}</p>
		{/if}
	</div>
	<button class="close" aria-label="Close" onclick={onclose}><X size={18} strokeWidth={2.4} /></button>
</div>

{#if offline}
	<div class="offline">
		<p>
			<b>{device.name} isn't answering.</b> It may be switched off at the wall, or it moved to a new address on your network.
		</p>
		<Button variant="primary" onclick={onfindagain} disabled={scanning}>
			<Radar size={16} strokeWidth={2.4} />
			{scanning ? 'Looking…' : 'Find again'}
		</Button>
		<p class="tip">Still missing? Make sure it has power and is on the same wifi as this computer.</p>
	</div>
{:else if !value}
	<p class="tip">Loading…</p>
{:else if value.control === 'light'}
	{#key device.uid}<LightControls features={value.features} value={value.state} {onchange} />{/key}
{:else if value.control === 'climate'}
	<ClimateControls features={value.features} value={value.state} assumed {onchange} />
{:else if value.control === 'remote'}
	<RemoteControls features={value.features} value={value.state} {onchange} {onteach} />
{:else}
	<PlugControls value={value.state} {onchange} />
{/if}

<style>
	.head {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: var(--s-3);
		margin-block-end: var(--s-5);
	}
	.name {
		flex: 1;
		min-inline-size: 0;
	}
	h2 {
		display: flex;
		align-items: center;
		gap: var(--s-2);
		margin: 0;
		font-size: var(--fs-xl);
		font-weight: var(--fw-bold);
		line-height: 1.2;
	}
	.head p {
		margin: 2px 0 0;
		font-size: var(--fs-sm);
		color: var(--text-2);
	}
	.edit {
		display: grid;
		place-items: center;
		inline-size: 28px;
		block-size: 28px;
		border: 0;
		border-radius: var(--r-pill);
		background: transparent;
		color: var(--text-3);
	}
	.edit:hover {
		background: var(--surface-2);
		color: var(--text);
	}
	.rename {
		display: flex;
		gap: var(--s-2);
	}
	.rename input {
		flex: 1;
		min-inline-size: 0;
		min-block-size: 40px;
		padding-inline: var(--s-3);
		border-radius: var(--r-md);
		border: 1px solid var(--accent);
		background: var(--surface-2);
		font-size: var(--fs-lg);
		font-weight: var(--fw-bold);
	}
	.rename button {
		display: grid;
		place-items: center;
		inline-size: 40px;
		border: 0;
		border-radius: var(--r-md);
		background: var(--accent);
		color: var(--on-accent);
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
	.offline {
		display: flex;
		flex-direction: column;
		gap: var(--s-4);
	}
	.offline p {
		margin: 0;
	}
	.tip {
		font-size: var(--fs-sm);
		color: var(--text-2);
	}
</style>
