<script lang="ts">
	import { AirVent, Check, Search } from '@lucide/svelte';
	import { api, type CodeSet } from '$lib/api';
	import Button from '$lib/ui/Button.svelte';

	interface Props {
		onadded: (name: string) => void;
		oncancel: () => void;
	}

	let { onadded, oncancel }: Props = $props();

	/** Codes probed per round: each needs its own temperature, and ACs span ~16–30°. */
	const ROUND = 12;
	const CONFIRM_TEMPS = [25, 23, 24, 26, 22, 21, 27, 20];

	type Step =
		| { kind: 'brand' }
		| { kind: 'ready' }
		| { kind: 'probing' }
		| { kind: 'pick'; assignment: [number, number][] }
		| { kind: 'confirming' }
		| { kind: 'confirm'; code: number; temp: number }
		| { kind: 'name'; code: number; temp: number }
		| { kind: 'nomatch' };

	let step = $state<Step>({ kind: 'brand' });
	let error = $state<string | null>(null);

	// --- Brand ---
	let query = $state('');
	let results = $state<CodeSet[]>([]);
	let brand = $state<{ name: string; sets: CodeSet[] } | null>(null);
	const brands = $derived(
		Object.entries(Object.groupBy(results, (s) => s.manufacturer)).map(([name, sets]) => ({ name, sets: sets! }))
	);

	$effect(() => {
		const q = query.trim();
		if (q.length < 2) {
			results = [];
			return;
		}
		const t = setTimeout(async () => {
			try {
				results = await api.searchCodeSets(q);
			} catch (e) {
				error = e instanceof Error ? e.message : String(e);
			}
		}, 250);
		return () => clearTimeout(t);
	});

	function pickBrand(b: { name: string; sets: CodeSet[] }) {
		brand = b;
		queue = b.sets.map((s) => s.code);
		step = { kind: 'ready' };
	}

	// --- Probe rounds ---
	let queue = $state<number[]>([]);

	async function probe() {
		error = null;
		const batch = queue.slice(0, ROUND);
		step = { kind: 'probing' };
		try {
			const r = await api.probe(batch);
			queue = [...r.skipped, ...queue.slice(ROUND)];
			const assignment = Object.entries(r.assignment)
				.map(([c, t]) => [Number(c), t] as [number, number])
				.sort((a, b) => a[1] - b[1]);
			step = { kind: 'pick', assignment };
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
			step = { kind: 'ready' };
		}
	}

	function nothingChanged() {
		step = queue.length ? { kind: 'ready' } : { kind: 'nomatch' };
	}

	// --- Confirm with a second, different temperature ---
	async function confirm(code: number, shown: number) {
		error = null;
		step = { kind: 'confirming' };
		for (const temp of CONFIRM_TEMPS.filter((t) => t !== shown)) {
			try {
				await api.testCodeSet(code, temp);
				step = { kind: 'confirm', code, temp };
				return;
			} catch {
				// this code set has no signal at that temperature; try the next one
			}
		}
		// Couldn't send a different temperature; trust the probe answer.
		step = { kind: 'name', code, temp: shown };
	}

	// --- Name & add ---
	let name = $state('AC');
	let adding = $state(false);

	async function add(e: SubmitEvent) {
		e.preventDefault();
		if (step.kind !== 'name') return;
		adding = true;
		error = null;
		try {
			await api.addRemote(name.trim(), step.code, step.temp);
			onadded(name.trim());
		} catch (err) {
			error = err instanceof Error ? err.message : String(err);
		} finally {
			adding = false;
		}
	}

	const remaining = $derived(queue.length);
</script>

