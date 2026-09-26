<script lang="ts">
	import {
		ChevronDown,
		ChevronLeft,
		ChevronRight,
		ChevronUp,
		House,
		Minus,
		Pause,
		Pencil,
		Play,
		Plus,
		Power,
		Undo2,
		Volume2,
		VolumeX
	} from '@lucide/svelte';
	import { api, type AppChoices } from '$lib/api';
	import AdbSetup from '$lib/streamer/AdbSetup.svelte';
	import AppPicker from '$lib/streamer/AppPicker.svelte';
	import type { AppShortcut, CatalogueApp, StateChange, StreamerFeatures, StreamerState } from '$lib/types';
	import Button from '$lib/ui/Button.svelte';

	interface Props {
		uid: string;
		features: StreamerFeatures;
		value: StreamerState;
		onchange: (change: StateChange) => void;
		/** Save new App Shortcuts; resolves true when saved. */
		onapps: (apps: AppShortcut[]) => Promise<boolean>;
	}

	let { uid, features, value, onchange, onapps }: Props = $props();

	const press = (name: string) => onchange({ press: name });

	// Editing the App Shortcuts: a draft, saved as a whole.
	let draft = $state<AppShortcut[] | null>(null);
	let catalogue = $state<CatalogueApp[]>([]);
	let installed = $state(false);
	let problem = $state<string | null>(null);
	let playStoreOk = $state(false);
	let saving = $state(false);

	function take(choices: AppChoices) {
		catalogue = choices.apps;
		installed = choices.installed;
		problem = choices.problem ?? null;
	}

	async function edit() {
		draft = features.apps.map((a) => ({ ...a }));
		playStoreOk = false;
		take({ installed: false, apps: [] }); // not the last edit's list while this one loads
		take(await api.streamerCatalogue(uid).catch(() => ({ installed: false, apps: [] })));
	}

	async function save() {
		if (!draft) return;
		saving = true;
		try {
			if (await onapps(draft)) draft = null;
		} finally {
			saving = false;
		}
	}

	const volume = $derived(
		value.volume !== null && value.volume_max ? Math.round((value.volume / value.volume_max) * 100) : null
	);
</script>

