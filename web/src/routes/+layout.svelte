<script lang="ts">
	import '@fontsource-variable/nunito';
	import '$lib/styles/tokens.css';
	import '$lib/styles/base.css';
	import { theme } from '$lib/theme.svelte';

	let { children } = $props();

	$effect(() => theme.apply());
</script>

<svelte:head>
	<title>Control</title>
</svelte:head>

{@render children()}
