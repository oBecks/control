<script lang="ts">
	import {
		AirVent,
		Clapperboard,
		House,
		Lightbulb,
		LightbulbOff,
		Moon,
		Plug,
		Plus,
		Radar,
		Settings,
		Sun,
		Sunrise,
		DoorOpen,
		Monitor
	} from '@lucide/svelte';
	import type { Component } from 'svelte';
	import { glowFor, type RGB } from '$lib/color';
	import { theme, type ThemePreference } from '$lib/theme.svelte';
	import type { ClimateFeatures, ClimateState, Control, LightFeatures, LightState, StateChange } from '$lib/types';
	import Banner from '$lib/ui/Banner.svelte';
	import Button from '$lib/ui/Button.svelte';
	import SceneChip from '$lib/ui/SceneChip.svelte';
	import SectionHeader from '$lib/ui/SectionHeader.svelte';
	import Segmented from '$lib/ui/Segmented.svelte';
	import Slider from '$lib/ui/Slider.svelte';
	import Tile from '$lib/ui/Tile.svelte';
	import LightControls from '$lib/controls/LightControls.svelte';
	import ClimateControls from '$lib/controls/ClimateControls.svelte';
	import PlugControls from '$lib/controls/PlugControls.svelte';

	// --- Demo devices (shaped like the Engine API; your real ones) ---------------

	const LIGHT: LightFeatures = { color: true, color_temp: true, min_kelvin: 1700, max_kelvin: 6500 };
	const AC: ClimateFeatures = {
		modes: ['cool', 'heat'],
		fan_modes: ['auto', 'low', 'mid', 'high'],
		swing_modes: [],
		min_temp: 17,
		max_temp: 30,
		step: 1
	};

	type Demo =
		| { uid: string; name: string; control: 'light'; state: LightState; offline?: boolean; isNew?: boolean }
		| { uid: string; name: string; control: 'climate'; state: ClimateState; offline?: boolean; isNew?: boolean }
		| { uid: string; name: string; control: 'plug'; state: { on: boolean }; offline?: boolean; isNew?: boolean };

	let devices = $state<Demo[]>([
		{
			uid: 'l1',
			name: 'LED strip',
			control: 'light',
			state: { on: true, brightness: 30, mode: 'white', rgb: null, kelvin: 2700 }
		},
		{
			uid: 'l2',
			name: 'Desk lamp',
			control: 'light',
			state: { on: true, brightness: 80, mode: 'color', rgb: [255, 59, 48], kelvin: null }
		},
		{
			uid: 'l3',
			name: 'Bedroom',
			control: 'light',
			state: { on: true, brightness: 60, mode: 'color', rgb: [0, 122, 255], kelvin: null }
		},
		{
			uid: 'l4',
			name: 'Hallway',
			control: 'light',
			state: { on: false, brightness: 100, mode: 'white', rgb: null, kelvin: 4000 }
		},
		{
			uid: 'l5',
			name: 'Balcony',
			control: 'light',
			state: { on: false, brightness: 100, mode: 'white', rgb: null, kelvin: 4000 },
			offline: true
		},
		{
			uid: 'a1',
			name: 'AC',
			control: 'climate',
			state: { on: true, mode: 'cool', target_temp: 22, fan: 'low', swing: null }
		},
		{
			uid: 'a2',
			name: 'Bedroom AC',
			control: 'climate',
			state: { on: true, mode: 'heat', target_temp: 25, fan: 'auto', swing: null }
		},
		{ uid: 'p1', name: 'Outlet', control: 'plug', state: { on: true } },
		{ uid: 'p2', name: 'Kettle', control: 'plug', state: { on: false }, isNew: true }
	]);

	const ICONS: Record<Exclude<Control, 'remote'>, Component> = { light: Lightbulb, climate: AirVent, plug: Plug };

	function statusOf(d: Demo): string {
		if (d.control === 'light') return d.state.on ? `On · ${d.state.brightness}%` : 'Off';
		if (d.control === 'climate')
			return d.state.on ? `${d.state.mode === 'heat' ? 'Heat' : 'Cool'} ${d.state.target_temp}°` : 'Off';
		return d.state.on ? 'On' : 'Off';
	}

	const glowOf = (d: Demo) =>
		glowFor(d.control, d.state as { mode?: string; rgb?: RGB | null; kelvin?: number | null });
	const iconOf = (d: Demo) => (d.control === 'light' && !d.state.on ? LightbulbOff : ICONS[d.control]);

	function toggle(d: Demo) {
		d.state.on = !d.state.on;
	}

	// Mimics the Engine: changing a setting turns the device on.
	function apply(d: Demo, c: StateChange) {
		const s = d.state as Record<string, unknown>;
		for (const [k, v] of Object.entries(c)) if (v !== undefined) s[k] = v;
		if (d.control === 'light') {
			if (c.rgb) (d.state as LightState).mode = 'color';
			if (c.kelvin) Object.assign(d.state, { mode: 'white', rgb: null });
		}
		if (c.on === undefined && Object.keys(c).length) d.state.on = true;
	}

	let selectedUid = $state('l1');
	const selected = $derived(devices.find((d) => d.uid === selectedUid)!);
	let sheetOpen = $state(false);

	const byControl = (c: Exclude<Control, 'remote'>) => devices.filter((d) => d.control === c);
	const onCount = (c: Exclude<Control, 'remote'>) => byControl(c).filter((d) => d.state.on && !d.offline).length;

	let activeScene = $state<string | null>(null);
	let demoSlider = $state(40);

	const SURFACES = ['--bg', '--surface', '--surface-2', '--surface-3', '--border'];
	const INKS = ['--text', '--text-2', '--text-3', '--accent', '--accent-ink'];
	const TINTS = ['--cool', '--heat', '--fan', '--offline', '--danger'];
