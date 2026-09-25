<script lang="ts">
	import { theme, type ThemePreference } from '$lib/theme.svelte';
	import Segmented from '$lib/ui/Segmented.svelte';
	import PhoneAccessSettings from '$lib/access/PhoneAccessSettings.svelte';
	import DesktopSettings from '$lib/desktop/DesktopSettings.svelte';
	import AssistantSettings from '$lib/assistant/AssistantSettings.svelte';
</script>

<svelte:head><title>Settings · Control</title></svelte:head>

<main>
	<h1>Settings</h1>
	<section>
		<h2>Appearance</h2>
		<Segmented
			label="Theme"
			options={[
				{ value: 'system', label: 'System' },
				{ value: 'light', label: 'Light' },
				{ value: 'dark', label: 'Dark' }
			]}
			value={theme.preference}
			onchange={(v: ThemePreference) => {
				theme.set(v);
				theme.apply();
			}}
		/>
	</section>
	<PhoneAccessSettings />
	<AssistantSettings />
	<DesktopSettings />
	<p class="later">Hubs & Bridges, rooms and more come later.</p>
</main>

<style>
	main {
		display: flex;
		flex-direction: column;
		gap: var(--s-6);
		max-inline-size: 480px;
		padding: var(--s-2) 0;
	}
	@media (min-width: 960px) {
		main {
			padding: var(--s-8);
		}
	}
	h1 {
		margin: 0;
		font-size: var(--fs-2xl);
	}
	h2 {
		margin: 0 0 var(--s-3);
		font-size: var(--fs-lg);
	}
	.later {
		color: var(--text-3);
	}
</style>
