<script lang="ts">
	// Setting up an Android TV found by a Scan: the Link (the TV shows a code), then its name,
	// whether it's a box or a TV, and its App Shortcuts.
	import { KeyRound, TvMinimalPlay } from '@lucide/svelte';
	import { api, type AppChoices, type Device } from '$lib/api';
	import { streamerName } from '$lib/present';
	import AdbSetup from '$lib/streamer/AdbSetup.svelte';
	import AppPicker from '$lib/streamer/AppPicker.svelte';
	import type { AppShortcut, CatalogueApp } from '$lib/types';
	import Button from '$lib/ui/Button.svelte';
	import Segmented from '$lib/ui/Segmented.svelte';

	interface Props {
		device: Device;
		ondone: (d: Device) => void;
	}

	let { device, ondone }: Props = $props();

	type Step = 'intro' | 'code' | 'setup';
	let step = $state<Step>('intro');
	let busy = $state(false);
	let error = $state<string | null>(null);

	let code = $state('');
	let networkName = $state('');
	let kind = $state<'box' | 'tv'>('box');
	let name = $state('');
	let nameEdited = $state(false);
	let catalogue = $state<CatalogueApp[]>([]);
	let apps = $state<AppShortcut[]>([]);
	let installed = $state(false);

	const strip = ({ name, app, link }: AppShortcut): AppShortcut => (link ? { name, app, link } : { name, app });

	// With adb allowed, pick from what's really installed: keep chosen apps the box has, add its defaults.
	function allowed(choices: AppChoices) {
		const has = new Set(choices.apps.map((a) => a.app));
		const kept = apps.filter((a) => has.has(a.app));
		const added = choices.apps.filter((a) => a.default && !kept.some((k) => k.app === a.app)).map(strip);
		catalogue = choices.apps;
		apps = [...kept, ...added];
		installed = true;
	}

	const linkless = $derived(apps.filter((a) => !a.link).map((a) => a.name));

	const message = (e: unknown) => (e instanceof Error ? e.message : String(e));

	async function start() {
		busy = true;
		error = null;
		try {
			await api.androidTvLinkStart(device.uid);
			step = 'code';
		} catch (e) {
			error = message(e);
		} finally {
			busy = false;
		}
	}

	async function sendCode(e: SubmitEvent) {
		e.preventDefault();
		busy = true;
		error = null;
		try {
			const r = await api.androidTvLinkCode(device.uid, code.trim());
			networkName = r.device.name;
			kind = r.is_tv_guess ? 'tv' : 'box';
			name = streamerName(networkName, r.is_tv_guess);
			catalogue = r.apps;
			apps = r.apps.filter((a) => a.default).map(strip);
			step = 'setup';
		} catch (e) {
			error = message(e);
		} finally {
			busy = false;
		}
	}

	function cancel() {
		api.androidTvLinkCancel(device.uid).catch(() => {});
		step = 'intro';
		code = '';
		error = null;
	}

	function pickKind(k: 'box' | 'tv') {
		if (!nameEdited) name = streamerName(networkName, k === 'tv');
	}

	async function save(e: SubmitEvent) {
		e.preventDefault();
		busy = true;
		error = null;
		try {
			await api.patch(device.uid, { name: name.trim() });
			ondone(await api.setStreamer(device.uid, { is_tv: kind === 'tv', apps }));
		} catch (e) {
			error = message(e);
		} finally {
			busy = false;
		}
	}
</script>

