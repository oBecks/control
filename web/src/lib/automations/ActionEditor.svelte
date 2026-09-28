<script lang="ts">
	// One "Then" of an Automation: control a Device or Group (what a Hotkey can do), set a Scene, run
	// another Automation, wait, or notify.
	import { Trash2 } from '@lucide/svelte';
	import ActionFields from '$lib/hotkeys/ActionFields.svelte';
	import { actionOf, choiceOf, DEFAULT_PARAMS, type Choice, type Params } from '$lib/hotkeys/keys';
	import { home } from '$lib/home.svelte';
	import type { AutomationAction } from '$lib/types';
	import Button from '$lib/ui/Button.svelte';
	import Segmented from '$lib/ui/Segmented.svelte';
	import { automations } from './automations.svelte';
	import './editor.css';
	import { joinSeconds, splitSeconds } from './parts';

	interface Props {
		/** The Action to change; none to add one. */
		action?: AutomationAction;
		/** The Automation being edited, which can't run itself; none while it's new. */
		self?: string;
		/** Keep it: answers why it can't be, or null. */
		onsave: (action: AutomationAction) => Promise<string | null>;
		onremove?: () => void;
		onclose: () => void;
	}

	let { action, self, onsave, onremove, onclose }: Props = $props();

	type Kind = 'control' | 'set_scene' | 'run' | 'wait' | 'notify';
	type Own = Extract<AutomationAction, { do: Exclude<Kind, 'control'> }>;
	const isOwn = (a: AutomationAction): a is Own => ['set_scene', 'run', 'wait', 'notify'].includes(a.do);
	const initial = (() => action)();
	const control = initial && !isOwn(initial) ? initial : undefined;
	const start = control ? choiceOf(control) : { choice: 'on' as Choice, params: {} };

	let kind = $state<Kind>(initial && isOwn(initial) ? initial.do : 'control');
	let target = $state(control?.target ?? '');
	/** The Automation a Run starts. */
	let runs = $state(initial?.do === 'run' ? initial.target : '');
	/** The Scene it sets. */
	let sets = $state(initial?.do === 'set_scene' ? initial.target : '');
	let choice = $state<Choice>(start.choice);
	let params = $state<Params>({ ...DEFAULT_PARAMS, ...start.params });
	let fieldsReady = $state(false);
	let wait = $state(splitSeconds(initial?.do === 'wait' ? initial.seconds : 600));
	let text = $state(initial?.do === 'notify' ? initial.text : '');
	let problem = $state<string | null>(null);
	let saving = $state(false);

	const built = $derived.by((): AutomationAction | null => {
		if (kind === 'wait') {
			const seconds = joinSeconds(wait);
			return seconds > 0 ? { do: 'wait', seconds } : null;
		}
		if (kind === 'notify') return text.trim() ? { do: 'notify', text: text.trim() } : null;
		if (kind === 'run') return runs ? { do: 'run', target: runs } : null;
		if (kind === 'set_scene') return sets ? { do: 'set_scene', target: sets } : null;
		// ActionFields offers no Automations or Scenes here, so a control Action never runs or sets one.
		return fieldsReady ? { ...actionOf(choice, params), target } : null;
	});

	$effect(() => {
		if (!automations.loaded) automations.load();
	});
	/** Every other Automation; the Engine refuses one that would run this one again. */
	const others = $derived(automations.list.filter((a) => a.uid !== self));

	async function save(e: SubmitEvent) {
		e.preventDefault();
		if (!built) return;
		saving = true;
		problem = await onsave(built);
		saving = false;
	}
</script>

<form class="part-editor" onsubmit={save}>
	<h2>{initial ? 'Then' : 'Add a Then'}</h2>

	<Segmented
		label="Then"
		options={[
			{ value: 'control', label: 'Control' },
			{ value: 'set_scene', label: 'Scene' },
			{ value: 'run', label: 'Run' },
			{ value: 'wait', label: 'Wait' },
			{ value: 'notify', label: 'Notify' }
		]}
		bind:value={kind}
	/>

	{#if kind === 'control'}
		<ActionFields bind:target bind:choice bind:params onready={(r) => (fieldsReady = r)} />
	{:else if kind === 'set_scene'}
		{#if home.scenes.length}
			<label class="field">
				<span>Scene</span>
				<select bind:value={sets} required>
					<option value="" disabled>Pick a scene</option>
					{#each home.scenes as sc (sc.uid)}<option value={sc.uid}>{sc.name}</option>{/each}
				</select>
			</label>
			<p class="hint">
				Sets every device in it at once. Automations that start when it's set start too, but not in a loop with this
				one.
			</p>
		{:else}
			<p class="hint">{home.loaded ? 'There are no scenes yet. Make one on the Scenes page.' : 'Loading scenes…'}</p>
		{/if}
	{:else if kind === 'run'}
		{#if others.length}
			<label class="field">
				<span>Automation</span>
				<select bind:value={runs} required>
					<option value="" disabled>Pick an automation</option>
					{#each others as a (a.uid)}<option value={a.uid}>{a.name}</option>{/each}
				</select>
			</label>
			<p class="hint">
				It does its Then right away, skipping its Only if, and this one carries on without waiting for it. Automations
				can't run each other in a loop.
			</p>
		{:else}
			<p class="hint">
				{automations.loaded ? 'There are no other automations to run yet.' : 'Loading automations…'}
			</p>
		{/if}
	{:else if kind === 'wait'}
		<div class="amounts" role="group" aria-label="How long">
			<input type="number" min="0" max="24" bind:value={wait.h} aria-label="Hours" /> h
			<input type="number" min="0" max="59" bind:value={wait.m} aria-label="Minutes" /> min
			<input type="number" min="0" max="59" bind:value={wait.s} aria-label="Seconds" /> s
		</div>
		<p class="hint">
			A new When during the wait starts the Automation again from the top. If the PC sleeps through the wait, the rest
			doesn't happen late: Control tells you instead.
		</p>
	{:else}
		<label class="field">
			<span>Says</span>
			<textarea bind:value={text} rows="2" maxlength="200" placeholder="e.g. The AC is still on" required></textarea>
		</label>
		<p class="hint">A Windows notification on the computer running Control, and a note at the top of the app.</p>
	{/if}

	{#if problem}<p class="problem">{problem}</p>{/if}

	<div class="actions">
		<Button type="submit" variant="primary" disabled={saving || !built}>Done</Button>
		<Button type="button" variant="ghost" onclick={onclose}>Cancel</Button>
		{#if onremove}
			<span class="remove">
				<Button type="button" variant="ghost" onclick={onremove}><Trash2 size={15} strokeWidth={2.4} /> Remove</Button>
			</span>
		{/if}
	</div>
</form>
