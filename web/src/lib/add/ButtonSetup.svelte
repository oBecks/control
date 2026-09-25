<script lang="ts">
	import { Check, Fan, Gamepad2, Tv } from '@lucide/svelte';
	import { api, type CodeSet, type Device, type RemoteKind } from '$lib/api';
	import Button from '$lib/ui/Button.svelte';

	interface Props {
		hubUid: string;
		hubName: string;
		kind: RemoteKind;
		/** Teach more buttons to an existing Remote Device instead of creating one. */
		existing?: Device;
		ondone: (device: Device) => void;
		oncancel: () => void;
	}

	let { hubUid, hubName, kind, existing, ondone, oncancel }: Props = $props();

	const NOUN = { tv: 'TV', fan: 'fan', other: 'device' } as const;
	const ICON = { tv: Tv, fan: Fan, other: Gamepad2 } as const;
	const DOMAIN = { tv: 'media_player', fan: 'fan' } as const;
	const noun = $derived(NOUN[kind]);
	const Icon = $derived(ICON[kind]);

	type Step =
		| { kind: 'name' }
		| { kind: 'library'; sets: CodeSet[]; i: number; tried?: string }
		| { kind: 'teach' }
		| { kind: 'finished' };

	// The parent remounts this flow ({#key}) whenever kind/existing change, so reading their
	// initial values here is intended.
	// svelte-ignore state_referenced_locally
	let step = $state<Step>(existing ? { kind: 'teach' } : { kind: 'name' });
	let error = $state<string | null>(null);
	let busy = $state(false);

	// svelte-ignore state_referenced_locally
	let name = $state(kind === 'tv' ? 'TV' : kind === 'fan' ? 'Fan' : '');
	let brand = $state('');
	// svelte-ignore state_referenced_locally
	let device = $state<Device | null>(existing ?? null);

	// --- Name (+ optional brand to try known codes) ---
	async function next(e: SubmitEvent) {
		e.preventDefault();
		error = null;
		busy = true;
		try {
			if (kind !== 'other' && brand.trim().length >= 2) {
				const sets = await api.searchCodeSets(brand.trim(), DOMAIN[kind]);
				if (sets.length) {
					step = { kind: 'library', sets, i: 0 };
					return;
				}
			}
			await startTeaching();
		} catch (err) {
			error = err instanceof Error ? err.message : String(err);
		} finally {
			busy = false;
		}
	}

	// --- Try known codes, one set at a time ---
	async function tryCurrent() {
		if (step.kind !== 'library' || kind === 'other') return;
		error = null;
		busy = true;
		try {
			const r = await api.tryLibraryButton(DOMAIN[kind], step.sets[step.i].code, hubUid);
			step = { ...step, tried: r.label };
		} catch {
			// This set has no usable test signal; move on.
			nextSet();
		} finally {
			busy = false;
		}
	}

	function nextSet() {
		if (step.kind !== 'library') return;
		if (step.i + 1 < step.sets.length) step = { ...step, i: step.i + 1, tried: undefined };
		else startTeaching();
	}

	async function useSet() {
		if (step.kind !== 'library') return;
		busy = true;
		try {
			device = await api.addButtonRemote(name.trim(), kind, step.sets[step.i].code, hubUid);
			step = { kind: 'finished' };
		} catch (err) {
			error = err instanceof Error ? err.message : String(err);
		} finally {
			busy = false;
		}
	}

	// --- Learning ---
	let queue = $state<{ name: string; label: string }[]>([]);
	let custom = $state('');
	type Capture = { state: 'idle' } | { state: 'listening' } | { state: 'got'; signal: string } | { state: 'missed' };
	let capture = $state<Capture>({ state: 'idle' });
	let saved = $state<string[]>([]);

	async function startTeaching() {
		error = null;
		if (!device) device = await api.addButtonRemote(name.trim(), kind, undefined, hubUid);
		const suggested = await api.suggestedButtons(kind);
		const have = new Set(
			existing
				? await api.state(existing.uid).then(
						(s) => (s.control === 'remote' ? s.features.buttons.map((b) => b.name) : []),
						() => []
					)
				: []
		);
		queue = suggested.filter((b) => !have.has(b.name));
		capture = { state: 'idle' };
		step = { kind: 'teach' };
	}
	// svelte-ignore state_referenced_locally
	if (existing) startTeaching();

	const current = $derived(queue[0]);

	async function listen() {
		capture = { state: 'listening' };
		try {
			const { signal } = await api.learn(hubUid);
			capture = { state: 'got', signal };
		} catch {
			capture = { state: 'missed' };
		}
	}

	async function testIt() {
		if (capture.state === 'got') await api.sendSignal(hubUid, capture.signal).catch(() => {});
	}

	async function keep() {
		if (capture.state !== 'got' || !device || !current) return;
		try {
			device = await api.saveButton(device.uid, current.name, capture.signal);
			saved = [...saved, current.label];
			advance();
		} catch (err) {
			error = err instanceof Error ? err.message : String(err);
		}
	}

	function advance() {
		queue = queue.slice(1);
		capture = { state: 'idle' };
	}

	function addCustom(e: SubmitEvent) {
		e.preventDefault();
		const label = custom.trim();
		if (!label) return;
		const id =
			label
				.toLowerCase()
				.replace(/[^a-z0-9]+/g, '_')
				.replace(/^_|_$/g, '') || 'button';
		queue = [{ name: id, label }];
		custom = '';
		capture = { state: 'idle' };
	}
