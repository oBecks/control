<script lang="ts">
	// What an action does to a Device or Group: the Device or Group, then toggle, set, step, press or
	// open an app, with its fields. Shared by Hotkeys and Automations (ADR 0012). A Hotkey may run an
	// Automation instead.
	import { automations as automationStore } from '$lib/automations/automations.svelte';
	import { home } from '$lib/home.svelte';
	import { choicesFor, stepOf, type Abilities, type Choice, type Params } from './keys';

	interface Props {
		target: string;
		choice: Choice;
		params: Params;
		/** The target was picked already (made from its controls): show it, don't offer others. */
		fixedTarget?: boolean;
		/** Holding keys repeats steps and presses: say so. */
		holdHint?: boolean;
		/** Offer Automations too, to run (a Hotkey's). */
		automations?: boolean;
		/** Says whether everything the choice needs is filled in. */
		onready?: (ready: boolean) => void;
	}

	let {
		target = $bindable(),
		choice = $bindable(),
		params = $bindable(),
		fixedTarget = false,
		holdHint = false,
		automations = false,
		onready
	}: Props = $props();

	$effect(() => {
		if (automations && !automationStore.loaded) automationStore.load();
	});

	const runnable = $derived(automations ? automationStore.list : []);
	const targets = $derived([
		...home.groups.map((g) => ({ uid: g.uid, name: g.name, group: true })),
		...home.controllable.map((d) => ({ uid: d.uid, name: d.name, group: false })),
		...runnable.map((a) => ({ uid: a.uid, name: a.name, group: false }))
	]);
	const targetName = $derived(targets.find((t) => t.uid === target)?.name ?? '');
	const isAutomation = $derived(target.startsWith('automation:'));

	/** The target's features have been read (a Device's buttons and apps come with its state). */
	const known = $derived(isAutomation || home.groups.some((g) => g.uid === target) || !!home.states[target]);
	const abilities = $derived.by((): Abilities => {
		if (isAutomation)
			return { control: 'automation', toggle: false, onOff: false, color: false, buttons: [], apps: [], modes: [] };
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

	// Another target may not offer the choice: fall back to its first one.
	$effect(() => {
		if (known && choices.length && !choices.some((c) => c.value === choice)) pick(choices[0].value);
	});

	$effect(() => {
		onready?.(
			!!target &&
				choices.some((c) => c.value === choice) &&
				(choice !== 'press' || !!params.button) &&
				(choice !== 'open_app' || !!params.app)
		);
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
</script>

{#if fixedTarget}
	<div class="field">
		<span>For</span>
		<p class="fixed">{targetName}</p>
	</div>
{:else}
	<label class="field">
		<span>For</span>
		<select bind:value={target} required>
			<option value="" disabled>Pick a device or group{automations ? ', or an automation' : ''}</option>
			{#if home.groups.length}
				<optgroup label="Groups">
					{#each targets.filter((t) => t.group) as t (t.uid)}<option value={t.uid}>{t.name}</option>{/each}
				</optgroup>
			{/if}
			<optgroup label="Devices">
				{#each home.controllable as d (d.uid)}<option value={d.uid}>{d.name}</option>{/each}
			</optgroup>
			{#if runnable.length}
				<optgroup label="Automations">
					{#each runnable as a (a.uid)}<option value={a.uid}>{a.name}</option>{/each}
				</optgroup>
			{/if}
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
		{#if holdHint}<p class="hint">Hold the keys to keep going.</p>{/if}
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
		{#if holdHint}<p class="hint">Hold the keys to keep pressing it.</p>{/if}
	{:else if choice === 'open_app'}
		<label class="field">
			<span>App</span>
			<select bind:value={params.app}>
				{#each abilities.apps as a (a.app)}<option value={a.app}>{a.name}</option>{/each}
			</select>
		</label>
	{/if}
{/if}

<style>
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
</style>
