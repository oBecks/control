<script lang="ts">
	// Automations: every one, with its switch, its last Run, and Run (ADR 0006).
	import { resolve } from '$app/paths';
	import { ChevronRight, Play, Plus } from '@lucide/svelte';
	import { automations } from '$lib/automations/automations.svelte';
	import { OUTCOMES, when } from '$lib/automations/parts';
	import type { Automation } from '$lib/types';
	import Switch from '$lib/ui/Switch.svelte';

	$effect(() => automations.start());

	function status(a: Automation): { text: string; bad: boolean } {
		if (a.attention) return { text: a.attention, bad: true };
		if (a.running) return { text: 'Running now', bad: false };
		const last = a.last_run;
		const lastText = last ? `${OUTCOMES[last.outcome].label} ${when(last.started).toLowerCase()}` : '';
		const bad = !!last && OUTCOMES[last.outcome].tone === 'bad';
		if (a.enabled && a.next_run) return { text: `Next: ${when(a.next_run)}${last ? ` · Last: ${lastText}` : ''}`, bad };
		if (!a.triggers.length) return { text: `Runs when you press Run${last ? ` · Last: ${lastText}` : ''}`, bad };
		return { text: a.enabled ? lastText || 'On' : 'Off', bad };
	}
</script>

<svelte:head><title>Automations · Control</title></svelte:head>

<main>
	<header>
		<h1>Automations</h1>
		<a class="new" href={resolve('/(app)/automations/[uid]', { uid: 'new' })}>
			<Plus size={16} strokeWidth={2.4} /> New automation
		</a>
	</header>

	<p class="hint">
		Things Control does by itself: at a time or at sunset, or when a device changes, only if something's true, a few
		steps in order. They run while Control is running on the computer.
	</p>

	{#if !automations.loaded}
		<p class="hint">Loading…</p>
	{:else if automations.list.length}
		<ul>
			{#each automations.list as a (a.uid)}
				{@const s = status(a)}
				<li class:off={!a.enabled}>
					<a class="name" href={resolve('/(app)/automations/[uid]', { uid: a.uid })}>
						<b>{a.name}</b>
						<small class:bad={s.bad}>{s.text}</small>
						{#if a.made_by === 'assistant'}<small>Made by the Assistant</small>{/if}
					</a>
					<button
						class="icon"
						aria-label="Run {a.name} now"
						title="Run it now, whatever its Only if says"
						disabled={a.running}
						onclick={() => automations.run(a.uid)}
					>
						<Play size={16} strokeWidth={2.4} />
					</button>
					<Switch checked={a.enabled} label="{a.name} on" onchange={(on) => automations.setEnabled(a.uid, on)} />
					<a class="icon go" href={resolve('/(app)/automations/[uid]', { uid: a.uid })} aria-label="Open {a.name}">
						<ChevronRight size={16} strokeWidth={2.4} />
					</a>
				</li>
			{/each}
		</ul>
	{:else}
		<div class="empty">
			<p>
				No automations yet. Try "at sunset, turn on the living room lights", or ask the Assistant to make one for you.
			</p>
			<a class="new primary" href={resolve('/(app)/automations/[uid]', { uid: 'new' })}>
				<Plus size={16} strokeWidth={2.4} /> New automation
			</a>
		</div>
	{/if}
</main>

<style>
	main {
		display: flex;
		flex-direction: column;
		gap: var(--s-4);
		max-inline-size: 600px;
		padding: var(--s-2) 0;
	}
	@media (min-width: 960px) {
		main {
			padding: var(--s-8);
		}
	}
	header {
		display: flex;
		align-items: flex-end;
		justify-content: space-between;
		gap: var(--s-3);
	}
	h1 {
		margin: 0;
		font-size: var(--fs-2xl);
	}
	p {
		margin: 0;
	}
	.hint {
		color: var(--text-2);
	}
	.new {
		display: inline-flex;
		align-items: center;
		gap: var(--s-2);
		min-block-size: 34px;
		padding-inline: var(--s-4);
		border-radius: var(--r-pill);
		color: var(--text-2);
		font-size: var(--fs-sm);
		font-weight: var(--fw-medium);
		text-decoration: none;
		white-space: nowrap;
	}
	.new:hover {
		background: var(--surface-2);
		color: var(--text);
	}
	.new.primary {
		min-block-size: 44px;
		padding-inline: var(--s-5);
		background: var(--accent);
		color: var(--on-accent);
		font-size: var(--fs-md);
	}
	ul {
		display: flex;
		flex-direction: column;
		gap: var(--s-1);
		margin: 0;
		padding: 0;
		list-style: none;
	}
	li {
		display: flex;
		align-items: center;
		gap: var(--s-2);
		padding: var(--s-2);
		border-radius: var(--r-md);
		transition: background-color var(--dur-fast) var(--ease);
	}
	li:hover {
		background: var(--surface-2);
	}
	.name {
		display: flex;
		flex-direction: column;
		flex: 1;
		min-inline-size: 0;
		color: var(--text);
		text-decoration: none;
	}
	.name b {
		overflow: hidden;
		font-weight: var(--fw-medium);
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	li.off .name b {
		color: var(--text-2);
	}
	small {
		overflow: hidden;
		color: var(--text-2);
		font-size: var(--fs-xs);
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	small.bad {
		color: var(--danger);
	}
	.icon {
		display: grid;
		place-items: center;
		flex-shrink: 0;
		inline-size: 36px;
		block-size: 36px;
		border: 0;
		border-radius: var(--r-pill);
		background: transparent;
		color: var(--text-2);
	}
	.icon:hover:not(:disabled) {
		background: var(--surface-3);
		color: var(--text);
	}
	.icon:disabled {
		opacity: 0.4;
	}
	.go {
		color: var(--text-3);
	}
	:global([dir='rtl']) .go > :global(svg) {
		transform: scaleX(-1);
	}
	.empty {
		display: flex;
		flex-direction: column;
		align-items: flex-start;
		gap: var(--s-4);
		padding-block: var(--s-6);
	}
</style>
