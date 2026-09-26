<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { AirVent, CircleAlert, Fan, Gamepad2, Lightbulb, Plug, Radar, Radio, CircleHelp, Tv } from '@lucide/svelte';
	import AcFinder from '$lib/add/AcFinder.svelte';
	import StreamerSetup from '$lib/add/StreamerSetup.svelte';
	import ButtonSetup from '$lib/add/ButtonSetup.svelte';
	import TuyaLink from '$lib/add/TuyaLink.svelte';
	import { api, type Device, type RemoteKind, type ScanResult } from '$lib/api';
	import { home } from '$lib/home.svelte';
	import Button from '$lib/ui/Button.svelte';
	import SectionHeader from '$lib/ui/SectionHeader.svelte';

	// Remember what was New on arrival (to badge it here), then clear the flags: the user has seen them.
	let newOnArrival = $state<Set<string>>(new Set());
	let clearedSeen = false;
	$effect(() => {
		if (clearedSeen || !home.loaded) return;
		clearedSeen = true;
		newOnArrival = new Set(home.devices.filter((d) => d.is_new).map((d) => d.uid));
		if (newOnArrival.size) api.markAllSeen().then(() => home.refresh());
	});

	let lastScan = $state<ScanResult | null>(null);
	async function scan() {
		lastScan = await home.scan();
	}

	// One setup flow at a time, on one Hub: an AC (Code Set Finder) or a button remote (Learning).
	type Flow = { hub: string; kind: 'ac' } | { hub: string; kind: RemoteKind; existing?: Device };
	let flow = $state<Flow | null>(null);

	// Arriving from Home's "Teach more buttons": open Learning for that device.
	$effect(() => {
		const uid = home.teachTarget;
		if (!uid || !home.loaded) return;
		home.teachTarget = null;
		const d = home.devices.find((x) => x.uid === uid);
		if (d?.via) {
			const kind: RemoteKind = d.category === 'media' ? 'tv' : d.category === 'climate' ? 'fan' : 'other';
			flow = { hub: d.via, kind, existing: d };
		}
	});

	const hubs = $derived(home.devices.filter((d) => d.category === 'transmitter' && d.readiness === 'ready'));
	const behind = (hub: Device) => home.devices.filter((d) => d.via === hub.uid);
	const REMOTE_ICON = { media: Tv, climate: AirVent, unknown: Gamepad2 } as Record<string, typeof Tv>;

	async function finished(d: Device) {
		flow = null;
		await home.refresh();
		home.notify(`${d.name} is set up`);
		if (d.control) goto(resolve('/'));
	}

	const network = $derived(home.devices.filter((d) => d.kind === 'network'));
	const needsLink = $derived(network.filter((d) => d.readiness === 'needs_link'));
	const needsSetup = $derived(network.filter((d) => d.readiness === 'needs_setup'));
	const tuyaWaiting = $derived(needsLink.filter((d) => d.brand === 'Tuya').length);
	// An Android TV's card stays until its setup is done: after the Link it no longer needs one.
	let streamerCards = $state<string[]>([]);
	$effect(() => {
		const waiting = needsLink.filter((d) => d.brand === 'Android TV' && d.online).map((d) => d.uid);
		const add = waiting.filter((uid) => !streamerCards.includes(uid));
		if (add.length) streamerCards = [...streamerCards, ...add];
	});
	const androidTvs = $derived(
		streamerCards.map((uid) => home.devices.find((d) => d.uid === uid)).filter((d): d is Device => !!d)
	);
	function streamerDone(d: Device) {
		streamerCards = streamerCards.filter((uid) => uid !== d.uid);
		finished(d);
	}

	function status(d: Device): { label: string; tone: 'ok' | 'warn' | 'muted' } {
		if (!d.online) return { label: 'Offline', tone: 'muted' };
		if (d.readiness === 'needs_link') return { label: 'Needs link', tone: 'warn' };
		if (d.readiness === 'needs_setup') return { label: 'Needs setup', tone: 'warn' };
		if (d.readiness === 'unsupported') return { label: 'Not supported yet', tone: 'muted' };
		if (d.category === 'transmitter') return { label: 'Hub', tone: 'ok' };
		return d.control ? { label: 'On Home', tone: 'ok' } : { label: 'Not supported yet', tone: 'muted' };
	}

	const ICON = { light: Lightbulb, plug: Plug, climate: AirVent, transmitter: Radio, media: Tv } as Record<
		string,
		typeof Lightbulb
	>;
	const summary = $derived.by(() => {
		if (!lastScan) return null;
		const parts = [`${lastScan.added.length} new`];
		const moved = Object.keys(lastScan.moved).length;
		if (moved) parts.push(`${moved} moved`);
		if (lastScan.missing.length) parts.push(`${lastScan.missing.length} not answering`);
		return parts.join(' · ');
	});
