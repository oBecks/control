<script lang="ts">
	// One Automation's builder and history ("new" makes one).
	import { page } from '$app/state';
	import AutomationBuilder from '$lib/automations/AutomationBuilder.svelte';
</script>

{#key page.params.uid}
	<AutomationBuilder uid={page.params.uid ?? 'new'} />
{/key}
