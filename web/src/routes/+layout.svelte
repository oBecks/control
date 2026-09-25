<script lang="ts">
	import '@fontsource-variable/nunito';
	import '$lib/styles/tokens.css';
	import '$lib/styles/base.css';
	import favicon from '$lib/assets/favicon.svg';
	import { theme } from '$lib/theme.svelte';

	let { children } = $props();

	$effect(() => theme.apply());
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
	<title>Control</title>
</svelte:head>

{@render children()}
