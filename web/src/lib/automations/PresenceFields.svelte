<script lang="ts">
	// The Presence part of a When or an Only if (ADR 0014): a Person arriving or leaving (being home
	// or away), or the first arriving and the last leaving (someone or nobody home).
	import { resolve } from '$app/paths';
	import { people } from '$lib/people/people.svelte';
	import Segmented from '$lib/ui/Segmented.svelte';

	interface Props {
		kind: 'person' | 'home';
		/** A When (arrives, leaves) or an Only if (is home, is away). */
		part: 'trigger' | 'condition';
		/** The Person, for kind person. */
		target: string;
		/** Arrives / is home (a Person), or the first arrives / someone is home. */
		home: boolean;
	}

	let { kind, part, target = $bindable(), home = $bindable() }: Props = $props();

	$effect(() => {
		people.refresh();
	});

	const words = $derived(
		part === 'trigger'
			? kind === 'person'
				? ['Arrives home', 'Leaves home']
				: ['The first person arrives', 'The last person leaves']
			: kind === 'person'
				? ['Is home', 'Is away']
				: ['Someone is home', 'Nobody is home']
	);

	// Only People with a phone can be told home or away.
	$effect(() => {
		if (kind === 'person' && !people.tracked.some((p) => p.uid === target) && people.tracked.length)
			target = people.tracked[0].uid;
	});
</script>

{#if !people.loaded}
	<p class="hint">Loading the people who live here…</p>
{:else if !people.tracked.length}
	<p class="hint">
		First add the people who live here and mark their phones, in
		<a href={resolve('/settings')}>Settings → People</a>.
	</p>
{:else}
	{#if kind === 'person'}
		<label class="field">
			<span>Who</span>
			<select bind:value={target} required>
				{#each people.tracked as p (p.uid)}<option value={p.uid}>{p.name}</option>{/each}
			</select>
		</label>
	{/if}
	<Segmented
		label={part === 'trigger' ? 'Arrives or leaves' : 'Home or away'}
		options={[
			{ value: 'home', label: words[0] },
			{ value: 'away', label: words[1] }
		]}
		value={home ? 'home' : 'away'}
		onchange={(v) => (home = v === 'home')}
	/>
	<p class="hint">
		{#if part === 'trigger'}
			Control sees phones on the home Wi-Fi: arriving shows within about a minute, and leaving once their phone has been
			gone for 10 minutes, so a sleeping phone doesn't count as leaving.
		{:else}
			Right after Control starts it may not know yet, and then this doesn't hold.
		{/if}
	</p>
{/if}
