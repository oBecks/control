<script lang="ts">
	// Settings → Desktop app (ADR 0004): Start with Windows and update notices. Only on the computer
	// running the Desktop App; under `control serve` the Engine reports no app and this stays hidden.
	import { Download } from '@lucide/svelte';
	import { api, type DesktopApp } from '$lib/api';
	import { home } from '$lib/home.svelte';
	import Segmented from '$lib/ui/Segmented.svelte';

	let status = $state<DesktopApp | null>(null);
	let busy = $state(false);

	$effect(() => {
		api.desktop().then(
			(s) => (status = s),
			() => {} // the layout already tells the user when the Engine is unreachable
		);
	});

	async function setStartWithWindows(on: boolean) {
		busy = true;
		try {
			status = await api.setStartWithWindows(on);
		} catch (e) {
			home.notify(e instanceof Error ? e.message : String(e));
		} finally {
			busy = false;
		}
	}
</script>

{#if status?.app && status.can_change}
	<section>
		<h2>Desktop app</h2>

		{#if status.update}
			<!-- eslint-disable-next-line svelte/no-navigation-without-resolve -- the installer on GitHub, not a page of the app -->
			<a class="update" href={status.update.url} target="_blank" rel="noreferrer">
				<Download size={18} strokeWidth={2.3} />
				<span>
					<strong>Control {status.update.version} is available</strong>
					<small>Download and run the installer. Your devices and settings stay.</small>
				</span>
			</a>
		{/if}

		<div class="row">
			<span>Start with Windows</span>
			<Segmented
				label="Start with Windows"
				options={[
					{ value: 'off', label: 'Off' },
					{ value: 'on', label: 'On' }
				]}
				value={status.start_with_windows ? 'on' : 'off'}
				onchange={(v) => !busy && setStartWithWindows(v === 'on')}
			/>
		</div>
		<p class="hint">
			Control starts in the tray when you sign in, so phones work without opening it. Closing this window keeps it
			running; <strong>Quit Control</strong> in the tray icon stops it.
		</p>
		<p class="hint">Version {status.version}</p>
	</section>
{/if}

<style>
	section {
		display: flex;
		flex-direction: column;
		gap: var(--s-3);
	}
	h2 {
		margin: 0;
		font-size: var(--fs-lg);
	}
	p {
		margin: 0;
	}
	.hint {
		color: var(--text-2);
		font-size: var(--fs-sm);
	}
	.row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--s-4);
	}
	.update {
		display: flex;
		align-items: center;
		gap: var(--s-3);
		padding: var(--s-3) var(--s-4);
		border-radius: var(--r-lg);
		border: 1px solid color-mix(in oklab, var(--accent) 45%, var(--border));
		background: color-mix(in oklab, var(--accent) 14%, var(--surface));
		color: var(--text);
		text-decoration: none;
	}
	.update span {
		display: flex;
		flex-direction: column;
	}
	.update small {
		color: var(--text-2);
		font-size: var(--fs-sm);
	}
</style>
