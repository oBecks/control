<script lang="ts">
	// Choose a Streamer's App Shortcuts: the chosen ones in order (move, remove), then known apps to
	// add, then any other app by its package name. Used by the setup and by Edit in Device Controls.
	import { ArrowDown, ArrowUp, Plus, X } from '@lucide/svelte';
	import type { Snippet } from 'svelte';
	import type { AppShortcut, CatalogueApp } from '$lib/types';
	import Button from '$lib/ui/Button.svelte';

	interface Props {
		catalogue: CatalogueApp[];
		value: AppShortcut[];
		/** The catalogue is what's really installed on the box. */
		installed?: boolean;
		/** Shown under the list while chosen apps have no link: offer adb (ADR 0008). */
		linkless?: Snippet<[string[]]>;
	}

	let { catalogue, value = $bindable(), installed = false, linkless }: Props = $props();

	const withoutLink = $derived(value.filter((a) => !a.link).map((a) => a.name));

	const offered = $derived(catalogue.filter((c) => !value.some((v) => v.app === c.app)));

	function move(i: number, by: number) {
		const next = [...value];
		[next[i], next[i + by]] = [next[i + by], next[i]];
		value = next;
	}

	const remove = (i: number) => (value = value.filter((_, j) => j !== i));
	const add = ({ name, app, link }: AppShortcut) => (value = [...value, link ? { name, app, link } : { name, app }]);

	let customName = $state('');
	let customApp = $state('');
	let customLink = $state('');
	let error = $state<string | null>(null);

	function addCustom(e: SubmitEvent) {
		e.preventDefault();
		const name = customName.trim();
		const app = customApp.trim();
		if (value.some((v) => v.app === app)) {
			error = 'That app is already in the list.';
			return;
		}
		const link = customLink.trim();
		add(link ? { name, app, link } : { name, app });
		customName = customApp = customLink = '';
		error = null;
	}
</script>

<div class="picker">
	{#if value.length}
		<ol class="chosen">
			{#each value as a, i (a.app)}
				<li>
					<span class="name">{a.name}</span>
					<button onclick={() => move(i, -1)} disabled={i === 0} aria-label="Move {a.name} up"
						><ArrowUp size={16} strokeWidth={2.4} /></button
					>
					<button onclick={() => move(i, 1)} disabled={i === value.length - 1} aria-label="Move {a.name} down"
						><ArrowDown size={16} strokeWidth={2.4} /></button
					>
					<button onclick={() => remove(i)} aria-label="Remove {a.name}"><X size={16} strokeWidth={2.4} /></button>
				</li>
			{/each}
		</ol>
	{:else}
		<p class="muted">No apps yet. Add the ones you open on it.</p>
	{/if}

	{#if linkless && withoutLink.length}{@render linkless(withoutLink)}{/if}

	{#if offered.length}
		<div>
			<h4>{installed ? 'Installed on this box' : 'Add'}</h4>
			<div class="chips">
				{#each offered as a (a.app)}
					<button class="chip" onclick={() => add(a)}><Plus size={14} strokeWidth={2.6} /> {a.name}</button>
				{/each}
			</div>
		</div>
	{/if}

	<details>
		<summary>Another app</summary>
		<form onsubmit={addCustom}>
			<input bind:value={customName} placeholder="Name, e.g. Kan 11" aria-label="App name" maxlength="30" />
			<input
				bind:value={customApp}
				placeholder="Package, e.g. com.example.tv"
				aria-label="Package name or link"
				autocomplete="off"
				spellcheck="false"
			/>
			<input
				bind:value={customLink}
				placeholder="Link, if you know it (optional)"
				aria-label="Link that opens it"
				autocomplete="off"
				spellcheck="false"
			/>
			<Button variant="secondary" size="sm" type="submit" disabled={!customName.trim() || !customApp.trim()}>Add</Button
			>
		</form>
		<p class="muted">
			The package name is in the app's Google Play address, after <code>id=</code>. Many boxes only open an app by its
			link (e.g. <code>stremio://</code>), so without one it may not open. Control can't see which apps are installed.
		</p>
		{#if error}<p class="error" role="alert">{error}</p>{/if}
	</details>
</div>

<style>
	.picker {
		display: flex;
		flex-direction: column;
		gap: var(--s-4);
	}
	p {
		margin: 0;
	}
	.muted {
		color: var(--text-2);
		font-size: var(--fs-sm);
	}
	.error {
		color: var(--danger);
		font-size: var(--fs-sm);
	}
	h4 {
		margin: 0 0 var(--s-2);
		font-size: var(--fs-sm);
		color: var(--text-2);
	}
	.chosen {
		margin: 0;
		padding: 0;
		list-style: none;
		border-radius: var(--r-md);
		border: 1px solid var(--border);
		overflow: hidden;
	}
	.chosen li {
		display: flex;
		align-items: center;
		gap: var(--s-1);
		padding: var(--s-1) var(--s-1) var(--s-1) var(--s-3);
		background: var(--surface-2);
	}
	.chosen li + li {
		border-block-start: 1px solid var(--border);
	}
	.name {
		flex: 1;
		min-inline-size: 0;
		font-weight: var(--fw-medium);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.chosen button {
		display: grid;
		place-items: center;
		inline-size: 36px;
		block-size: 36px;
		border: 0;
		border-radius: var(--r-pill);
		background: transparent;
		color: var(--text-2);
	}
	.chosen button:hover:not(:disabled) {
		background: var(--surface-3);
		color: var(--text);
	}
	.chosen button:disabled {
		opacity: 0.3;
	}
	.chips {
		display: flex;
		flex-wrap: wrap;
		gap: var(--s-2);
	}
	.chip {
		display: inline-flex;
		align-items: center;
		gap: var(--s-1);
		min-block-size: 36px;
		padding-inline: var(--s-3);
		border-radius: var(--r-pill);
		border: 1px dashed var(--border);
		background: transparent;
		font-size: var(--fs-sm);
		font-weight: var(--fw-medium);
	}
	.chip:hover {
		background: var(--surface-2);
	}
	summary {
		cursor: pointer;
		font-size: var(--fs-sm);
		font-weight: var(--fw-medium);
		color: var(--text-2);
	}
	details[open] {
		display: flex;
		flex-direction: column;
		gap: var(--s-3);
	}
	form {
		display: flex;
		flex-wrap: wrap;
		gap: var(--s-2);
		margin-block-start: var(--s-3);
	}
	input {
		flex: 1 1 160px;
		min-block-size: 40px;
		padding-inline: var(--s-3);
		border-radius: var(--r-md);
		border: 1px solid var(--border);
		background: var(--surface-2);
	}
	code {
		font-size: 0.95em;
	}
</style>