<div class="card">
	<div class="title">
		<span class="icon"><TvMinimalPlay size={18} strokeWidth={2.3} /></span>
		<div>
			<h3>{step === 'setup' ? name || networkName : device.name}</h3>
			<p>{[device.brand, device.model, device.ip].filter(Boolean).join(' · ')}</p>
		</div>
	</div>

	{#if step === 'intro'}
		<p>
			Link it once and Control can turn it on and off, change the volume, and open apps. Turn on the TV it's plugged
			into first: a code will appear on it.
		</p>
		<div><Button variant="primary" onclick={start} disabled={busy}>{busy ? 'Asking…' : 'Link'}</Button></div>
	{:else if step === 'code'}
		<p>Type the code shown on the TV.</p>
		<form onsubmit={sendCode}>
			<!-- svelte-ignore a11y_autofocus -->
			<input
				bind:value={code}
				class="code"
				placeholder="Code"
				autocomplete="off"
				autocapitalize="characters"
				spellcheck="false"
				maxlength="8"
				aria-label="Code shown on the TV"
				autofocus
			/>
			<Button variant="primary" type="submit" disabled={busy || code.trim().length < 4}
				><KeyRound size={16} strokeWidth={2.4} /> {busy ? 'Linking…' : 'Link'}</Button
			>
			<Button variant="ghost" onclick={cancel}>Cancel</Button>
		</form>
		<p class="muted">No code on the TV? Check the TV is on and showing this box's input, then cancel and try again.</p>
	{:else}
		<form class="setup" onsubmit={save}>
			<Segmented
				label="What is it?"
				options={[
					{ value: 'box', label: 'A box plugged into a TV' },
					{ value: 'tv', label: 'A TV' }
				]}
				bind:value={kind}
				onchange={pickKind}
			/>
			<label>
				<span>Name</span>
				<input bind:value={name} oninput={() => (nameEdited = true)} maxlength="40" />
			</label>
			<AdbSetup
				uid={device.uid}
				onallowed={allowed}
				reason={linkless.length
					? `${linkless.join(', ')} can't be opened directly: without this, Control goes through ${linkless.length === 1 ? 'its' : 'their'} Play Store page. It also lets you pick from the apps really installed.`
					: 'Optional: lets you pick from the apps really installed, and open apps that have no link (like yes+) directly.'}
			/>
			<div>
				<h4>Apps</h4>
				<p class="muted">Buttons that open an app on it. Change them any time from its controls.</p>
			</div>
			<AppPicker {catalogue} {installed} bind:value={apps} />
			<div>
				<Button variant="primary" type="submit" disabled={busy || !name.trim()}>{busy ? 'Saving…' : 'Done'}</Button>
			</div>
		</form>
	{/if}
	{#if error}<p class="error" role="alert">{error}</p>{/if}
</div>

<style>
	.card {
		display: flex;
		flex-direction: column;
		gap: var(--s-4);
		padding: var(--s-5);
		border-radius: var(--r-lg);
		background: var(--surface);
		border: 1px solid var(--border);
		box-shadow: var(--shadow-1);
	}
	.title {
		display: flex;
		gap: var(--s-3);
	}
	.icon {
		display: grid;
		place-items: center;
		flex-shrink: 0;
		inline-size: 36px;
		block-size: 36px;
		border-radius: var(--r-pill);
		background: var(--accent);
		color: var(--on-accent);
	}
	h3 {
		margin: 0;
		font-size: var(--fs-lg);
	}
	h4 {
		margin: 0;
		font-size: var(--fs-md);
	}
	p {
		margin: 0;
	}
	.title p,
	.muted {
		color: var(--text-2);
		font-size: var(--fs-sm);
	}
	form {
		display: flex;
		flex-wrap: wrap;
		gap: var(--s-2);
	}
	.setup {
		flex-direction: column;
		flex-wrap: nowrap;
		gap: var(--s-4);
	}
	label {
		display: flex;
		flex-direction: column;
		gap: var(--s-1);
		font-size: var(--fs-sm);
		font-weight: var(--fw-medium);
		color: var(--text-2);
	}
	input {
		flex: 1 1 160px;
		min-block-size: 44px;
		padding-inline: var(--s-4);
		border-radius: var(--r-pill);
		border: 1px solid var(--border);
		background: var(--surface-2);
		color: var(--text);
		font-size: var(--fs-md);
	}
	label input {
		flex: none;
	}
	.code {
		flex: 0 1 160px;
		letter-spacing: 0.2em;
		font-weight: var(--fw-bold);
		text-transform: uppercase;
	}
	.error {
		color: var(--danger);
		font-size: var(--fs-sm);
	}
</style>