</script>

{#snippet tileFor(d: Demo, withSelect = false)}
	<Tile
		name={d.name}
		status={statusOf(d)}
		icon={iconOf(d)}
		on={d.state.on}
		glow={glowOf(d)}
		offline={d.offline}
		assumed={d.control === 'climate'}
		isNew={d.isNew}
		selected={withSelect && d.uid === selectedUid}
		ontoggle={() => toggle(d)}
		onopen={() => {
			selectedUid = d.uid;
			sheetOpen = true;
		}}
	/>
{/snippet}

{#snippet controlsFor(d: Demo)}
	{#if d.offline}
		<div class="offline-help">
			<p>
				<b>{d.name} isn't answering.</b> It may be switched off at the wall, or it moved to a new address on your network.
			</p>
			<Button variant="primary"><Radar size={16} strokeWidth={2.4} /> Find again</Button>
			<p class="tip">Still missing? Make sure it's powered and on the same wifi as this device.</p>
		</div>
	{:else if d.control === 'light'}
		{#key d.uid}<LightControls features={LIGHT} value={d.state} onchange={(c) => apply(d, c)} />{/key}
	{:else if d.control === 'climate'}
		<ClimateControls features={AC} value={d.state} assumed onchange={(c) => apply(d, c)} />
	{:else}
		<PlugControls value={d.state} onchange={(c) => apply(d, c)} />
	{/if}
{/snippet}

{#snippet homeBody(cols: string)}
	<Banner title="1 new device found" detail="Kettle · Tuya plug, ready to use" />
	<div class="chips">
		{#each [{ l: 'Movie night', i: Clapperboard }, { l: 'Good morning', i: Sunrise }, { l: 'All off', i: Moon }] as s (s.l)}
			<SceneChip
				label={s.l}
				icon={s.i}
				active={activeScene === s.l}
				onclick={() => (activeScene = activeScene === s.l ? null : s.l)}
			/>
		{/each}
		<SceneChip label="Scene" icon={Plus} dashed />
	</div>
	{#each [['light', 'Lights'], ['climate', 'Climate'], ['plug', 'Plugs']] as [c, title] (c)}
		<section>
			<SectionHeader
				{title}
				summary={onCount(c as Exclude<Control, 'remote'>)
					? `${onCount(c as Exclude<Control, 'remote'>)} on`
					: 'all off'}
			/>
			<div class="grid" style:--cols={cols}>
				{#each byControl(c as Exclude<Control, 'remote'>) as d (d.uid)}{@render tileFor(d, true)}{/each}
			</div>
		</section>
	{/each}
{/snippet}

<div class="page">
	<header class="page-head">
		<div>
			<h1>Control style guide</h1>
			<p>Tokens, components and every Tile state. Tiles and controls are live, so try them.</p>
		</div>
		<Segmented
			label="Theme"
			options={[
				{ value: 'system', label: 'System' },
				{ value: 'light', label: 'Light' },
				{ value: 'dark', label: 'Dark' }
			]}
			value={theme.preference}
			onchange={(v: ThemePreference) => {
				theme.set(v);
				theme.apply();
			}}
		/>
	</header>

	<!-- Colour -->
	<section class="block">
		<h2 class="block-title">Colour</h2>
		<p class="note">Warm neutrals and one amber accent. The loudest colours on screen belong to your devices.</p>
		<div class="swatch-rows">
			{#each [['Surfaces', SURFACES], ['Ink & accent', INKS], ['States', TINTS]] as [label, tokens] (label)}
				<div>
					<h3 class="mini">{label}</h3>
					<div class="swatches">
						{#each tokens as t (t)}
							<div class="swatch"><span style:background="var({t})"></span><code>{t}</code></div>
						{/each}
					</div>
				</div>
			{/each}
		</div>
	</section>

	<!-- Type -->
	<section class="block">
		<h2 class="block-title">Type · Nunito</h2>
		<div class="type">
			<span class="t-display num">22°</span>
			<span class="t-2xl">Good evening</span>
			<span class="t-xl">Living room</span>
			<span class="t-lg">Lights · 2 on</span>
			<span class="t-md">LED strip is on at 30% brightness.</span>
			<span class="t-sm">Last set by Control</span>
			<span class="t-xs">NEW</span>
		</div>
	</section>

	<!-- Tiles -->
	<section class="block">
		<h2 class="block-title">Tiles</h2>
		<p class="note">
			Tap toggles. <b>›</b> (or right-click, or press-and-hold on a phone) opens Device Controls. On = the device's real colour:
			warm white, red, blue, AC cool/heat, plug amber. Offline dims in place; ≈ marks an Assumed State.
		</p>
		<div class="grid" style:--cols="repeat(auto-fill, minmax(var(--tile-min), 1fr))">
			{#each devices as d (d.uid)}{@render tileFor(d)}{/each}
		</div>
	</section>

	<!-- Components -->
	<section class="block">
		<h2 class="block-title">Components</h2>
		<div class="components">
			<div class="row">
				<Button variant="primary"><Radar size={16} strokeWidth={2.4} /> Scan network</Button>
				<Button>Find again</Button>
				<Button variant="ghost">Cancel</Button>
				<Button size="sm">Small</Button>
				<Button disabled>Disabled</Button>
			</div>
			<div class="row">
				<SceneChip label="Movie night" icon={Clapperboard} active />
				<SceneChip label="Good morning" icon={Sun} />
				<SceneChip label="Scene" icon={Plus} dashed />
			</div>
			<div class="narrow">
				<Banner title="2 new devices found" detail="Tap to set them up" />
				<Segmented
					label="Fan"
					options={[
						{ value: 'auto', label: 'Auto' },
						{ value: 'low', label: 'Low' },
						{ value: 'high', label: 'High' }
					]}
					value="auto"
				/>
				<Slider label="Brightness" min={1} max={100} bind:value={demoSlider} format={(v) => `${v}%`} />
			</div>
		</div>
	</section>

	<!-- Device Controls -->
	<section class="block">
		<h2 class="block-title">Device Controls</h2>
		<div class="control-cards">
			{#each [devices[0], devices[5], devices[7]] as d (d.uid)}
				<div class="panel-card">
					<h3 class="panel-title">{d.name}</h3>
					{@render controlsFor(d)}
				</div>
			{/each}
		</div>
	</section>

	<!-- Layouts -->
	<section class="block">
		<h2 class="block-title">Layouts</h2>
		<p class="note">
			Phone and desktop are designed as equals. On the phone, › opens a bottom sheet. On desktop, a side panel that
			stays open.
		</p>

		<div class="layouts">
			<div class="phone">
				<div class="phone-screen">
					<div class="app-head">
						<div>
							<span class="greet">Good evening</span>
							<h2 class="home-title">Home</h2>
						</div>
						<Segmented
							label="Group by"
							options={[
								{ value: 'type', label: 'Type' },
								{ value: 'rooms', label: 'Rooms' }
							]}
							value="type"
						/>
					</div>
					<div class="home">{@render homeBody('1fr 1fr')}</div>

					{#if sheetOpen}
						<button class="scrim" aria-label="Close" onclick={() => (sheetOpen = false)}></button>
						<div class="sheet" role="dialog" aria-label="{selected.name} controls">
							<div class="grabber"></div>
							<h3 class="panel-title">{selected.name}</h3>
							{@render controlsFor(selected)}
						</div>
					{/if}

					<nav class="tabbar">
						<span class="tab active"><House size={20} /><small>Home</small></span>
						<span class="tab"><Radar size={20} /><small>Add</small></span>
						<span class="tab"><Settings size={20} /><small>Settings</small></span>
					</nav>
				</div>
			</div>

			<div class="desktop-wrap">
				<div class="desktop">
					<aside class="sidebar">
						<span class="brand">Control</span>
						<span class="nav active"><House size={18} /> Home</span>
						<span class="nav"><DoorOpen size={18} /> Rooms</span>
						<span class="nav"><Radar size={18} /> Add devices</span>
						<span class="nav"><Settings size={18} /> Settings</span>
						<span class="nav hint"><Monitor size={18} /> Also on your phone</span>
					</aside>
					<main class="desk-main">
						<div class="app-head">
							<h2 class="home-title">Home</h2>
							<Segmented
								label="Group by"
								options={[
									{ value: 'type', label: 'Type' },
									{ value: 'rooms', label: 'Rooms' }
								]}
								value="type"
							/>
						</div>
						{@render homeBody('repeat(auto-fill, minmax(var(--tile-min), 1fr))')}
					</main>
					<aside class="side-panel">
						<h3 class="panel-title">{selected.name}</h3>
						{@render controlsFor(selected)}
					</aside>
				</div>
			</div>
		</div>
	</section>
</div>

<style>
	.page {
		max-inline-size: 1240px;
		margin-inline: auto;
		padding: var(--s-8) var(--s-4) var(--s-12);
	}
	.page-head {
		display: flex;
		flex-wrap: wrap;
		align-items: end;
		justify-content: space-between;
		gap: var(--s-4);
		margin-block-end: var(--s-8);
	}
	h1 {
		margin: 0;
		font-size: var(--fs-2xl);
		font-weight: var(--fw-bold);
	}
	.page-head p,
	.note {
		margin: var(--s-1) 0 0;
		color: var(--text-2);
		max-inline-size: 70ch;
	}
	.block {
		padding-block: var(--s-8);
		border-block-start: 1px solid var(--border);
	}
	.block-title {
		margin: 0;
		font-size: var(--fs-xl);
		font-weight: var(--fw-bold);
	}
	.block > .note {
		margin-block-end: var(--s-5);
	}
	.mini {
		margin: 0 0 var(--s-2);
		font-size: var(--fs-sm);
		color: var(--text-2);
		font-weight: var(--fw-medium);
	}

	.swatch-rows {
		display: grid;
		gap: var(--s-5);
	}
	.swatches {
		display: flex;
		flex-wrap: wrap;
		gap: var(--s-3);
	}
	.swatch {
		display: flex;
		flex-direction: column;
		gap: var(--s-1);
		inline-size: 104px;
	}
	.swatch span {
		block-size: 56px;
		border-radius: var(--r-md);
		border: 1px solid var(--border);
	}
	code {
		font-size: var(--fs-xs);
		color: var(--text-2);
	}

	.type {
		display: flex;
		flex-direction: column;
		gap: var(--s-2);
		margin-block-start: var(--s-4);
	}
	.t-display {
		font-size: var(--fs-display);
		font-weight: var(--fw-bold);
		line-height: 1;
	}
	.t-2xl {
		font-size: var(--fs-2xl);
		font-weight: var(--fw-bold);
	}
	.t-xl {
		font-size: var(--fs-xl);
		font-weight: var(--fw-bold);
	}
	.t-lg {
		font-size: var(--fs-lg);
		font-weight: var(--fw-bold);
	}
	.t-md {
		font-size: var(--fs-md);
	}
	.t-sm {
		font-size: var(--fs-sm);
		color: var(--text-2);
	}
	.t-xs {
		font-size: var(--fs-xs);
		font-weight: var(--fw-bold);
		letter-spacing: 0.04em;
	}

	.grid {
		display: grid;
		grid-template-columns: var(--cols);
		gap: var(--s-3);
	}

	.components {
		display: flex;
		flex-direction: column;
		gap: var(--s-5);
		margin-block-start: var(--s-4);
	}
	.row {
		display: flex;
		flex-wrap: wrap;
		gap: var(--s-2);
	}
	.narrow {
		display: flex;
		flex-direction: column;
		gap: var(--s-4);
		max-inline-size: 380px;
	}

	.control-cards {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(290px, 1fr));
		gap: var(--s-4);
		margin-block-start: var(--s-4);
	}
	.panel-card {
		padding: var(--s-5);
		border-radius: var(--r-lg);
		background: var(--surface);
		border: 1px solid var(--border);
		box-shadow: var(--shadow-1);
	}
	.panel-title {
		margin: 0 0 var(--s-4);
		font-size: var(--fs-xl);
		font-weight: var(--fw-bold);
	}

	.offline-help {
		display: flex;
		flex-direction: column;
		gap: var(--s-4);
	}
	.offline-help p {
		margin: 0;
	}
	.offline-help .tip {
		font-size: var(--fs-sm);
		color: var(--text-2);
	}

	/* --- Layout previews --- */
	.layouts {
		display: flex;
		flex-wrap: wrap;
		gap: var(--s-6);
		align-items: flex-start;
	}
	.app-head {
		display: flex;
		align-items: end;
		justify-content: space-between;
		gap: var(--s-3);
		margin-block-end: var(--s-4);
	}
	.greet {
		font-size: var(--fs-sm);
		color: var(--text-2);
	}
	.home-title {
		margin: 0;
		font-size: var(--fs-2xl);
		font-weight: var(--fw-bold);
		line-height: 1.1;
	}
	.home {
		display: flex;
		flex-direction: column;
		gap: var(--s-5);
	}
	.chips {
		display: flex;
		gap: var(--s-2);
		overflow-x: auto;
		scrollbar-width: none;
		margin-inline: calc(-1 * var(--s-4));
		padding-inline: var(--s-4);
		padding-block: 2px var(--s-1);
	}

	.phone {
		flex: none;
		inline-size: min(390px, 100%);
		padding: 10px;
		border-radius: 48px;
		background: oklch(18% 0 0);
		box-shadow: var(--shadow-2);
	}
	.phone-screen {
		position: relative;
		block-size: 780px;
		overflow: hidden;
		border-radius: 38px;
		background: var(--bg);
		padding: var(--s-10) var(--s-4) 0;
		overflow-y: auto;
		scrollbar-width: none;
	}
	.phone-screen .home {
		padding-block-end: 96px;
	}
	.tabbar {
		position: sticky;
		inset-block-end: 0;
		display: flex;
		justify-content: space-around;
		margin-inline: calc(-1 * var(--s-4));
		padding: var(--s-2) 0 var(--s-5);
		background: color-mix(in oklab, var(--bg) 85%, transparent);
		backdrop-filter: blur(12px);
		border-block-start: 1px solid var(--border);
	}
	.tab {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 2px;
		color: var(--text-3);
	}
	.tab.active {
		color: var(--accent-ink);
	}
	.scrim {
		position: absolute;
		inset: 0;
		z-index: 2;
		border: 0;
		background: var(--scrim);
		animation: fade var(--dur) var(--ease);
	}
	.sheet {
		position: absolute;
		inset-inline: 0;
		inset-block-end: 0;
		z-index: 3;
		max-block-size: 85%;
		overflow-y: auto;
		padding: var(--s-3) var(--s-5) var(--s-8);
		border-start-start-radius: 28px;
		border-start-end-radius: 28px;
		background: var(--surface);
		box-shadow: var(--shadow-2);
		animation: rise var(--dur-slow) var(--ease);
	}
	.grabber {
		inline-size: 40px;
		block-size: 5px;
		margin: 0 auto var(--s-4);
		border-radius: var(--r-pill);
		background: var(--surface-3);
	}
	@keyframes rise {
		from {
			transform: translateY(40%);
			opacity: 0;
		}
	}
	@keyframes fade {
		from {
			opacity: 0;
		}
	}

	.desktop-wrap {
		flex: 1 1 620px;
		min-inline-size: 0;
		overflow-x: auto;
		border-radius: var(--r-lg);
		border: 1px solid var(--border);
		box-shadow: var(--shadow-2);
	}
	.desktop {
		display: grid;
		grid-template-columns: 200px minmax(0, 1fr) 320px;
		min-inline-size: 900px;
		block-size: 780px;
		background: var(--bg);
	}
	.sidebar {
		display: flex;
		flex-direction: column;
		gap: var(--s-1);
		padding: var(--s-5) var(--s-3);
		border-inline-end: 1px solid var(--border);
	}
	.brand {
		padding: 0 var(--s-3) var(--s-4);
		font-size: var(--fs-lg);
		font-weight: var(--fw-bold);
	}
	.nav {
		display: flex;
		align-items: center;
		gap: var(--s-3);
		padding: var(--s-2) var(--s-3);
		border-radius: var(--r-sm);
		color: var(--text-2);
		font-weight: var(--fw-medium);
	}
	.nav.active {
		background: var(--surface);
		color: var(--text);
		box-shadow: var(--shadow-1);
	}
	.nav.hint {
		margin-block-start: auto;
		font-size: var(--fs-sm);
		color: var(--text-3);
	}
	.desk-main {
		display: flex;
		flex-direction: column;
		gap: var(--s-5);
		padding: var(--s-6);
		overflow-y: auto;
	}
	.desk-main .chips {
		margin-inline: 0;
		padding-inline: 0;
	}
	.side-panel {
		padding: var(--s-6) var(--s-5);
		border-inline-start: 1px solid var(--border);
		background: var(--surface);
		overflow-y: auto;
	}
</style>
