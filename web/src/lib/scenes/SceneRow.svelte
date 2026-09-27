<script lang="ts">
	// Home's Scene chips: tap sets one, holding or right-clicking opens it on the Scenes page.
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import Pencil from '@lucide/svelte/icons/pencil';
	import Plus from '@lucide/svelte/icons/plus';
	import { home } from '$lib/home.svelte';
	import SceneChip from '$lib/ui/SceneChip.svelte';
	import { sceneIcon } from './icons';

	// A Scene with nothing left in it waits on the Scenes page.
	const shown = $derived(home.scenes.filter((s) => s.parts.length));
</script>

<div class="row" role="group" aria-label="Scenes">
	{#each shown as s (s.uid)}
		<SceneChip
			label={s.name}
			icon={sceneIcon(s.icon)}
			active={home.isSceneActive(s)}
			title="Set {s.name}"
			onclick={() => home.setScene(s.uid)}
			onopen={() => goto(resolve('/(app)/scenes/[uid]', { uid: s.uid }))}
		/>
	{/each}
	{#if shown.length}
		<SceneChip label="Edit" icon={Pencil} dashed title="Scenes" onclick={() => goto(resolve('/scenes'))} />
	{:else}
		<SceneChip
			label="New scene"
			icon={Plus}
			dashed
			title="Set several devices in one tap, like Movie night"
			onclick={() => goto(resolve('/(app)/scenes/[uid]', { uid: 'new' }))}
		/>
	{/if}
</div>

<style>
	.row {
		display: flex;
		gap: var(--s-2);
		/* Scrolls sideways on a phone; the shadows get room to show. */
		overflow-x: auto;
		margin-inline: calc(-1 * var(--s-4));
		padding: var(--s-1) var(--s-4) var(--s-2);
		scrollbar-width: none;
	}
	.row::-webkit-scrollbar {
		display: none;
	}
	@media (min-width: 960px) {
		.row {
			flex-wrap: wrap;
			overflow: visible;
			margin-inline: 0;
			padding-inline: 0;
		}
	}
</style>