</script>

<div class="card">
	<div class="title">
		<span class="icon"><Icon size={18} strokeWidth={2.3} /></span>
		<div>
			<h3>{existing ? `Teach ${existing.name} more buttons` : `Add a ${noun}`}</h3>
			<p>Controlled by {hubName} using infrared.</p>
		</div>
	</div>

	{#if step.kind === 'name'}
		<form onsubmit={next} class="fields">
			<label>
				<span>Name</span>
				<input bind:value={name} placeholder="e.g. Living room {noun}" maxlength="40" />
			</label>
			{#if kind !== 'other'}
				<label>
					<span>Brand <small>optional, to try known codes first</small></span>
					<input bind:value={brand} placeholder={kind === 'tv' ? 'e.g. Philips' : 'e.g. Dyson'} autocomplete="off" />
				</label>
			{/if}
			<div class="actions">
				<Button variant="primary" type="submit" disabled={busy || !name.trim()}
					>{busy ? 'One moment…' : 'Continue'}</Button
				>
			</div>
		</form>
	{:else if step.kind === 'library'}
		{@const set = step.sets[step.i]}
		<p class="muted">Known codes {step.i + 1} of {step.sets.length}: {set.manufacturer} {set.models.join(', ')}</p>
		{#if !step.tried}
			<p>
				{kind === 'tv' ? 'Turn your TV on and point' : 'Point'} the Broadlink at your {noun}, then send a test signal.
			</p>
			<div class="actions">
				<Button variant="primary" onclick={tryCurrent} disabled={busy}>{busy ? 'Sending…' : 'Send test signal'}</Button>
				<Button variant="ghost" onclick={startTeaching}>Skip, teach with my remote</Button>
			</div>
		{:else}
			<p>
				<b>
					We pressed “{step.tried}”.
					{kind === 'tv' && (step.tried === 'Off' || step.tried === 'Power')
						? 'Did your TV turn off?'
						: `Did your ${noun} react?`}
				</b>
			</p>
			<div class="actions">
				<Button variant="primary" onclick={useSet} disabled={busy}>Yes, use these codes</Button>
				<Button variant="secondary" onclick={nextSet}
					>{step.i + 1 < step.sets.length ? 'No, try next' : 'No, teach with my remote'}</Button
				>
			</div>
		{/if}
	{:else if step.kind === 'teach'}
		{#if saved.length}
			<p class="saved"><Check size={16} strokeWidth={2.6} /> Learned: {saved.join(', ')}</p>
		{/if}

		{#if current}
			<div class="teach">
				<p class="big">{current.label}</p>
				{#if capture.state === 'idle'}
					<p class="muted">
						Point your {noun}'s own remote at {hubName}, tap Listen, then press <b>{current.label}</b> on it.
					</p>
					<div class="actions">
						<Button variant="primary" onclick={listen}>Listen</Button>
						<Button variant="ghost" onclick={advance}>Skip</Button>
					</div>
				{:else if capture.state === 'listening'}
					<p class="waiting"><span class="pulse"></span> Listening… press <b>{current.label}</b> now.</p>
				{:else if capture.state === 'got'}
					<p class="saved"><Check size={16} strokeWidth={2.6} /> Got it.</p>
					<div class="actions">
						<Button variant="primary" onclick={keep}>Keep</Button>
						<Button variant="secondary" onclick={testIt}>Try it</Button>
						<Button variant="ghost" onclick={listen}>Redo</Button>
					</div>
				{:else}
					<p class="error">Didn't catch anything. Hold the remote close to {hubName} and press firmly.</p>
					<div class="actions">
						<Button variant="primary" onclick={listen}>Listen again</Button>
						<Button variant="ghost" onclick={advance}>Skip</Button>
					</div>
				{/if}
			</div>
		{:else}
			<form onsubmit={addCustom} class="fields">
				<label>
					<span>Another button? <small>Any name, e.g. “Netflix” or “Light”</small></span>
					<input bind:value={custom} placeholder="Button name" maxlength="30" />
				</label>
				<div class="actions">
					<Button variant="secondary" type="submit" disabled={!custom.trim()}>Teach it</Button>
					<Button variant="primary" type="button" onclick={() => (step = { kind: 'finished' })}>Done</Button>
				</div>
			</form>
		{/if}
	{:else}
		<p class="saved">
			<Check size={18} strokeWidth={2.6} />
			{device?.name} is ready{device?.control ? ' on Home' : ''}.
		</p>
		{#if !device?.control}
			<p class="muted">It has no buttons yet. Teach at least one to control it.</p>
		{/if}
		<div class="actions">
			<Button variant="primary" onclick={() => device && ondone(device)}>Finish</Button>
		</div>
	{/if}

	{#if error}<p class="error" role="alert">{error}</p>{/if}

	{#if step.kind !== 'finished' && capture.state !== 'listening'}
		<div class="footer">
			<Button
				variant="ghost"
				size="sm"
				onclick={() => (device && step.kind === 'teach' ? (step = { kind: 'finished' }) : oncancel())}
			>
				{device && step.kind === 'teach' ? 'Stop here' : 'Cancel'}
			</Button>
		</div>
	{/if}
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
	p {
		margin: 0;
	}
	.title p,
	.muted {
		color: var(--text-2);
		font-size: var(--fs-sm);
	}
	.fields {
		display: flex;
		flex-direction: column;
		gap: var(--s-3);
	}
	label {
		display: flex;
		flex-direction: column;
		gap: var(--s-1);
		font-size: var(--fs-sm);
		font-weight: var(--fw-medium);
	}
	small {
		font-weight: var(--fw-regular);
		color: var(--text-3);
	}
	input {
		min-block-size: 44px;
		padding-inline: var(--s-4);
		border-radius: var(--r-pill);
		border: 1px solid var(--border);
		background: var(--surface-2);
		font-size: var(--fs-md);
	}
	.actions {
		display: flex;
		flex-wrap: wrap;
		gap: var(--s-2);
	}
	.teach {
		display: flex;
		flex-direction: column;
		gap: var(--s-3);
		padding: var(--s-4);
		border-radius: var(--r-md);
		background: var(--surface-2);
	}
	.big {
		font-size: var(--fs-2xl);
		font-weight: var(--fw-bold);
	}
	.waiting {
		display: flex;
		align-items: center;
		gap: var(--s-2);
	}
	.pulse {
		inline-size: 10px;
		block-size: 10px;
		border-radius: var(--r-pill);
		background: var(--accent);
		animation: blink 0.8s var(--ease) infinite alternate;
	}
	@keyframes blink {
		to {
			opacity: 0.2;
		}
	}
	.saved {
		display: flex;
		align-items: center;
		gap: var(--s-2);
		font-weight: var(--fw-medium);
		font-size: var(--fs-sm);
	}
	.error {
		color: var(--danger);
		font-size: var(--fs-sm);
	}
	.footer {
		display: flex;
		justify-content: flex-end;
		margin-block-start: calc(-1 * var(--s-2));
	}
</style>
