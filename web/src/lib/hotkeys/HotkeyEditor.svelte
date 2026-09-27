<script lang="ts">
	// Make or change a Hotkey: its keys, the Device or Group, and what it does to it (or the Automation it runs).
	import { Trash2, X } from '@lucide/svelte';
	import { api } from '$lib/api';
	import type { Hotkey, KeysCheck } from '$lib/types';
	import Button from '$lib/ui/Button.svelte';
	import Segmented from '$lib/ui/Segmented.svelte';
	import ActionFields from './ActionFields.svelte';
	import { hotkeys } from './hotkeys.svelte';
	import KeyRecorder from './KeyRecorder.svelte';
	import {
		actionOf,
		choiceOf,
		DEFAULT_PARAMS,
		parseTrigger,
		triggerText,
		type Choice,
		type Params,
		type Press
	} from './keys';

	interface Props {
		/** The Hotkey to edit; none to make one. */
		hotkey?: Hotkey;
		/** A new Hotkey's Device, Group or Automation, when made from its controls or page. */
		target?: string;
		onclose: () => void;
	}

	let { hotkey, target: preset, onclose }: Props = $props();

	// The form starts from the Hotkey once; polling hands over fresh objects that mustn't reset it.
	const initial = (() => ({ hotkey, preset }))();
	const start = initial.hotkey ? choiceOf(initial.hotkey.action) : { choice: 'toggle' as Choice, params: {} };
	const trigger = parseTrigger(initial.hotkey?.keys ?? '');
	let keys = $state(trigger.keys);
	let press = $state<Press>(trigger.press);
	let second = $state(trigger.then);
	let check = $state<KeysCheck | null>(null);
	let checking = $state(false);
	let target = $state(initial.hotkey?.target ?? initial.preset ?? '');
	let choice = $state<Choice>(start.choice);
	let params = $state<Params>({ ...DEFAULT_PARAMS, ...start.params });
	let fieldsReady = $state(false);
	let saving = $state(false);
	let confirmDelete = $state(false);

	const action = $derived(actionOf(choice, params));

	const PRESSES: { value: Press; label: string }[] = [
		{ value: 'once', label: 'Once' },
		{ value: 'double', label: 'Twice' },
		{ value: 'long', label: 'Hold' },
		{ value: 'then', label: 'Then a key' }
	];
	const PRESS_HINTS: Record<Press, string> = {
		once: '',
		double: 'Press them twice quickly. If one press of these keys also does something, it waits a moment first.',
		long: 'Hold them for half a second.',
		then: 'Press the keys, then the second key within 2 seconds. A small window near the tray lists the choices.'
	};
	/** Holding the keys repeats steps and presses, except after two presses or in a sequence. */
	const holdRepeats = $derived(press === 'once' || press === 'long');

	/** The keys as a whole, e.g. "Ctrl+Alt+L, then 1"; empty until there's enough to check. */
	const text = $derived(keys && (press !== 'then' || second) ? triggerText({ keys, press, then: second }) : '');

	// The Engine checks the keys, with what they'll do: a long press can't share keys with a single
	// press that repeats. A newer check wins over an older one still on its way.
	let checks = 0;
	$effect(() => {
		const asked = text;
		const does = target ? action : undefined;
		const n = ++checks;
		if (!asked) {
			check = null;
			checking = false;
			return;
		}
		checking = true;
		api
			.checkKeys(asked, hotkey?.uid, does)
			.then((c) => {
				if (n !== checks) return;
				check = c;
				if (!c.problem) {
					// Shown the way Control writes them ("KeyL" becomes "L").
					const t = parseTrigger(c.keys);
					if (t.keys !== keys) keys = t.keys;
					if (t.then !== second) second = t.then;
				}
			})
			.catch((e) => {
				if (n === checks) check = { keys: asked, problem: e instanceof Error ? e.message : String(e), warning: null };
			})
			.finally(() => {
				if (n === checks) checking = false;
			});
	});

	const ready = $derived(!!text && !checking && !!check && !check.problem && fieldsReady);

	async function save(e: SubmitEvent) {
		e.preventDefault();
		saving = true;
		if (await hotkeys.save(hotkey?.uid ?? null, text, target, action)) onclose();
		saving = false;
	}

	async function remove() {
		if (!hotkey) return;
		saving = true;
		if (await hotkeys.remove(hotkey.uid)) onclose();
		saving = false;
	}
