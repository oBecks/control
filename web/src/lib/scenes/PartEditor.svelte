<script lang="ts">
	// One Device or Group in a Scene: on or off, and while on, only the settings ticked (ADR 0013).
	import X from '@lucide/svelte/icons/x';
	import { hexToRgb, kelvinToRgb, rgbCss, type RGB } from '$lib/color';
	import { home } from '$lib/home.svelte';
	import type { ClimateFeatures, LightFeatures, SceneState, StreamerFeatures } from '$lib/types';
	import Segmented from '$lib/ui/Segmented.svelte';
	import Slider from '$lib/ui/Slider.svelte';
	import Stepper from '$lib/ui/Stepper.svelte';

	interface Props {
		target: string;
		state: SceneState;
		onchange: (state: SceneState) => void;
		onremove: () => void;
	}

	let { target, state, onchange, onremove }: Props = $props();

	const name = $derived(home.nameOf(target) ?? target);
	// What it can take, from its latest reading (a Group's: what every member shares).
	const reading = $derived(home.stateOf(target));
	const light = $derived(reading?.control === 'light' ? (reading.features as LightFeatures) : null);
	const climate = $derived(reading?.control === 'climate' ? (reading.features as ClimateFeatures) : null);
	const box = $derived(reading?.control === 'streamer' ? (reading.features as StreamerFeatures) : null);
	const now = $derived((reading?.state ?? {}) as unknown as Record<string, unknown>);

	const on = $derived(state.on !== false);
	const colourMode = $derived<'white' | 'color'>(
		state.rgb ? 'color' : state.kelvin ? 'white' : light?.color_temp ? 'white' : 'color'
	);

	const SWATCHES = ['#ff3b30', '#ff9500', '#ffcc00', '#34c759', '#00c7be', '#007aff', '#5856d6', '#af52de', '#ff2d95'];
	const LABELS: Record<string, string> = {
		cool: 'Cool',
		heat: 'Heat',
		fan: 'Fan',
		fan_only: 'Fan',
		dry: 'Dry',
		auto: 'Auto',
		heat_cool: 'Auto',
		low: 'Low',
		mid: 'Mid',
		med: 'Mid',
		high: 'High',
		static: 'Fixed',
		swing: 'Swing'
	};
	const opts = (list: string[]) => list.map((v) => ({ value: v, label: LABELS[v] ?? v }));

	const kelvinTrack = $derived(
		light
			? `linear-gradient(to right, ${[light.min_kelvin, 2700, 4000, 5500, light.max_kelvin]
					.map((k) => rgbCss(kelvinToRgb(k)))
					.join(', ')})`
			: undefined
	);

	/** Change some fields; undefined drops a field (the Scene then leaves it as it is). */
	function set(change: Partial<Record<keyof SceneState, unknown>>) {
		const next: Record<string, unknown> = { ...state, ...change };
		for (const k of Object.keys(next)) if (next[k] === undefined) delete next[k];
		onchange(next as SceneState);
	}

	function power(value: 'on' | 'off') {
		onchange(value === 'off' ? { on: false } : { on: true });
	}

	/** Tick or untick a setting; ticking starts from how the Device is now. */
	function tick(key: keyof SceneState, checked: boolean, start: unknown) {
		set({ [key]: checked ? start : undefined, on: true });
	}

	const num = (k: string, fallback: number) => (typeof now[k] === 'number' ? (now[k] as number) : fallback);
	const sameRgb = (a: RGB | undefined, b: RGB) => !!a && a.every((v, i) => v === b[i]);
</script>