</script>

<svelte:head><title>Add devices · Control</title></svelte:head>

<main>
	<header>
		<div>
			<h1>Add devices</h1>
			<p class="muted">Find what's on your wifi and finish setting it up.</p>
		</div>
		<Button variant="primary" onclick={scan} disabled={home.scanning}>
			<span class:spin={home.scanning}><Radar size={16} strokeWidth={2.4} /></span>
			{home.scanning ? 'Scanning…' : 'Scan network'}
		</Button>
	</header>

	{#if summary}
		<p class="scan-summary" role="status">Scan finished: {summary}.</p>
		{#each Object.entries(lastScan?.errors ?? {}) as [brand, err] (brand)}
			<p class="error">{brand} couldn't be scanned: {err}</p>
		{/each}
	{/if}

	{#if tuyaWaiting || androidTvs.length || needsSetup.length}
		<section>
			<SectionHeader title="Needs your attention" />
			<div class="stack">
				{#if tuyaWaiting}
					<TuyaLink waiting={tuyaWaiting} onlinked={() => home.refresh()} />
				{/if}
				{#each androidTvs as d (d.uid)}
					<StreamerSetup device={d} ondone={streamerDone} />
				{/each}
				{#each needsSetup as d (d.uid)}
					<div class="setup">
						<CircleAlert size={20} strokeWidth={2.3} />
						<div>
							<b>{d.name}</b>
							<p class="muted">
								{d.note ? d.note[0].toUpperCase() + d.note.slice(1) : 'Finish setting it up in its own app'}. Then scan
								again.
							</p>
						</div>
					</div>
				{/each}
			</div>
		</section>
	{/if}

	<section>
		<SectionHeader title="Hubs" />
		{#if !hubs.length}
			<p class="muted">
				An AC, TV or fan without wifi can be controlled through an infrared hub like a Broadlink. None found on your
				network yet.
			</p>
		{/if}
		<div class="stack">
			{#each hubs as hub (hub.uid)}
				{@const devices = behind(hub)}
				<div class="hub">
					<div class="hub-head">
						<span class="dev-icon"><Radio size={18} strokeWidth={2.2} /></span>
						<div>
							<h3>What does {hub.name} control?</h3>
							<p class="muted">It sends infrared, like a remote. Tell Control what's in front of it.</p>
						</div>
					</div>

					{#if devices.length}
						<div class="behind">
							{#each devices as d (d.uid)}
								{@const Icon =
									d.category === 'climate' && d.control === 'remote' ? Fan : (REMOTE_ICON[d.category] ?? Gamepad2)}
								<span class="behind-chip"
									><Icon size={14} strokeWidth={2.3} /> {d.name}{d.control ? '' : ' · no buttons yet'}</span
								>
							{/each}
						</div>
					{/if}

					{#if flow?.hub === hub.uid}
						{#if flow.kind === 'ac'}
							<AcFinder
								oncancel={() => (flow = null)}
								onadded={async (name) => {
									flow = null;
									await home.refresh();
									home.notify(`${name} added to Home`);
									goto(resolve('/'));
								}}
							/>
						{:else}
							{#key flow}
								<ButtonSetup
									hubUid={hub.uid}
									hubName={hub.name}
									kind={flow.kind}
									existing={flow.existing}
									ondone={finished}
									oncancel={() => (flow = null)}
								/>
							{/key}
						{/if}
					{:else}
						<div class="choices">
							<button onclick={() => (flow = { hub: hub.uid, kind: 'ac' })}
								><AirVent size={20} strokeWidth={2.2} /> AC</button
							>
							<button onclick={() => (flow = { hub: hub.uid, kind: 'tv' })}
								><Tv size={20} strokeWidth={2.2} /> TV</button
							>
							<button onclick={() => (flow = { hub: hub.uid, kind: 'fan' })}
								><Fan size={20} strokeWidth={2.2} /> Fan</button
							>
							<button onclick={() => (flow = { hub: hub.uid, kind: 'other' })}
								><Gamepad2 size={20} strokeWidth={2.2} /> Other</button
							>
						</div>
					{/if}
				</div>
			{/each}
		</div>
	</section>

	<section>
		<SectionHeader title="On your network" summary={network.length ? `${network.length} found` : undefined} />
		{#if !network.length}
			<p class="muted">Nothing yet. Tap <b>Scan network</b>.</p>
		{:else}
			<ul class="list">
				{#each network as d (d.uid)}
					{@const s = status(d)}
					{@const Icon = ICON[d.category] ?? CircleHelp}
					<li>
						<span class="dev-icon"><Icon size={18} strokeWidth={2.2} /></span>
						<span class="dev-text">
							<span class="dev-name">
								{d.name}
								{#if newOnArrival.has(d.uid)}<span class="new">New</span>{/if}
							</span>
							<small class="muted">{[d.brand, d.model, d.ip].filter(Boolean).join(' · ')}</small>
						</span>
						<span class="chip {s.tone}">{s.label}</span>
					</li>
				{/each}
			</ul>
		{/if}
	</section>
</main>

<style>
	main {
		display: flex;
		flex-direction: column;
		gap: var(--s-8);
		max-inline-size: 760px;
	}
	@media (min-width: 960px) {
		main {
			padding: var(--s-8);
		}
	}
	header {
		display: flex;
		flex-wrap: wrap;
		align-items: flex-end;
		justify-content: space-between;
		gap: var(--s-4);
	}
	h1 {
		margin: 0;
		font-size: var(--fs-2xl);
		line-height: 1.1;
	}
	p {
		margin: 0;
	}
	.muted {
		color: var(--text-2);
		font-size: var(--fs-sm);
	}
	.spin {
		display: inline-flex;
		animation: spin 1.2s linear infinite;
	}
	@keyframes spin {
		to {
			rotate: 1turn;
		}
	}
	.scan-summary {
		margin-block-start: calc(-1 * var(--s-5));
		color: var(--text-2);
	}
	.error {
		color: var(--danger);
		font-size: var(--fs-sm);
	}
	.stack {
		display: flex;
		flex-direction: column;
		gap: var(--s-3);
	}
	.setup {
		display: flex;
		gap: var(--s-3);
		padding: var(--s-4) var(--s-5);
		border-radius: var(--r-lg);
		border: 1px solid color-mix(in oklab, var(--accent) 40%, var(--border));
		background: color-mix(in oklab, var(--accent) 10%, var(--surface));
		color: var(--accent-ink);
	}
	.setup b {
		color: var(--text);
	}
	.hub {
		display: flex;
		flex-direction: column;
		gap: var(--s-4);
		padding: var(--s-5);
		border-radius: var(--r-lg);
		background: var(--surface);
		border: 1px solid var(--border);
	}
	.hub-head {
		display: flex;
		gap: var(--s-3);
	}
	.hub h3 {
		margin: 0;
		font-size: var(--fs-lg);
	}
	.behind {
		display: flex;
		flex-wrap: wrap;
		gap: var(--s-2);
	}
	.behind-chip {
		display: inline-flex;
		align-items: center;
		gap: var(--s-1);
		padding: 2px var(--s-3);
		border-radius: var(--r-pill);
		background: var(--surface-2);
		font-size: var(--fs-sm);
		font-weight: var(--fw-medium);
	}
	.choices {
		display: grid;
		grid-template-columns: repeat(4, minmax(0, 1fr));
		gap: var(--s-2);
	}
	.choices button {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: var(--s-1);
		padding: var(--s-3) var(--s-2);
		border-radius: var(--r-md);
		border: 1px dashed var(--border);
		background: transparent;
		font-weight: var(--fw-medium);
		transition:
			background-color var(--dur-fast) var(--ease),
			transform var(--dur-fast) var(--ease);
	}
	.choices button:hover {
		background: var(--surface-2);
	}
	.choices button:active {
		transform: scale(0.96);
	}
	.list {
		margin: 0;
		padding: 0;
		list-style: none;
		border-radius: var(--r-lg);
		background: var(--surface);
		border: 1px solid var(--border);
		overflow: hidden;
	}
	.list li {
		display: flex;
		align-items: center;
		gap: var(--s-3);
		padding: var(--s-3) var(--s-4);
	}
	.list li + li {
		border-block-start: 1px solid var(--border);
	}
	.dev-icon {
		display: grid;
		place-items: center;
		flex-shrink: 0;
		inline-size: 36px;
		block-size: 36px;
		border-radius: var(--r-pill);
		background: var(--surface-2);
		color: var(--text-2);
	}
	.dev-text {
		flex: 1;
		min-inline-size: 0;
		display: flex;
		flex-direction: column;
	}
	.dev-name {
		display: flex;
		align-items: center;
		gap: var(--s-2);
		font-weight: var(--fw-medium);
	}
	.dev-text small {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.new {
		padding: 0 var(--s-2);
		border-radius: var(--r-pill);
		background: var(--accent);
		color: var(--on-accent);
		font-size: var(--fs-xs);
		font-weight: var(--fw-bold);
	}
	.chip {
		flex-shrink: 0;
		padding: 2px var(--s-3);
		border-radius: var(--r-pill);
		font-size: var(--fs-xs);
		font-weight: var(--fw-bold);
	}
	.chip.ok {
		background: color-mix(in oklab, var(--fan) 25%, var(--surface));
	}
	.chip.warn {
		background: color-mix(in oklab, var(--accent) 30%, var(--surface));
	}
	.chip.muted {
		background: var(--surface-2);
		color: var(--text-2);
	}
</style>
