<script lang="ts">
	// Records keys by pressing them: a Hotkey's, or a sequence's second key. While recording, the
	// Desktop App lets go of every Hotkey, so pressing an existing one lands here instead of firing.
	// Keys another app holds never reach the Window: those can be picked from a list instead.
	import { api } from '$lib/api';
	import type { PickableKey } from '$lib/types';
	import Button from '$lib/ui/Button.svelte';
	import { keyCaps, keysOf, modifiersOf } from './keys';

	interface Props {
		/** The keys to show, as Control writes them, e.g. "Ctrl+Alt+L". */
		keys: string;
		/** Keys just pressed or picked, e.g. "Ctrl+Alt+KeyL"; the Engine writes them properly. */
		onrecord: (keys: string) => void;
		/** A sequence's second key: a plain key is fine, so the list offers one. */
		second?: boolean;
	}

	let { keys, onrecord, second = false }: Props = $props();

	const MODIFIERS = ['Ctrl', 'Alt', 'Shift', 'Win'];
	const GROUPS: [PickableKey['group'], string][] = [
		['spare', 'Spare keys'],
		['media', 'Media keys'],
		['function', 'F1–F12'],
		['letters', 'Letters and digits'],
		['numpad', 'Number pad'],
		['other', 'Other keys']
	];

	let recording = $state(false);
	let held = $state<string[]>([]);
	let picking = $state(false);
	let pickable = $state<PickableKey[]>([]);
	// The list starts from a usual choice: a digit for a sequence's second key.
	const first = (() => (second ? { mods: [], key: 'Digit1' } : { mods: ['Ctrl', 'Alt'], key: 'F13' }))();
	let pickMods = $state<string[]>(first.mods);
	let pickKey = $state(first.key);
	let timer: ReturnType<typeof setTimeout> | undefined;

	function start() {
		recording = true;
		held = [];
		api.recordingKeys(true).catch(() => {});
		timer = setTimeout(stop, 50_000); // the Engine gives the keys back after a minute anyway
	}

	function stop() {
		if (!recording) return;
		recording = false;
		clearTimeout(timer);
		api.recordingKeys(false).catch(() => {});
	}

	// Leaving the editor mid-recording gives the Hotkeys back.
	$effect(() => stop);

	function onkeydown(e: KeyboardEvent) {
		if (!recording) return;
		e.preventDefault();
		e.stopPropagation();
		const mods = modifiersOf(e);
		if (e.code === 'Escape' && !mods.length) return stop();
		held = mods;
		const pressed = keysOf(e);
		if (!pressed) return;
		stop();
		onrecord(pressed);
	}

	function onkeyup(e: KeyboardEvent) {
		if (recording) held = modifiersOf(e);
	}

	async function openPicker() {
		picking = !picking;
		if (picking && !pickable.length) pickable = await api.pickableKeys().catch(() => []);
	}

	function togglePickMod(m: string) {
		pickMods = pickMods.includes(m) ? pickMods.filter((x) => x !== m) : [...pickMods, m];
	}

	function usePicked() {
		const mods = MODIFIERS.filter((m) => pickMods.includes(m));
		onrecord([...mods, pickKey].join('+'));
	}
</script>

<svelte:window onkeydowncapture={onkeydown} onkeyupcapture={onkeyup} onblur={stop} />

<div class="recorder">
	<div class="keys" class:recording aria-live="polite">
		{#if recording}
			<span class="prompt">
				{held.length ? `${held.join(' + ')} + …` : second ? 'Press the second key…' : 'Press the keys…'}
			</span>
		{:else if keys}
			<span class="caps">
				{#each keyCaps(keys) as k, i (i)}<kbd>{k}</kbd>{/each}
			</span>
		{:else}
			<span class="prompt">No keys yet</span>
		{/if}
		<Button type="button" size="sm" variant={recording ? 'ghost' : 'secondary'} onclick={recording ? stop : start}>
			{recording ? 'Cancel' : keys ? 'Change' : 'Record keys'}
		</Button>
	</div>

	<button type="button" class="link" onclick={openPicker} aria-expanded={picking}>
		{picking ? 'Hide the key list' : 'Key not showing up? Pick it from a list'}
	</button>

	{#if picking}
		<div class="picker">
			<div class="mods" role="group" aria-label="Modifiers">
				{#each MODIFIERS as m (m)}
					<button
						type="button"
						class="mod"
						aria-pressed={pickMods.includes(m)}
						class:on={pickMods.includes(m)}
						onclick={() => togglePickMod(m)}>{m}</button
					>
				{/each}
			</div>
			<select bind:value={pickKey} aria-label="Key">
				{#each GROUPS as [group, label] (group)}
					<optgroup {label}>
						{#each pickable.filter((k) => k.group === group) as k (k.code)}
							<option value={k.code}>{k.label}</option>
						{/each}
					</optgroup>
				{/each}
			</select>
			<Button type="button" size="sm" onclick={usePicked}>Use these keys</Button>
		</div>
	{/if}
</div>

<style>
	.recorder {
		display: flex;
		flex-direction: column;
		gap: var(--s-2);
	}
	.keys {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--s-3);
		min-block-size: 56px;
		padding: var(--s-2) var(--s-2) var(--s-2) var(--s-3);
		border-radius: var(--r-md);
		border: 1px solid var(--border);
		background: var(--surface-2);
		transition: border-color var(--dur-fast) var(--ease);
	}
	.keys.recording {
		border-color: var(--accent);
	}
	.prompt {
		color: var(--text-2);
	}
	.recording .prompt {
		color: var(--text);
		font-weight: var(--fw-medium);
	}
	.caps {
		display: flex;
		flex-wrap: wrap;
		gap: var(--s-1);
	}
	kbd {
		min-inline-size: 28px;
		padding: 3px var(--s-2);
		border-radius: var(--r-sm);
		border: 1px solid var(--border);
		border-block-end-width: 2px;
		background: var(--surface);
		font-family: inherit;
		font-size: var(--fs-sm);
		font-weight: var(--fw-bold);
		text-align: center;
	}
	.link {
		align-self: flex-start;
		padding: 0;
		border: 0;
		background: none;
		color: var(--accent-ink);
		font-size: var(--fs-sm);
		text-decoration: underline;
		text-underline-offset: 2px;
	}
	.picker {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: var(--s-2);
	}
	.mods {
		display: flex;
		gap: var(--s-1);
	}
	.mod {
		min-block-size: 34px;
		padding-inline: var(--s-3);
		border-radius: var(--r-pill);
		border: 1px solid var(--border);
		background: var(--surface-2);
		font-size: var(--fs-sm);
	}
	.mod.on {
		border-color: var(--accent);
		background: color-mix(in oklab, var(--accent) 30%, var(--surface));
	}
	select {
		min-block-size: 34px;
		padding-inline: var(--s-2);
		border-radius: var(--r-md);
		border: 1px solid var(--border);
		background: var(--surface-2);
	}
</style>