<div class="card">
	<div class="title">
		<span class="icon"><AirVent size={18} strokeWidth={2.3} /></span>
		<div>
			<h3>Add an AC</h3>
			<p>Controlled by your Broadlink, using the AC's remote signals.</p>
		</div>
	</div>

	{#if step.kind === 'brand'}
		<label class="search">
			<Search size={16} strokeWidth={2.3} />
			<input bind:value={query} placeholder="AC brand, e.g. Electra" autocomplete="off" aria-label="AC brand" />
		</label>
		{#if brands.length}
			<ul class="brands">
				{#each brands as b (b.name)}
					<li>
						<button onclick={() => pickBrand(b)}>
							<span>{b.name}</span>
							<span class="muted">{b.sets.length} code set{b.sets.length === 1 ? '' : 's'}</span>
						</button>
					</li>
				{/each}
			</ul>
		{:else if query.trim().length >= 2}
			<p class="muted">No brand matches “{query}”.</p>
		{/if}
	{:else if step.kind === 'ready'}
		<p>
			We'll find which of <b>{brand?.name}</b>'s {brand?.sets.length} code sets your AC understands. Each gets its own temperature.
			Afterwards, tell us which number your AC shows.
		</p>
		<p class="muted">
			Stand where you can see the AC's display, and make sure the Broadlink faces it. Your AC will turn on.
		</p>
		<div class="actions">
			<Button variant="primary" onclick={probe}>
				Send {Math.min(ROUND, remaining)} test signal{Math.min(ROUND, remaining) === 1 ? '' : 's'}
			</Button>
			<Button variant="ghost" onclick={() => (step = { kind: 'brand' })}>Change brand</Button>
		</div>
	{:else if step.kind === 'probing'}
		<p class="waiting"><span class="pulse"></span> Sending signals… watch your AC.</p>
	{:else if step.kind === 'pick'}
		<p><b>What temperature does your AC show now?</b></p>
		<div class="temps" role="group" aria-label="Temperature shown on the AC">
			{#each step.assignment as [code, temp] (code)}
				<button class="temp num" onclick={() => confirm(code, temp)}>{temp}°</button>
			{/each}
		</div>
		<div class="actions">
			<Button variant="secondary" onclick={nothingChanged}>
				{queue.length ? 'Nothing changed, try more' : 'Nothing changed'}
			</Button>
		</div>
	{:else if step.kind === 'confirming'}
		<p class="waiting"><span class="pulse"></span> Sending a check…</p>
	{:else if step.kind === 'confirm'}
		<p><b>Did your AC just change to {step.temp}°?</b></p>
		<div class="actions">
			<Button
				variant="primary"
				onclick={() => step.kind === 'confirm' && (step = { kind: 'name', code: step.code, temp: step.temp })}
			>
				Yes, it did
			</Button>
			<Button variant="secondary" onclick={() => (step = queue.length ? { kind: 'ready' } : { kind: 'nomatch' })}
				>No</Button
			>
		</div>
	{:else if step.kind === 'name'}
		<p class="found"><Check size={18} strokeWidth={2.6} /> Found it: code set {step.code}.</p>
		<form onsubmit={add}>
			<input bind:value={name} aria-label="AC name" placeholder="e.g. Living room AC" />
			<Button variant="primary" type="submit" disabled={adding || !name.trim()}
				>{adding ? 'Adding…' : 'Add to Home'}</Button
			>
		</form>
	{:else}
		<p>None of {brand?.name}'s code sets matched your AC.</p>
		<p class="muted">
			Teaching buttons with your AC's own remote is coming later. Double-check that the Broadlink can see the AC, then
			try again.
		</p>
		<div class="actions">
			<Button variant="secondary" onclick={() => brand && pickBrand(brand)}>Try again</Button>
		</div>
	{/if}

	{#if error}<p class="error" role="alert">{error}</p>{/if}

	{#if step.kind !== 'probing' && step.kind !== 'confirming'}
		<div class="footer"><Button variant="ghost" size="sm" onclick={oncancel}>Cancel</Button></div>
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
		background: var(--cool);
		color: oklch(20% 0.03 232);
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
	.search {
		display: flex;
		align-items: center;
		gap: var(--s-2);
		min-block-size: 44px;
		padding-inline: var(--s-4);
		border-radius: var(--r-pill);
		border: 1px solid var(--border);
		background: var(--surface-2);
		color: var(--text-2);
	}
	.search input {
		flex: 1;
		border: 0;
		background: transparent;
		outline: none;
		color: var(--text);
	}
	.brands {
		margin: 0;
		padding: 0;
		list-style: none;
		display: flex;
		flex-direction: column;
		gap: var(--s-1);
	}
	.brands button {
		display: flex;
		justify-content: space-between;
		inline-size: 100%;
		padding: var(--s-3) var(--s-4);
		border: 0;
		border-radius: var(--r-md);
		background: var(--surface-2);
		font-weight: var(--fw-medium);
		text-align: start;
	}
	.brands button:hover {
		background: var(--surface-3);
	}
	.actions {
		display: flex;
		flex-wrap: wrap;
		gap: var(--s-2);
	}
	.temps {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(72px, 1fr));
		gap: var(--s-2);
	}
	.temp {
		min-block-size: 64px;
		border-radius: var(--r-md);
		border: 1px solid var(--border);
		background: color-mix(in oklab, var(--cool) 16%, var(--surface));
		font-size: var(--fs-xl);
		font-weight: var(--fw-bold);
		transition: transform var(--dur-fast) var(--ease);
	}
	.temp:active {
		transform: scale(0.95);
	}
	.waiting {
		display: flex;
		align-items: center;
		gap: var(--s-2);
		color: var(--text-2);
	}
	.pulse {
		inline-size: 8px;
		block-size: 8px;
		border-radius: var(--r-pill);
		background: var(--accent);
		animation: blink 1s var(--ease) infinite alternate;
	}
	@keyframes blink {
		to {
			opacity: 0.2;
		}
	}
	.found {
		display: flex;
		align-items: center;
		gap: var(--s-2);
		font-weight: var(--fw-medium);
	}
	form {
		display: flex;
		flex-wrap: wrap;
		gap: var(--s-2);
	}
	form input {
		flex: 1 1 180px;
		min-block-size: 44px;
		padding-inline: var(--s-4);
		border-radius: var(--r-pill);
		border: 1px solid var(--border);
		background: var(--surface-2);
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
