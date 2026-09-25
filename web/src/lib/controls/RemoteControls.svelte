<script lang="ts">
	import {
		ChevronDown,
		ChevronLeft,
		ChevronRight,
		ChevronUp,
		House,
		Info,
		Minus,
		Plus,
		Power,
		Undo2,
		Volume2,
		VolumeX
	} from '@lucide/svelte';
	import type { RemoteFeatures, RemoteState, StateChange } from '$lib/types';
	import Button from '$lib/ui/Button.svelte';

	interface Props {
		features: RemoteFeatures;
		value: RemoteState;
		onchange: (change: StateChange) => void;
		onteach?: () => void;
	}

	let { features, value, onchange, onteach }: Props = $props();

	const has = (n: string) => features.buttons.some((b) => b.name === n);
	const press = (n: string) => onchange({ press: n });

	// Buttons laid out in dedicated groups; everything else goes under "More".
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
		'speed_up',
		'speed_down'
	]);
	const inputs = $derived(features.buttons.filter((b) => b.name.startsWith('input:')));
	const speeds = $derived(features.buttons.filter((b) => b.name.startsWith('speed:')));
	const more = $derived(
		features.buttons.filter(
			(b) => !LAID_OUT.has(b.name) && !b.name.startsWith('input:') && !b.name.startsWith('speed:')
		)
	);
	const dpad = $derived(['up', 'down', 'left', 'right', 'ok'].some(has));
</script>

<div class="pad">
	{#if features.discrete_power}
		<div class="pair">
			<Button variant={value.on ? 'secondary' : 'primary'} onclick={() => onchange({ on: true })}>
				<Power size={16} strokeWidth={2.4} /> On
			</Button>
			<Button variant="secondary" onclick={() => onchange({ on: false })}>Off</Button>
		</div>
	{:else if has('power')}
		<button class="power" onclick={() => press('power')} aria-label="Power">
			<Power size={28} strokeWidth={2.3} />
		</button>
	{/if}

	{#if has('volume_up') || has('volume_down') || has('channel_up') || has('channel_down') || has('mute')}
		<div class="rockers">
			{#if has('volume_up') || has('volume_down')}
				<div class="rocker" aria-label="Volume">
					<button onclick={() => press('volume_up')} disabled={!has('volume_up')} aria-label="Volume up"
						><Plus size={20} strokeWidth={2.4} /></button
					>
					<span><Volume2 size={16} strokeWidth={2.3} /></span>
					<button onclick={() => press('volume_down')} disabled={!has('volume_down')} aria-label="Volume down"
						><Minus size={20} strokeWidth={2.4} /></button
					>
				</div>
			{/if}
			{#if has('mute')}
				<button class="round" onclick={() => press('mute')} aria-label="Mute"
					><VolumeX size={20} strokeWidth={2.3} /></button
				>
			{/if}
			{#if has('channel_up') || has('channel_down')}
				<div class="rocker" aria-label="Channel">
					<button onclick={() => press('channel_up')} disabled={!has('channel_up')} aria-label="Channel up"
						><ChevronUp size={20} strokeWidth={2.4} /></button
					>
					<span class="ch">CH</span>
					<button onclick={() => press('channel_down')} disabled={!has('channel_down')} aria-label="Channel down"
						><ChevronDown size={20} strokeWidth={2.4} /></button
					>
				</div>
			{/if}
		</div>
	{/if}

	{#if dpad}
		<div class="dpad">
			<button class="u" onclick={() => press('up')} disabled={!has('up')} aria-label="Up"
				><ChevronUp size={22} strokeWidth={2.4} /></button
			>
			<button class="l" onclick={() => press('left')} disabled={!has('left')} aria-label="Left"
				><ChevronLeft size={22} strokeWidth={2.4} /></button
			>
			<button class="ok" onclick={() => press('ok')} disabled={!has('ok')}>OK</button>
			<button class="r" onclick={() => press('right')} disabled={!has('right')} aria-label="Right"
				><ChevronRight size={22} strokeWidth={2.4} /></button
			>
			<button class="d" onclick={() => press('down')} disabled={!has('down')} aria-label="Down"
				><ChevronDown size={22} strokeWidth={2.4} /></button
			>
		</div>
	{/if}

	{#if has('home') || has('back')}
		<div class="pair">
			{#if has('back')}<Button variant="secondary" onclick={() => press('back')}
					><Undo2 size={16} strokeWidth={2.4} /> Back</Button
				>{/if}
			{#if has('home')}<Button variant="secondary" onclick={() => press('home')}
					><House size={16} strokeWidth={2.4} /> Home</Button
				>{/if}
		</div>
	{/if}

	{#if has('speed_up') || has('speed_down')}
		<div class="pair">
			<Button variant="secondary" onclick={() => press('speed_down')} disabled={!has('speed_down')}
				><Minus size={16} strokeWidth={2.4} /> Slower</Button
			>
			<Button variant="secondary" onclick={() => press('speed_up')} disabled={!has('speed_up')}
				><Plus size={16} strokeWidth={2.4} /> Faster</Button
			>
		</div>
	{/if}

	{#each [['Speed', speeds], ['Input', inputs], ['More', more]] as const as [title, list] (title)}
		{#if list.length}
			<div class="group">
				<h3>{title}</h3>
				<div class="chips">
					{#each list as b (b.name)}
						<button class="chip" onclick={() => press(b.name)}>{b.label}</button>
					{/each}
				</div>
			</div>
		{/if}
	{/each}

	<p class="note">
		<Info size={16} strokeWidth={2.3} />
		<span>
			{#if features.discrete_power}
				On/Off shows what Control last sent. Its own remote can change it without Control knowing.
			{:else}
				Sent by infrared: Control can't see whether it's on, so Power just presses the button.
			{/if}
		</span>
	</p>

	{#if onteach}
		<Button variant="ghost" size="sm" onclick={onteach}>Teach more buttons</Button>
	{/if}
</div>

<style>
	.pad {
		display: flex;
		flex-direction: column;
		gap: var(--s-5);
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
	button:disabled {
		opacity: 0.3;
	}
	.power {
		align-self: center;
		display: grid;
		place-items: center;
		inline-size: 76px;
		block-size: 76px;
		border-radius: var(--r-pill);
		color: var(--danger);
		box-shadow: var(--shadow-1);
	}
	.rockers {
		display: flex;
		align-items: center;
		justify-content: space-around;
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
		display: grid;
		place-items: center;
		inline-size: 56px;
		block-size: 56px;
		border-radius: var(--r-pill);
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
	.group h3 {
		margin: 0 0 var(--s-2);
		font-size: var(--fs-sm);
		color: var(--text-2);
	}
	.chips {
		display: flex;
		flex-wrap: wrap;
		gap: var(--s-2);
	}
	.chip {
		min-block-size: 38px;
		padding-inline: var(--s-4);
		border-radius: var(--r-pill);
		font-size: var(--fs-sm);
		font-weight: var(--fw-medium);
	}
	.note {
		display: flex;
		gap: var(--s-2);
		margin: 0;
		padding: var(--s-3);
		border-radius: var(--r-md);
		background: var(--surface-2);
		color: var(--text-2);
		font-size: var(--fs-sm);
	}
	.note :global(svg) {
		flex-shrink: 0;
		margin-block-start: 2px;
	}
</style>
