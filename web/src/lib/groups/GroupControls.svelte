<script lang="ts">
	import { ChevronRight, Info, Pencil, WifiOff, X } from '@lucide/svelte';
	import type { Component } from 'svelte';
	import type { Group, GroupState } from '$lib/api';
	import ClimateControls from '$lib/controls/ClimateControls.svelte';
	import LightControls from '$lib/controls/LightControls.svelte';
	import PlugControls from '$lib/controls/PlugControls.svelte';
	import type { StateChange } from '$lib/types';

	export interface MemberRow {
		uid: string;
		name: string;
		status: string;
		icon: Component;
		on: boolean;
		offline: boolean;
	}

	interface Props {
		group: Group;
		value?: GroupState;
		members: MemberRow[];
		offline: boolean;
		onchange: (change: StateChange) => void;
		onclose: () => void;
		onedit: () => void;
		/** Open one member's own Device Controls. */
		onopenmember: (uid: string) => void;
	}

	let { group, value, members, offline, onchange, onclose, onedit, onopenmember }: Props = $props();

	const subtitle = $derived(
		[
			`Group · ${members.length} device${members.length === 1 ? '' : 's'}`,
			group.made_by === 'assistant' && 'Made by the Assistant'
		]
			.filter(Boolean)
			.join(' · ')
	);
</script>

<div class="head">
	<div class="name">
		<h2>
			{group.name}
			<button class="edit" aria-label="Edit {group.name}" onclick={onedit}
				><Pencil size={15} strokeWidth={2.4} /></button
			>
		</h2>
		<p>{subtitle}</p>
	</div>
	<button class="close" aria-label="Close" onclick={onclose}><X size={18} strokeWidth={2.4} /></button>
</div>

<div class="body">
	{#if offline}
		<p class="note"><b>None of its devices are answering.</b> Open one below to look for it again.</p>
	{:else if !value}
		<p class="tip">Loading…</p>
	{:else if value.control === 'light'}
		{#key group.uid}<LightControls features={value.features} value={value.state} {onchange} />{/key}
	{:else if value.control === 'climate'}
		<ClimateControls features={value.features} value={value.state} assumed {onchange} />
	{:else}
		<PlugControls value={value.state} {onchange} />
		{#if members.length > 1}
			<p class="note">
				<Info size={16} strokeWidth={2.3} />
				<span>On and off only: that's all its devices have in common.</span>
			</p>
		{/if}
	{/if}

	<section>
		<h3>Devices</h3>
		<ul>
			{#each members as m (m.uid)}
				{@const Icon = m.icon}
				<li>
					<button class="member" class:on={m.on && !m.offline} onclick={() => onopenmember(m.uid)}>
						<span class="badge" aria-hidden="true">
							{#if m.offline}<WifiOff size={16} strokeWidth={2.2} />{:else}<Icon size={16} strokeWidth={2.2} />{/if}
						</span>
						<span class="text">
							<span class="member-name">{m.name}</span>
							<span class="status">{m.offline ? 'Offline' : m.status}</span>
						</span>
						<ChevronRight size={16} strokeWidth={2.4} />
					</button>
				</li>
			{/each}
		</ul>
	</section>
</div>

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
	.edit,
	.close {
		display: grid;
		place-items: center;
		flex-shrink: 0;
		border: 0;
		border-radius: var(--r-pill);
	}
	.edit {
		inline-size: 28px;
		block-size: 28px;
		background: transparent;
		color: var(--text-3);
	}
	.edit:hover {
		background: var(--surface-2);
		color: var(--text);
	}
	.close {
		inline-size: 32px;
		block-size: 32px;
		background: var(--surface-2);
		color: var(--text-2);
	}
	.body {
		display: flex;
		flex-direction: column;
		gap: var(--s-5);
	}
	.note {
		display: flex;
		gap: var(--s-2);
		margin: 0;
		padding: var(--s-3);
		border-radius: var(--r-md);
		background: var(--surface-2);
		color: var(--text-2);
		font-size: var(--fs-sm);
	}
	.note :global(svg) {
		flex-shrink: 0;
		margin-block-start: 2px;
	}
	.tip {
		margin: 0;
		font-size: var(--fs-sm);
		color: var(--text-2);
	}
	h3 {
		margin: 0 0 var(--s-2);
		font-size: var(--fs-md);
		font-weight: var(--fw-bold);
	}
	ul {
		display: flex;
		flex-direction: column;
		gap: var(--s-1);
		margin: 0;
		padding: 0;
		list-style: none;
	}
	.member {
		display: flex;
		align-items: center;
		gap: var(--s-3);
		inline-size: 100%;
		padding: var(--s-2);
		border: 0;
		border-radius: var(--r-md);
		background: transparent;
		color: var(--text-3);
		text-align: start;
		transition: background-color var(--dur-fast) var(--ease);
	}
	.member:hover {
		background: var(--surface-2);
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
	.member.on .badge {
		background: color-mix(in oklab, var(--accent) 35%, var(--surface));
		color: var(--text);
	}
	.text {
		display: flex;
		flex-direction: column;
		flex: 1;
		min-inline-size: 0;
	}
	.member-name {
		overflow: hidden;
		color: var(--text);
		font-weight: var(--fw-medium);
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.status {
		font-size: var(--fs-sm);
		color: var(--text-2);
	}
	:global([dir='rtl']) .member > :global(svg:last-child) {
		transform: scaleX(-1);
	}
</style>
