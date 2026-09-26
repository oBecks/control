<script lang="ts">
	// Make or change a Hotkey: its keys, the Device or Group, and what it does to it.
	import { Trash2, X } from '@lucide/svelte';
	import { api } from '$lib/api';
	import { home } from '$lib/home.svelte';
	import type { Hotkey, KeysCheck } from '$lib/types';
	import Button from '$lib/ui/Button.svelte';
	import Segmented from '$lib/ui/Segmented.svelte';
	import { hotkeys } from './hotkeys.svelte';
	import KeyRecorder from './KeyRecorder.svelte';
	import {
		actionOf,
		choiceOf,
		choicesFor,
		DEFAULT_PARAMS,
		parseTrigger,
		stepOf,
		triggerText,
		type Abilities,
		type Choice,
		type Params,
		type Press
	} from './keys';

	interface Props {
		/** The Hotkey to edit; none to make one. */
		hotkey?: Hotkey;
		/** A new Hotkey's Device or Group, when made from its controls. */
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
	let saving = $state(false);
	let confirmDelete = $state(false);

	const targets = $derived([
		...home.groups.map((g) => ({ uid: g.uid, name: g.name, group: true })),
		...home.controllable.map((d) => ({ uid: d.uid, name: d.name, group: false }))
	]);
	const targetName = $derived(targets.find((t) => t.uid === target)?.name ?? '');

	/** The target's features have been read (a Device's buttons and apps come with its state). */
	const known = $derived(home.groups.some((g) => g.uid === target) || !!home.states[target]);
	const abilities = $derived.by((): Abilities => {
		const group = home.groups.find((g) => g.uid === target);
		if (group) {
			const st = home.groupStates[group.uid];
			return {
				control: group.control,
				toggle: true,
				onOff: true,
				color: st?.control === 'light' ? st.features.color : false,
				buttons: [],
				apps: [],
				modes: st?.control === 'climate' ? st.features.modes : []
			};
		}
		const d = home.controllable.find((x) => x.uid === target);
		const st = home.states[target];
		const base = {
			control: d?.control ?? null,
			toggle: true,
			onOff: true,
			color: false,
			buttons: [],
			apps: [],
			modes: []
		};
		if (!d || !st) return { ...base, onOff: !d?.group_problem };
		switch (st.control) {
			case 'light':
				return { ...base, color: st.features.color };
			case 'climate':
				return { ...base, modes: st.features.modes };
			case 'remote':
				return {
					...base,
					toggle: st.features.can_power,
					onOff: st.features.discrete_power,
					buttons: st.features.buttons
				};
			case 'streamer':
				return { ...base, buttons: st.features.buttons, apps: st.features.apps };
			default:
				return base;
		}
	});

	const choices = $derived(choicesFor(abilities));
	const step = $derived(stepOf(choice));
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

	// Another target may not offer the choice: fall back to its first one.
	$effect(() => {
		if (known && choices.length && !choices.some((c) => c.value === choice)) pick(choices[0].value);
	});

	function pick(next: Choice) {
		const before = stepOf(choice);
		const after = stepOf(next);
		if (after && after.unit !== before?.unit) params.step = after.normal;
		if (next === 'press' && !abilities.buttons.some((b) => b.name === params.button))
			params.button = abilities.buttons[0]?.name ?? '';
		if (next === 'open_app' && !abilities.apps.some((a) => a.app === params.app))
			params.app = abilities.apps[0]?.app ?? '';
		if (next === 'climate' && !params.mode) params.mode = abilities.modes[0] ?? '';
		choice = next;
	}

	const ready = $derived(
		!!text &&
			!checking &&
			!!check &&
			!check.problem &&
			!!target &&
			choices.some((c) => c.value === choice) &&
			(choice !== 'press' || !!params.button) &&
			(choice !== 'open_app' || !!params.app)
	);

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

	{#if initial.preset && !hotkey}
		<div class="field">
			<span>For</span>
			<p class="fixed">{targetName}</p>
		</div>
	{:else}
		<label class="field">
			<span>For</span>
			<select bind:value={target} required>
				<option value="" disabled>Pick a device or group</option>
				{#if home.groups.length}
					<optgroup label="Groups">
						{#each targets.filter((t) => t.group) as t (t.uid)}<option value={t.uid}>{t.name}</option>{/each}
					</optgroup>
				{/if}
				<optgroup label="Devices">
					{#each targets.filter((t) => !t.group) as t (t.uid)}<option value={t.uid}>{t.name}</option>{/each}
				</optgroup>
			</select>
		</label>
	{/if}

	{#if target}
		<label class="field">
			<span>Does</span>
			<select value={choice} onchange={(e) => pick(e.currentTarget.value as Choice)}>
				{#each choices as c (c.value)}<option value={c.value}>{c.label}</option>{/each}
			</select>
		</label>

		{#if step}
			<label class="field inline">
				<span>By</span>
				<span class="amount">
					<input type="number" min="1" max={step.max} step="1" bind:value={params.step} required />
					{step.unit}
				</span>
			</label>
			{#if holdRepeats}<p class="hint">Hold the keys to keep going.</p>{/if}
		{:else if choice === 'brightness'}
			<label class="field inline">
				<span>Brightness</span>
				<span class="amount"><input type="number" min="1" max="100" bind:value={params.brightness} required /> %</span>
			</label>
		{:else if choice === 'color'}
			<label class="field inline">
				<span>Colour</span>
				<input type="color" bind:value={params.color} />
			</label>
		{:else if choice === 'climate'}
			<div class="row">
				{#if abilities.modes.length}
					<label class="field">
						<span>Mode</span>
						<select bind:value={params.mode}>
							{#each abilities.modes as m (m)}<option value={m}>{m[0].toUpperCase() + m.slice(1)}</option>{/each}
						</select>
					</label>
				{/if}
				<label class="field">
					<span>Temperature</span>
					<span class="amount"
						><input type="number" min="10" max="35" step="0.5" bind:value={params.temp} required /> °</span
					>
				</label>
			</div>
		{:else if choice === 'press'}
			<label class="field">
				<span>Button</span>
				<select bind:value={params.button}>
					{#each abilities.buttons as b (b.name)}<option value={b.name}>{b.label}</option>{/each}
				</select>
			</label>
			{#if holdRepeats}<p class="hint">Hold the keys to keep pressing it.</p>{/if}
		{:else if choice === 'open_app'}
			<label class="field">
				<span>App</span>
				<select bind:value={params.app}>
					{#each abilities.apps as a (a.app)}<option value={a.app}>{a.name}</option>{/each}
				</select>
			</label>
		{/if}
	{/if}

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
	.field.inline {
		flex-direction: row;
		align-items: center;
		justify-content: space-between;
	}
	.row {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: var(--s-3);
	}
	select,
	input[type='number'] {
		min-block-size: 44px;
		padding-inline: var(--s-3);
		border-radius: var(--r-md);
		border: 1px solid var(--border);
		background: var(--surface-2);
		font-size: var(--fs-md);
	}
	select:focus,
	input:focus {
		border-color: var(--accent);
		outline: none;
	}
	.amount {
		display: flex;
		align-items: center;
		gap: var(--s-2);
		color: var(--text-2);
	}
	.amount input {
		inline-size: 5.5em;
		color: var(--text);
	}
	input[type='color'] {
		inline-size: 64px;
		block-size: 40px;
		padding: 2px;
		border-radius: var(--r-md);
		border: 1px solid var(--border);
		background: var(--surface-2);
	}
	.fixed {
		margin: 0;
		font-size: var(--fs-md);
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
