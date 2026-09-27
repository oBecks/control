<script lang="ts">
	// A Remote Pad: a TV's, fan's or Streamer's buttons laid out like its remote, from the buttons it really has.
	// Compact: power, volume (or a fan's speed), mute, play/pause, channels, the arrows with OK, Back and Home.
	// Full adds inputs and speeds, a Streamer's App Shortcuts, and learned extra buttons in a row at the bottom.
	// Without arrows even a compact pad has room for those.
	import ChevronDown from '@lucide/svelte/icons/chevron-down';
	import ChevronLeft from '@lucide/svelte/icons/chevron-left';
	import ChevronRight from '@lucide/svelte/icons/chevron-right';
	import ChevronUp from '@lucide/svelte/icons/chevron-up';
	import House from '@lucide/svelte/icons/house';
	import Minus from '@lucide/svelte/icons/minus';
	import Pause from '@lucide/svelte/icons/pause';
	import Play from '@lucide/svelte/icons/play';
	import Plus from '@lucide/svelte/icons/plus';
	import Power from '@lucide/svelte/icons/power';
	import Undo2 from '@lucide/svelte/icons/undo-2';
	import Volume2 from '@lucide/svelte/icons/volume-2';
	import VolumeX from '@lucide/svelte/icons/volume-x';
	import Wind from '@lucide/svelte/icons/wind';
	import type { DeviceState } from '$lib/api';
	import type { StateChange } from '$lib/types';
	import Card from './Card.svelte';

	type Pad = Extract<DeviceState, { control: 'remote' | 'streamer' }>;

	interface Props {
		name: string;
		reading: Pad;
		look: 'compact' | 'full';
		offline?: boolean;
		inert?: boolean;
		onchange: (change: StateChange) => void;
		onopen?: () => void;
	}

	let { name, reading, look, offline = false, inert = false, onchange, onopen }: Props = $props();

	/** Buttons with a place of their own on the pad; the rest are extras. */
	const LAID_OUT = new Set([
		'power',
		'power_on',
		'power_off',
		'volume_up',
		'volume_down',
		'mute',
		'channel_up',
		'channel_down',
		'up',
		'down',
		'left',
		'right',
		'ok',
		'home',
		'back',
		'play_pause',
		'speed_up',
		'speed_down'
	]);

	const buttons = $derived(reading.features.buttons);
	const has = (n: string) => buttons.some((b) => b.name === n);
	const press = (n: string) => onchange({ press: n });
	const streamer = $derived(reading.control === 'streamer' ? reading : null);
	const remote = $derived(reading.control === 'remote' ? reading : null);

	const dpad = $derived(['up', 'down', 'left', 'right', 'ok'].some(has));
	const full = $derived(look === 'full' || !dpad);
	const volume = $derived(has('volume_up') || has('volume_down'));
	const speed = $derived(has('speed_up') || has('speed_down'));
	const channel = $derived(has('channel_up') || has('channel_down'));
	const inputs = $derived(buttons.filter((b) => b.name.startsWith('input:')));
	const speeds = $derived(buttons.filter((b) => b.name.startsWith('speed:')));
	const extras = $derived(
		buttons.filter((b) => !LAID_OUT.has(b.name) && !b.name.startsWith('input:') && !b.name.startsWith('speed:'))
	);
	const apps = $derived(streamer?.features.apps ?? []);

	const status = $derived.by(() => {
		if (streamer) return streamer.state.on ? (streamer.state.app_name ?? 'On') : 'Off';
		if (remote?.features.discrete_power) return (remote.state.on ? 'On' : 'Off') + ' ≈';
		return undefined;
	});
</script>

