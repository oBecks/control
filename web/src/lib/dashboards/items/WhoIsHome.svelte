<script lang="ts">
	// Who's home (ADR 0014): each Person with a phone, lit while they're home. Presence changes on its
	// own, so it's read again every few seconds while it's on screen.
	import { resolve } from '$app/paths';
	import { people } from '$lib/people/people.svelte';

	interface Props {
		/** Arranging: shown, but not usable. */
		inert?: boolean;
	}

	let { inert = false }: Props = $props();

	$effect(() => people.watch());

	const shown = $derived(people.tracked);

	function state(home: boolean | null) {
		return home === true ? 'Home' : home === false ? 'Away' : 'Not known yet';
	}
</script>

<div class="who" class:inert aria-label="Who’s home">
	{#if people.loaded && !shown.length}
		<p class="empty">
			No one yet: add people and their phones in
			{#if inert}Settings{:else}<a href={resolve('/settings')}>Settings</a>{/if}.
		</p>
	{:else}
		<ul>
			{#each shown as p (p.uid)}
				<li class:home={p.home === true} class:unknown={p.home === null} title="{p.name}: {state(p.home)}">
					<span class="badge" aria-hidden="true">{p.name.slice(0, 1).toUpperCase()}</span>
					<span class="text">
						<span class="name">{p.name}</span>
						<span class="state">{state(p.home)}</span>
					</span>
				</li>
			{/each}
		</ul>
	{/if}
</div>

<style>
	.who {
		display: flex;
		align-items: center;
		min-inline-size: 0;
		overflow: hidden;
		padding: var(--s-2) var(--s-3);
		border-radius: var(--r-lg);
		background: var(--surface);
		border: 1px solid var(--border);
		container-type: size;
	}
	ul {
		display: flex;
		flex-wrap: wrap;
		align-content: center;
		gap: var(--s-2) var(--s-3);
		inline-size: 100%;
		margin: 0;
		padding: 0;
		list-style: none;
	}
	li {
		display: flex;
		align-items: center;
		gap: var(--s-2);
		min-inline-size: 0;
	}
	.badge {
		flex: none;
		display: grid;
		place-items: center;
		inline-size: 32px;
		block-size: 32px;
		border-radius: var(--r-pill);
		background: var(--surface-2);
		color: var(--text-3);
		font-weight: var(--fw-bold);
		transition:
			background var(--dur) var(--ease),
			color var(--dur) var(--ease);
	}
	li.home .badge {
		background: var(--accent);
		color: var(--on-accent);
	}
	li.unknown .badge {
		background: transparent;
		box-shadow: inset 0 0 0 2px var(--border);
	}
	.text {
		display: flex;
		flex-direction: column;
		min-inline-size: 0;
		line-height: 1.2;
	}
	.name {
		overflow: hidden;
		font-weight: var(--fw-medium);
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.state {
		color: var(--text-3);
		font-size: var(--fs-xs);
	}
	li.home .state {
		color: var(--accent-ink);
	}
	/* One column wide, or a single row: only the lit initials. */
	@container (max-width: 110px) or (max-height: 56px) {
		.text {
			display: none;
		}
	}
	.empty {
		margin: 0;
		color: var(--text-2);
		font-size: var(--fs-sm);
	}
	.inert {
		pointer-events: none;
	}
</style>