<div class="part">
	<div class="head">
		<b>{name}</b>
		<button class="remove" aria-label="Take {name} out of the scene" onclick={onremove}>
			<X size={16} strokeWidth={2.4} />
		</button>
	</div>

	<Segmented
		label="{name} power"
		options={[
			{ value: 'on', label: 'On' },
			{ value: 'off', label: 'Off' }
		]}
		value={on ? 'on' : 'off'}
		onchange={power}
	/>

	{#if on && light}
		<label class="tick">
			<input
				type="checkbox"
				checked={state.brightness !== undefined}
				onchange={(e) => tick('brightness', e.currentTarget.checked, num('brightness', 100))}
			/>
			Brightness
		</label>
		{#if state.brightness !== undefined}
			<Slider
				label="Brightness"
				min={1}
				max={100}
				value={state.brightness}
				format={(v) => `${v}%`}
				onchange={(v) => set({ brightness: v })}
			/>
		{/if}

		{#if light.color || light.color_temp}
			<label class="tick">
				<input
					type="checkbox"
					checked={state.rgb !== undefined || state.kelvin !== undefined}
					onchange={(e) =>
						e.currentTarget.checked
							? light?.color_temp
								? set({ kelvin: num('kelvin', 2700), rgb: undefined })
								: set({ rgb: (now.rgb as RGB | null) ?? hexToRgb(SWATCHES[1]), kelvin: undefined })
							: set({ rgb: undefined, kelvin: undefined })}
				/>
				Colour
			</label>
			{#if state.rgb !== undefined || state.kelvin !== undefined}
				{#if light.color && light.color_temp}
					<Segmented
						label="Light mode"
						options={[
							{ value: 'white', label: 'White' },
							{ value: 'color', label: 'Colour' }
						]}
						value={colourMode}
						onchange={(m) =>
							m === 'white'
								? set({ kelvin: num('kelvin', 2700), rgb: undefined })
								: set({ rgb: hexToRgb(SWATCHES[1]), kelvin: undefined })}
					/>
				{/if}
				{#if colourMode === 'white' && light.color_temp}
					<Slider
						label="White"
						min={light.min_kelvin}
						max={light.max_kelvin}
						step={100}
						value={state.kelvin ?? 2700}
						track={kelvinTrack}
						format={(v) => `${v}K`}
						onchange={(v) => set({ kelvin: v })}
					/>
				{:else if light.color}
					<div class="swatches" role="radiogroup" aria-label="Colour">
						{#each SWATCHES as hex (hex)}
							{@const rgb = hexToRgb(hex)}
							<button
								role="radio"
								aria-checked={sameRgb(state.rgb, rgb)}
								aria-label={hex}
								style:--sw={hex}
								onclick={() => set({ rgb, kelvin: undefined })}
							></button>
						{/each}
					</div>
				{/if}
			{/if}
		{/if}
	{:else if on && climate}
		<label class="tick">
			<input
				type="checkbox"
				checked={state.mode !== undefined}
				onchange={(e) => tick('mode', e.currentTarget.checked, now.mode ?? climate?.modes[0])}
			/>
			Mode
		</label>
		{#if state.mode !== undefined}
			<Segmented label="Mode" options={opts(climate.modes)} value={state.mode} onchange={(m) => set({ mode: m })} />
		{/if}
		<label class="tick">
			<input
				type="checkbox"
				checked={state.target_temp !== undefined}
				onchange={(e) => tick('target_temp', e.currentTarget.checked, num('target_temp', 24))}
			/>
			Temperature
		</label>
		{#if state.target_temp !== undefined}
			<div class="temp">
				<Stepper
					label="Temperature"
					value={state.target_temp}
					min={climate.min_temp}
					max={climate.max_temp}
					onchange={(t) => set({ target_temp: t })}
				/>
				<span>{state.target_temp}°</span>
			</div>
		{/if}
		{#if climate.fan_modes.length}
			<label class="tick">
				<input
					type="checkbox"
					checked={state.fan !== undefined}
					onchange={(e) => tick('fan', e.currentTarget.checked, now.fan ?? climate?.fan_modes[0])}
				/>
				Fan
			</label>
			{#if state.fan !== undefined}
				<Segmented label="Fan" options={opts(climate.fan_modes)} value={state.fan} onchange={(f) => set({ fan: f })} />
			{/if}
		{/if}
		{#if climate.swing_modes.length}
			<label class="tick">
				<input
					type="checkbox"
					checked={state.swing !== undefined}
					onchange={(e) => tick('swing', e.currentTarget.checked, now.swing ?? climate?.swing_modes[0])}
				/>
				Swing
			</label>
			{#if state.swing !== undefined}
				<Segmented
					label="Swing"
					options={opts(climate.swing_modes)}
					value={state.swing}
					onchange={(s) => set({ swing: s })}
				/>
			{/if}
		{/if}
	{:else if on && box?.apps.length}
		<label class="tick">
			<input
				type="checkbox"
				checked={state.app !== undefined}
				onchange={(e) => tick('app', e.currentTarget.checked, box?.apps[0].app)}
			/>
			Open an app
		</label>
		{#if state.app !== undefined}
			<select aria-label="App" value={state.app} onchange={(e) => set({ app: e.currentTarget.value })}>
				{#each box.apps as a (a.app)}<option value={a.app}>{a.name}</option>{/each}
				{#if !box.apps.some((a) => a.app === state.app)}<option value={state.app}>{state.app}</option>{/if}
			</select>
		{/if}
	{:else if on && !reading}
		<p class="hint">It isn't answering right now, so only On or Off can be picked.</p>
	{/if}
</div>

<style>
	.part {
		display: flex;
		flex-direction: column;
		gap: var(--s-3);
		padding: var(--s-4);
		border: 1px solid var(--border);
		border-radius: var(--r-lg);
		background: var(--surface);
		box-shadow: var(--shadow-1);
	}
	.head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--s-2);
	}
	.head b {
		overflow: hidden;
		font-weight: var(--fw-bold);
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.remove {
		display: grid;
		place-items: center;
		flex-shrink: 0;
		inline-size: 32px;
		block-size: 32px;
		border: 0;
		border-radius: var(--r-pill);
		background: transparent;
		color: var(--text-2);
	}
	.remove:hover {
		background: var(--surface-3);
		color: var(--text);
	}
	.tick {
		display: flex;
		align-items: center;
		gap: var(--s-2);
		min-block-size: 32px;
		color: var(--text-2);
		font-size: var(--fs-sm);
		font-weight: var(--fw-medium);
	}
	.tick input {
		inline-size: 18px;
		block-size: 18px;
		accent-color: var(--accent);
	}
	.temp {
		display: flex;
		align-items: center;
		gap: var(--s-3);
	}
	.temp span {
		font-size: var(--fs-xl);
		font-weight: var(--fw-bold);
		font-variant-numeric: tabular-nums;
	}
	select {
		min-block-size: 40px;
		padding-inline: var(--s-3);
		border: 1px solid var(--border);
		border-radius: var(--r-md);
		background: var(--surface);
		color: var(--text);
	}
	.swatches {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(36px, 1fr));
		gap: var(--s-3);
	}
	.swatches button {
		aspect-ratio: 1;
		border-radius: var(--r-pill);
		border: 2px solid transparent;
		background: var(--sw);
		box-shadow: inset 0 0 0 1px oklch(0% 0 0 / 0.08);
	}
	.swatches button[aria-checked='true'] {
		outline: 2px solid var(--text);
		outline-offset: 3px;
	}
	.hint {
		margin: 0;
		color: var(--text-2);
		font-size: var(--fs-sm);
	}
</style>