<Card {name} {status} on={!!reading.state.on} {offline} {inert} {onopen}>
	<div class="pad" class:full>
		<div class="top">
			{#if remote?.features.discrete_power}
				<div class="pair">
					<button class:lit={remote.state.on} disabled={offline} onclick={() => onchange({ on: true })}>
						<Power size={15} strokeWidth={2.5} /> On
					</button>
					<button class:lit={!remote.state.on} disabled={offline} onclick={() => onchange({ on: false })}>Off</button>
				</div>
			{:else if streamer || has('power')}
				<button
					class="round power"
					class:on={!!streamer?.state.on}
					aria-label={streamer ? (streamer.state.on ? 'Turn off' : 'Turn on') : 'Power'}
					disabled={offline}
					onclick={() => (streamer ? onchange({ on: !streamer.state.on }) : press('power'))}
				>
					<Power size={20} strokeWidth={2.4} />
				</button>
			{/if}
			{#if volume}
				{@render rocker('Volume', 'volume_down', 'volume_up', Volume2)}
			{:else if speed}
				{@render rocker('Speed', 'speed_down', 'speed_up', Wind)}
			{/if}
		</div>

		{#if has('mute') || has('play_pause') || channel || (volume && speed)}
			<div class="top">
				{#if has('mute')}
					<button class="round" aria-label="Mute" disabled={offline} onclick={() => press('mute')}
						><VolumeX size={18} strokeWidth={2.3} /></button
					>
				{/if}
				{#if has('play_pause')}
					<button class="round" aria-label="Play or pause" disabled={offline} onclick={() => press('play_pause')}
						><Play size={13} strokeWidth={2.6} /><Pause size={13} strokeWidth={2.6} /></button
					>
				{/if}
				{#if volume && speed}
					{@render rocker('Speed', 'speed_down', 'speed_up', Wind)}
				{/if}
				{#if channel}
					<div class="rocker" role="group" aria-label="Channel">
						<button
							aria-label="Channel down"
							disabled={offline || !has('channel_down')}
							onclick={() => press('channel_down')}><ChevronDown size={18} strokeWidth={2.4} /></button
						>
						<span class="ch">CH</span>
						<button aria-label="Channel up" disabled={offline || !has('channel_up')} onclick={() => press('channel_up')}
							><ChevronUp size={18} strokeWidth={2.4} /></button
						>
					</div>
				{/if}
			</div>
		{/if}

		{#if dpad}
			<div class="well">
				<div class="dpad">
					<button class="u" aria-label="Up" disabled={offline || !has('up')} onclick={() => press('up')}
						><ChevronUp size={22} strokeWidth={2.4} /></button
					>
					<button class="l" aria-label="Left" disabled={offline || !has('left')} onclick={() => press('left')}
						><ChevronLeft size={22} strokeWidth={2.4} /></button
					>
					<button class="ok" disabled={offline || !has('ok')} onclick={() => press('ok')}>OK</button>
					<button class="r" aria-label="Right" disabled={offline || !has('right')} onclick={() => press('right')}
						><ChevronRight size={22} strokeWidth={2.4} /></button
					>
					<button class="d" aria-label="Down" disabled={offline || !has('down')} onclick={() => press('down')}
						><ChevronDown size={22} strokeWidth={2.4} /></button
					>
				</div>
			</div>
		{/if}

		{#if has('back') || has('home')}
			<div class="pair">
				{#if has('back')}<button disabled={offline} onclick={() => press('back')}
						><Undo2 size={15} strokeWidth={2.4} /> Back</button
					>{/if}
				{#if has('home')}<button disabled={offline} onclick={() => press('home')}
						><House size={15} strokeWidth={2.4} /> Home</button
					>{/if}
			</div>
		{/if}

		{#if full}
			{#each [speeds, inputs] as list, n (n)}
				{#if list.length}
					<div class="chips">
						{#each list as b (b.name)}
							<button class="chip" disabled={offline} onclick={() => press(b.name)}>{b.label}</button>
						{/each}
					</div>
				{/if}
			{/each}
			{#if apps.length}
				<div class="chips">
					{#each apps as a (a.app)}
						<button
							class="chip"
							class:lit={!!streamer?.state.on && streamer.state.app === a.app}
							disabled={offline}
							onclick={() => onchange({ open_app: a.link ?? a.app })}>{a.name}</button
						>
					{/each}
				</div>
			{/if}
			{#if extras.length}
				<div class="chips extras" role="group" aria-label="More buttons">
					{#each extras as b (b.name)}
						<button class="chip" disabled={offline} onclick={() => press(b.name)}>{b.label}</button>
					{/each}
				</div>
			{/if}
		{/if}
	</div>
</Card>

{#snippet rocker(label: string, down: string, up: string, Icon: typeof Volume2)}
	<div class="rocker" role="group" aria-label={label}>
		<button aria-label="{label} down" disabled={offline || !has(down)} onclick={() => press(down)}
			><Minus size={18} strokeWidth={2.4} /></button
		>
		<span><Icon size={15} strokeWidth={2.3} /></span>
		<button aria-label="{label} up" disabled={offline || !has(up)} onclick={() => press(up)}
			><Plus size={18} strokeWidth={2.4} /></button
		>
	</div>
{/snippet}

<style>
	.pad {
		flex: 1;
		min-block-size: 0;
		display: flex;
		flex-direction: column;
		gap: var(--s-2);
		overflow-y: auto;
		scrollbar-width: thin;
	}
	button {
		border: 1px solid var(--border);
		background: var(--surface-2);
		color: var(--text);
		transition:
			background-color var(--dur-fast) var(--ease),
			transform var(--dur-fast) var(--ease);
	}
	button:active:not(:disabled) {
		transform: scale(0.93);
		background: color-mix(in oklab, var(--accent) 35%, var(--surface-2));
	}
	button:disabled {
		opacity: 0.3;
	}
	/* A narrow pad puts a rocker on its own line rather than squeezing it. */
	.top {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		justify-content: space-between;
		gap: var(--s-2);
		flex-shrink: 0;
	}
	.round {
		display: grid;
		grid-auto-flow: column;
		place-items: center;
		flex-shrink: 0;
		inline-size: 40px;
		block-size: 40px;
		border-radius: var(--r-pill);
	}
	.power {
		color: var(--danger);
	}
	.power.on {
		background: var(--accent);
		border-color: var(--accent);
		color: var(--on-accent);
	}
	.rocker {
		display: flex;
		align-items: center;
		flex: 1 0 88px;
		max-inline-size: 160px;
		border-radius: var(--r-pill);
		border: 1px solid var(--border);
		background: var(--surface-2);
		overflow: hidden;
	}
	.rocker button {
		display: grid;
		place-items: center;
		flex: 1;
		block-size: 40px;
		border: 0;
		background: transparent;
	}
	.rocker span {
		display: grid;
		place-items: center;
		color: var(--text-3);
	}
	.ch {
		font-size: var(--fs-xs);
		font-weight: var(--fw-bold);
	}
	/* The arrows take whatever room is left, as a square. */
	.well {
		flex: 1 1 120px;
		min-block-size: 108px;
		display: grid;
		place-items: center;
		container-type: size;
	}
	.full .well {
		flex-basis: 150px;
		max-block-size: 260px;
	}
	.dpad {
		display: grid;
		grid-template-areas: '. u .' 'l ok r' '. d .';
		grid-template-columns: repeat(3, 1fr);
		grid-template-rows: repeat(3, 1fr);
		gap: 4px;
		inline-size: min(100cqi, 100cqh);
		aspect-ratio: 1;
		/* Arrows are the remote's, not the page's: Left stays on the left in a right-to-left language. */
		direction: ltr;
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
	.pair {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(0, 1fr));
		gap: var(--s-1);
		flex-shrink: 0;
	}
	.pair button {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: var(--s-1);
		min-inline-size: 0;
		block-size: 36px;
		border-radius: var(--r-pill);
		font-size: var(--fs-sm);
		font-weight: var(--fw-medium);
	}
	.pair button.lit,
	.chip.lit {
		background: var(--surface-3);
		font-weight: var(--fw-bold);
	}
	.chips {
		display: flex;
		flex-wrap: wrap;
		gap: var(--s-1);
		flex-shrink: 0;
	}
	.extras {
		margin-block-start: auto;
		padding-block-start: var(--s-2);
		border-block-start: 1px solid var(--border);
	}
	.chip {
		min-block-size: 32px;
		padding-inline: var(--s-3);
		border-radius: var(--r-pill);
		font-size: var(--fs-sm);
		font-weight: var(--fw-medium);
	}
</style>
