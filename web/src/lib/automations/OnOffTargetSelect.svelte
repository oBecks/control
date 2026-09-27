<script lang="ts">
	// A Device or Group whose on/off Control knows, Groups first.
	import type { PickTarget } from './targets';

	interface Props {
		value: string;
		targets: PickTarget[];
	}

	let { value = $bindable(), targets }: Props = $props();

	const groups = $derived(targets.filter((t) => t.group));
</script>

<select bind:value required>
	<option value="" disabled>Pick one</option>
	{#if groups.length}
		<optgroup label="Groups">
			{#each groups as t (t.uid)}<option value={t.uid}>{t.name}</option>{/each}
		</optgroup>
	{/if}
	<optgroup label="Devices">
		{#each targets.filter((t) => !t.group) as t (t.uid)}<option value={t.uid}>{t.name}</option>{/each}
	</optgroup>
</select>
