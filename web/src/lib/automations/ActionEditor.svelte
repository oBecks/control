<script lang="ts">
	// One "Then" of an Automation: control a Device or Group (what a Hotkey can do), wait, or notify.
	import { Trash2 } from '@lucide/svelte';
	import ActionFields from '$lib/hotkeys/ActionFields.svelte';
	import { actionOf, choiceOf, DEFAULT_PARAMS, type Choice, type Params } from '$lib/hotkeys/keys';
	import type { AutomationAction } from '$lib/types';
	import Button from '$lib/ui/Button.svelte';
	import Segmented from '$lib/ui/Segmented.svelte';
	import './editor.css';
	import { joinSeconds, splitSeconds } from './parts';

	interface Props {
		/** The Action to change; none to add one. */
		action?: AutomationAction;
		/** Keep it: answers why it can't be, or null. */
		onsave: (action: AutomationAction) => Promise<string | null>;
		onremove?: () => void;
		onclose: () => void;
	}

	let { action, onsave, onremove, onclose }: Props = $props();

	type Kind = 'control' | 'wait' | 'notify';
	const initial = (() => action)();
	const control = initial && initial.do !== 'wait' && initial.do !== 'notify' ? initial : undefined;
	const start = control ? choiceOf(control) : { choice: 'on' as Choice, params: {} };

	let kind = $state<Kind>(initial?.do === 'wait' ? 'wait' : initial?.do === 'notify' ? 'notify' : 'control');
	let target = $state(control?.target ?? '');
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
		return fieldsReady ? { ...actionOf(choice, params), target } : null;
	});

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
			{ value: 'wait', label: 'Wait' },
			{ value: 'notify', label: 'Notify' }
		]}
		bind:value={kind}
	/>

	{#if kind === 'control'}
		<ActionFields bind:target bind:choice bind:params onready={(r) => (fieldsReady = r)} />
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