<div class="pad">
	<div class="top">
		<button
			class="power"
			class:on={value.on}
			onclick={() => onchange({ on: !value.on })}
			aria-label={value.on ? 'Turn off' : 'Turn on'}
			aria-pressed={value.on}
		>
			<Power size={28} strokeWidth={2.3} />
		</button>
		<p class="now">
			{#if value.on}
				<b>{value.app_name ?? 'On'}</b>
				{#if volume !== null}<span>Volume {value.muted ? 'muted' : `${volume}%`}</span>{/if}
			{:else}
				<b>Off</b>
			{/if}
		</p>
	</div>

	<div class="rockers">
		<div class="rocker" aria-label="Volume">
			<button onclick={() => press('volume_up')} aria-label="Volume up"><Plus size={20} strokeWidth={2.4} /></button>
			<span><Volume2 size={16} strokeWidth={2.3} /></span>
			<button onclick={() => press('volume_down')} aria-label="Volume down"
				><Minus size={20} strokeWidth={2.4} /></button
			>
		</div>
		<div class="middle">
			<button class="round" class:active={value.muted} onclick={() => press('mute')} aria-label="Mute"
				><VolumeX size={20} strokeWidth={2.3} /></button
			>
			<button class="round" onclick={() => press('play_pause')} aria-label="Play or pause"
				><Play size={14} strokeWidth={2.6} /><Pause size={14} strokeWidth={2.6} /></button
			>
		</div>
		<div class="rocker" aria-label="Channel">
			<button onclick={() => press('channel_up')} aria-label="Channel up"
				><ChevronUp size={20} strokeWidth={2.4} /></button
			>
			<span class="ch">CH</span>
			<button onclick={() => press('channel_down')} aria-label="Channel down"
				><ChevronDown size={20} strokeWidth={2.4} /></button
			>
		</div>
	</div>

	<div class="dpad">
		<button class="u" onclick={() => press('up')} aria-label="Up"><ChevronUp size={22} strokeWidth={2.4} /></button>
		<button class="l" onclick={() => press('left')} aria-label="Left"
			><ChevronLeft size={22} strokeWidth={2.4} /></button
		>
		<button class="ok" onclick={() => press('ok')}>OK</button>
		<button class="r" onclick={() => press('right')} aria-label="Right"
			><ChevronRight size={22} strokeWidth={2.4} /></button
		>
		<button class="d" onclick={() => press('down')} aria-label="Down"
			><ChevronDown size={22} strokeWidth={2.4} /></button
		>
	</div>

	<div class="pair">
		<Button variant="secondary" onclick={() => press('back')}><Undo2 size={16} strokeWidth={2.4} /> Back</Button>
		<Button variant="secondary" onclick={() => press('home')}><House size={16} strokeWidth={2.4} /> Home</Button>
	</div>

	<div class="apps">
		<div class="apps-head">
			<h3>Apps</h3>
			{#if !draft}
				<Button variant="ghost" size="sm" onclick={edit}><Pencil size={14} strokeWidth={2.4} /> Edit</Button>
			{/if}
		</div>
		{#if draft}
			{#if problem}<p class="muted">Couldn't read the installed apps: {problem}.</p>{/if}
			<AppPicker {catalogue} {installed} bind:value={draft}>
				{#snippet linkless(names)}
					{#if !features.adb && !installed && !playStoreOk}
						<AdbSetup
							{uid}
							reason="{names.join(', ')} can't be opened directly. Control can go through {names.length === 1
								? 'its'
								: 'their'} Play Store page, or open {names.length === 1
								? 'it'
								: 'them'} straight away with the box's developer mode."
							onallowed={take}
							onskip={() => (playStoreOk = true)}
						/>
					{/if}
				{/snippet}
			</AppPicker>
			<div class="pair">
				<Button variant="secondary" onclick={() => (draft = null)}>Cancel</Button>
				<Button variant="primary" onclick={save} disabled={saving}>{saving ? 'Saving…' : 'Save'}</Button>
			</div>
		{:else if features.apps.length}
			<div class="grid">
				{#each features.apps as a (a.app)}
					<button
						class="app"
						class:open={value.on && value.app === a.app}
						onclick={() => onchange({ open_app: a.link ?? a.app })}>{a.name}</button
					>
				{/each}
			</div>
		{:else}
			<p class="muted">No apps yet. Tap Edit to add the ones you open on it.</p>
		{/if}
	</div>
</div>

<style>
	.pad {
		display: flex;
		flex-direction: column;
		gap: var(--s-5);
	}
	.top {
		display: flex;
		align-items: center;
		gap: var(--s-4);
	}
	.now {
		display: flex;
		flex-direction: column;
		margin: 0;
		min-inline-size: 0;
	}
	.now b {
		font-size: var(--fs-lg);
	}
	.now span,
	.muted {
		margin: 0;
		color: var(--text-2);
		font-size: var(--fs-sm);
	}
	.pair {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: var(--s-2);
	}
	button {
		border: 1px solid var(--border);
		background: var(--surface-2);
		transition:
			background-color var(--dur-fast) var(--ease),
			transform var(--dur-fast) var(--ease);
	}
	button:active:not(:disabled) {
		transform: scale(0.93);
		background: color-mix(in oklab, var(--accent) 35%, var(--surface-2));
	}
	.power {
		display: grid;
		place-items: center;
		flex-shrink: 0;
		inline-size: 76px;
		block-size: 76px;
		border-radius: var(--r-pill);
		color: var(--text-2);
		box-shadow: var(--shadow-1);
	}
	.power.on {
		background: var(--accent);
		border-color: var(--accent);
		color: var(--on-accent);
	}
	.rockers {
		display: flex;
		align-items: center;
		justify-content: space-around;
	}
	.middle {
		display: flex;
		flex-direction: column;
		gap: var(--s-3);
	}
	.rocker {
		display: flex;
		flex-direction: column;
		align-items: center;
		border-radius: var(--r-pill);
		background: var(--surface-2);
		border: 1px solid var(--border);
		overflow: hidden;
	}
	.rocker button {
		display: grid;
		place-items: center;
		inline-size: 60px;
		block-size: 56px;
		border: 0;
		background: transparent;
	}
	.rocker span {
		display: grid;
		place-items: center;
		block-size: 28px;
		color: var(--text-3);
	}
	.ch {
		font-size: var(--fs-xs);
		font-weight: var(--fw-bold);
	}
	.round {
		display: flex;
		align-items: center;
		justify-content: center;
		inline-size: 56px;
		block-size: 56px;
		border-radius: var(--r-pill);
	}
	.round.active {
		background: color-mix(in oklab, var(--accent) 30%, var(--surface-2));
	}
	.dpad {
		align-self: center;
		display: grid;
		grid-template-areas: '. u .' 'l ok r' '. d .';
		grid-template-columns: repeat(3, 60px);
		grid-template-rows: repeat(3, 56px);
		gap: 4px;
	}
	.dpad button {
		display: grid;
		place-items: center;
		border-radius: var(--r-md);
	}
	.dpad .u {
		grid-area: u;
	}
	.dpad .d {
		grid-area: d;
	}
	.dpad .l {
		grid-area: l;
	}
	.dpad .r {
		grid-area: r;
	}
	.dpad .ok {
		grid-area: ok;
		border-radius: var(--r-pill);
		font-weight: var(--fw-bold);
		background: var(--surface-3);
	}
	.apps {
		display: flex;
		flex-direction: column;
		gap: var(--s-3);
	}
	.apps-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
	}
	h3 {
		margin: 0;
		font-size: var(--fs-sm);
		color: var(--text-2);
	}
	.grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(104px, 1fr));
		gap: var(--s-2);
	}
	.app {
		min-block-size: 52px;
		padding: var(--s-2);
		border-radius: var(--r-md);
		font-weight: var(--fw-bold);
		overflow-wrap: anywhere;
	}
	.app.open {
		border-color: var(--accent);
		background: color-mix(in oklab, var(--accent) 22%, var(--surface-2));
	}
</style>
