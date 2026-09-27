<script lang="ts">
	// One Scene's page ("new" makes one).
	import { page } from '$app/state';
	import SceneEditor from '$lib/scenes/SceneEditor.svelte';
</script>

{#key page.params.uid}
	<SceneEditor uid={page.params.uid ?? 'new'} />
{/key}
