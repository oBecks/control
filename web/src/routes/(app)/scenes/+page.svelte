<script lang="ts">
	// Scenes: every one, in the order Home's chips follow, with Set and the way into each (ADR 0013).
	import { resolve } from '$app/paths';
	import ChevronRight from '@lucide/svelte/icons/chevron-right';
	import GripVertical from '@lucide/svelte/icons/grip-vertical';
	import Plus from '@lucide/svelte/icons/plus';
	import { flip } from 'svelte/animate';
	import { MediaQuery } from 'svelte/reactivity';
	import { moveItem } from '$lib/dashboards/layout';
	import { reorder } from '$lib/dashboards/reorder';
	import { home } from '$lib/home.svelte';
	import { sceneIcon } from '$lib/scenes/icons';
	import type { Scene } from '$lib/types';
	import Button from '$lib/ui/Button.svelte';

	const reduceMotion = new MediaQuery('prefers-reduced-motion: reduce');

	/** The order while a row is being dragged. */
	let dragged = $state<Scene[] | null>(null);
	const list = $derived(dragged ?? home.scenes);

	const summary = (s: Scene) => s.parts.map((p) => `${p.target_name}: ${p.label}`).join(', ');
</script>

<svelte:head><title>Scenes · Control</title></svelte:head>

<main>
	<header>
		<h1>Scenes</h1>
		<a class="new" href={resolve('/(app)/scenes/[uid]', { uid: 'new' })}>
			<Plus size={16} strokeWidth={2.4} /> New scene
		</a>
	</header>

	<p class="hint">
		How several devices should be, set in one tap from Home: the lamp at 20%, the ceiling light off, the AC at 24°. A
		scene lights up while everything in it is that way.
	</p>

	{#if !home.loaded}
		<p class="hint">Loading…</p>
	{:else if list.length}
		<ul
			{@attach reorder(() => ({
				onmove: (from, to) => (dragged = moveItem(list, from, to)),
				onend: () => {
					if (dragged) home.orderScenes(dragged.map((s) => s.uid));
					dragged = null;
				}
			}))}
		>
			{#each list as s, i (s.uid)}
				{@const Icon = sceneIcon(s.icon)}
				{@const active = home.isSceneActive(s)}
				<li data-index={i} animate:flip={{ duration: reduceMotion.current ? 0 : 200 }}>
					{#if list.length > 1}
						<span class="handle" data-handle aria-hidden="true"><GripVertical size={16} strokeWidth={2.4} /></span>
					{/if}
					<span class="icon" class:active><Icon size={18} strokeWidth={2.2} /></span>
					<a class="name" href={resolve('/(app)/scenes/[uid]', { uid: s.uid })}>
						<b>{s.name}</b>
						{#if s.attention}
							<small class="bad">{s.attention}</small>
						{:else}
							<small>{active ? 'On now · ' : ''}{summary(s)}</small>
						{/if}
						{#if s.made_by === 'assistant'}<small>Made by the Assistant</small>{/if}
					</a>
					<Button
						variant="secondary"
						size="sm"
						disabled={!s.parts.length || !!home.settingScene}
						onclick={() => home.setScene(s.uid)}>Set</Button
					>
					<a class="go" href={resolve('/(app)/scenes/[uid]', { uid: s.uid })} aria-label="Open {s.name}">
						<ChevronRight size={16} strokeWidth={2.4} />
					</a>
				</li>
			{/each}
		</ul>
	{:else}
		<div class="empty">
			<p>
				No scenes yet. Set the room up the way you like it, then save it as a scene, or ask the Assistant to make one.
			</p>
			<a class="new primary" href={resolve('/(app)/scenes/[uid]', { uid: 'new' })}>
				<Plus size={16} strokeWidth={2.4} /> New scene
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
		background: var(--bg);
		transition: background-color var(--dur-fast) var(--ease);
	}
	li:hover {
		background: var(--surface-2);
	}
	.handle {
		display: grid;
		place-items: center;
		inline-size: 24px;
		block-size: 40px;
		color: var(--text-3);
		cursor: grab;
		touch-action: none;
	}
	:global([data-dragging]) .handle {
		cursor: grabbing;
	}
	.icon {
		display: grid;
		place-items: center;
		flex-shrink: 0;
		inline-size: 36px;
		block-size: 36px;
		border-radius: var(--r-pill);
		background: var(--surface-2);
		color: var(--text-2);
		transition: background-color var(--dur) var(--ease);
	}
	.icon.active {
		background: var(--accent);
		color: var(--on-accent);
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
	.go {
		display: grid;
		place-items: center;
		flex-shrink: 0;
		inline-size: 32px;
		block-size: 36px;
		border-radius: var(--r-pill);
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