</script>

<form onsubmit={save}>
	<div class="head">
		<h2>{hotkey ? 'Edit Hotkey' : 'New Hotkey'}</h2>
		<button type="button" class="close" aria-label="Close" onclick={onclose}><X size={18} strokeWidth={2.4} /></button>
	</div>

	<div class="field">
		<span>Keys</span>
		<KeyRecorder {keys} onrecord={(k) => (keys = k)} />
		<p class="hint">
			They work in any app, and then only for Control. Spare keys are best: F13–F24, media keys, or Ctrl+Alt with a
			letter.
		</p>
	</div>

	<div class="field">
		<span>Pressed</span>
		<Segmented label="Pressed" options={PRESSES} bind:value={press} />
		{#if PRESS_HINTS[press]}<p class="hint">{PRESS_HINTS[press]}</p>{/if}
		{#if press === 'then'}
			<KeyRecorder keys={second} second onrecord={(k) => (second = k)} />
		{/if}
		{#if check?.problem}
			<p class="problem">{check.problem}</p>
		{:else if check?.warning}
			<p class="hint">{check.warning}</p>
		{/if}
	</div>

	<ActionFields
		bind:target
		bind:choice
		bind:params
		fixedTarget={!!initial.preset && !hotkey}
		holdHint={holdRepeats}
		automations
		onready={(r) => (fieldsReady = r)}
	/>

	<div class="actions">
		<Button type="submit" variant="primary" disabled={saving || !ready}>{hotkey ? 'Save' : 'Add Hotkey'}</Button>
		<Button type="button" variant="ghost" onclick={onclose}>Cancel</Button>
	</div>

	{#if hotkey}
		<div class="danger">
			{#if confirmDelete}
				<p>Delete the Hotkey {hotkey.keys}? The keys go back to other apps.</p>
				<div class="actions">
					<Button type="button" variant="secondary" disabled={saving} onclick={remove}>
						<Trash2 size={16} strokeWidth={2.4} /> Delete
					</Button>
					<Button type="button" variant="ghost" onclick={() => (confirmDelete = false)}>Keep it</Button>
				</div>
			{:else}
				<Button type="button" variant="ghost" size="sm" onclick={() => (confirmDelete = true)}>
					<Trash2 size={15} strokeWidth={2.4} /> Delete Hotkey
				</Button>
			{/if}
		</div>
	{/if}
</form>

<style>
	form {
		display: flex;
		flex-direction: column;
		gap: var(--s-5);
	}
	.head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--s-3);
	}
	h2 {
		margin: 0;
		font-size: var(--fs-xl);
		font-weight: var(--fw-bold);
	}
	.close {
		display: grid;
		place-items: center;
		flex-shrink: 0;
		inline-size: 32px;
		block-size: 32px;
		border: 0;
		border-radius: var(--r-pill);
		background: var(--surface-2);
		color: var(--text-2);
	}
	.field {
		display: flex;
		flex-direction: column;
		gap: var(--s-2);
		min-inline-size: 0;
	}
	.field > span:first-child {
		font-weight: var(--fw-medium);
	}
	.hint {
		margin: calc(-1 * var(--s-3)) 0 0;
		font-size: var(--fs-sm);
		color: var(--text-2);
	}
	.field .hint,
	.problem {
		margin: 0;
		font-size: var(--fs-sm);
	}
	.problem {
		color: var(--danger);
	}
	.actions {
		display: flex;
		flex-wrap: wrap;
		gap: var(--s-2);
	}
	.danger {
		display: flex;
		flex-direction: column;
		align-items: flex-start;
		gap: var(--s-3);
		padding-block-start: var(--s-4);
		border-block-start: 1px solid var(--border);
	}
	.danger p {
		margin: 0;
		color: var(--text-2);
	}
	.danger :global(.btn) {
		color: var(--danger);
	}
</style>
