<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { House, Keyboard, LayoutDashboard, Radar, Settings, Workflow } from '@lucide/svelte';
	import { dashboards } from '$lib/dashboards/dashboards.svelte';
	import { home } from '$lib/home.svelte';
	import AccessRequestBanner from '$lib/access/AccessRequestBanner.svelte';
	import Notices from '$lib/automations/Notices.svelte';
	import WaitingScreen from '$lib/access/WaitingScreen.svelte';
	import StillRunningNote from '$lib/desktop/StillRunningNote.svelte';

	let { children } = $props();

	const onThisComputer = ['localhost', '127.0.0.1', '[::1]'].includes(location.hostname);

	const NAV = [
		{ href: resolve('/'), label: 'Home', icon: House },
		{ href: resolve('/dashboards'), label: 'Dashboards', icon: LayoutDashboard },
		{ href: resolve('/automations'), label: 'Automations', short: 'Automate', icon: Workflow },
		{ href: resolve('/add'), label: 'Add devices', short: 'Add', icon: Radar },
		// Hotkeys are keys on this computer, so phones don't get the page.
		...(onThisComputer ? [{ href: resolve('/hotkeys'), label: 'Hotkeys', icon: Keyboard }] : []),
		{ href: resolve('/settings'), label: 'Settings', icon: Settings }
	];

	$effect(() => home.start());

	/** A Dashboard's (or an Automation's) own page counts as Dashboards (or Automations). */
	const isActive = (href: string) =>
		page.url.pathname === href || (href !== resolve('/') && page.url.pathname.startsWith(`${href}/`));

	/** Which side a phone held sideways has its notch on. The phone reports the space to keep clear on
	 * both sides (the other one for its rounded corners), which is too much margin; the angle tells them apart. */
	const notchSide = () => {
		const angle = screen.orientation?.angle;
		return angle === 90 ? 'left' : angle === 270 ? 'right' : undefined;
	};
	let notch = $state(notchSide());
	$effect(() => {
		const update = () => (notch = notchSide());
		screen.orientation?.addEventListener('change', update);
		return () => screen.orientation?.removeEventListener('change', update);
	});

	/** On a Dashboard, a phone on its side hides the tab bar so the Dashboard gets the whole screen. */
	const onDashboard = $derived(page.url.pathname.startsWith(`${resolve('/dashboards')}/`));

	// Opening Control lands on this browser's Dashboard instead of Home, if it picked one and it still exists.
	// Home stays hidden meanwhile, so it doesn't flash first.
	const landsOn = page.url.pathname === resolve('/') ? dashboards.openTo : null;
	let landing = $state(!!landsOn);
	if (landsOn) {
		const uid = landsOn;
		dashboards
			.load()
			.then(async () => {
				if (!dashboards.loaded || page.url.pathname !== resolve('/')) return;
				if (dashboards.get(uid)) await goto(resolve('/(app)/dashboards/[uid]', { uid }), { replaceState: true });
				else dashboards.setOpenTo(null);
			})
			.finally(() => (landing = false));
	}
</script>

{#if home.lock === 'approval_required'}
	<WaitingScreen />
{:else if home.lock === 'phone_access_off'}
	<div class="down">
		<h1>Phone access is off</h1>
		<p>Turn it on in Control's Settings on the computer running Control. This page reconnects by itself.</p>
	</div>
{:else}
	<div class="shell" class:on-dashboard={onDashboard} data-notch={notch}>
		<aside class="sidebar">
			<span class="brand">Control</span>
			<nav aria-label="Main">
				{#each NAV as n (n.href)}
					<a href={n.href} class:active={isActive(n.href)} aria-current={isActive(n.href) ? 'page' : undefined}>
						<n.icon size={18} strokeWidth={2.2} />
						{n.label}
						{#if n.href === '/add' && home.newCount}<span class="count">{home.newCount}</span>{/if}
					</a>
				{/each}
			</nav>
		</aside>

		<div class="content">
			{#if home.engineDown}
				<div class="down">
					<h1>Can't reach Control</h1>
					{#if onThisComputer}
						<p>
							Open Control from the Start menu (or, from source, run <code>control serve</code>). This page reconnects
							by itself.
						</p>
					{:else}
						<p>
							Check that the computer running Control is on, and that this phone is on the home Wi-Fi. This page
							reconnects by itself.
						</p>
					{/if}
				</div>
			{:else}
				{#if onThisComputer}<StillRunningNote />{/if}
				<Notices />
				{#if home.accessRequests.length}
					<div class="asks">
						{#each home.accessRequests as request (request.ref)}
							<AccessRequestBanner {request} ondecide={(approve) => home.decide(request.ref, approve)} />
						{/each}
					</div>
				{/if}
				{#if !landing}{@render children()}{/if}
			{/if}
		</div>

		<nav class="tabbar" aria-label="Main">
			{#each NAV as n (n.href)}
				<a href={n.href} class:active={isActive(n.href)} aria-current={isActive(n.href) ? 'page' : undefined}>
					<n.icon size={22} strokeWidth={2.1} />
					<small>{n.short ?? n.label}</small>
					{#if n.href === '/add' && home.newCount}<span class="dot" aria-label="{home.newCount} new"></span>{/if}
				</a>
			{/each}
		</nav>

		{#if home.toast}
			<div class="toast" role="status">{home.toast}</div>
		{/if}
	</div>
{/if}

<style>
	.shell {
		min-block-size: 100dvh;
	}
	/* On its side, a phone's notch and rounded corners are at the start and end. */
	.content {
		padding: var(--s-6) max(var(--s-4), env(safe-area-inset-right)) calc(88px + env(safe-area-inset-bottom))
			max(var(--s-4), env(safe-area-inset-left));
	}
	/* Screen sides, not reading sides: the notch is where it is in any language. */
	@media (max-width: 959px) {
		[data-notch='left'] .content {
			padding-right: var(--s-4);
		}
		[data-notch='right'] .content {
			padding-left: var(--s-4);
		}
	}

	/* Phone: bottom tab bar */
	.sidebar {
		display: none;
	}
	.tabbar {
		position: fixed;
		inset-inline: 0;
		inset-block-end: 0;
		z-index: 10;
		display: flex;
		justify-content: space-around;
		padding: var(--s-2) env(safe-area-inset-right) calc(var(--s-3) + env(safe-area-inset-bottom))
			env(safe-area-inset-left);
		background: color-mix(in oklab, var(--bg) 82%, transparent);
		backdrop-filter: blur(14px);
		border-block-start: 1px solid var(--border);
	}
	.tabbar a {
		position: relative;
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 2px;
		min-inline-size: 64px;
		color: var(--text-3);
		text-decoration: none;
		font-weight: var(--fw-medium);
	}
	.tabbar a.active {
		color: var(--accent-ink);
	}
	.dot {
		position: absolute;
		inset-block-start: 0;
		inset-inline-end: 18px;
		inline-size: 8px;
		block-size: 8px;
		border-radius: var(--r-pill);
		background: var(--accent);
	}

	/* A phone on its side, on a Dashboard: no tab bar (the Dashboard has its own way back). */
	@media (orientation: landscape) and (max-height: 500px) and (max-width: 959px) {
		.on-dashboard .tabbar {
			display: none;
		}
		.on-dashboard .content {
			padding-block: var(--s-3) calc(var(--s-4) + env(safe-area-inset-bottom));
		}
		.on-dashboard .toast {
			inset-block-end: calc(var(--s-4) + env(safe-area-inset-bottom));
		}
	}

	/* Desktop: sidebar */
	@media (min-width: 960px) {
		.shell {
			display: grid;
			grid-template-columns: 220px minmax(0, 1fr);
		}
		.tabbar {
			display: none;
		}
		.sidebar {
			position: sticky;
			inset-block-start: 0;
			block-size: 100dvh;
			display: flex;
			flex-direction: column;
			gap: var(--s-4);
			padding: var(--s-6) var(--s-3);
			border-inline-end: 1px solid var(--border);
		}
		.content {
			padding: 0;
		}
	}

	.brand {
		padding-inline: var(--s-3);
		font-size: var(--fs-lg);
		font-weight: var(--fw-bold);
	}
	.sidebar nav {
		display: flex;
		flex-direction: column;
		gap: var(--s-1);
	}
	.sidebar a {
		display: flex;
		align-items: center;
		gap: var(--s-3);
		padding: var(--s-2) var(--s-3);
		border-radius: var(--r-sm);
		color: var(--text-2);
		text-decoration: none;
		font-weight: var(--fw-medium);
		transition: background-color var(--dur-fast) var(--ease);
	}
	.sidebar a:hover {
		background: var(--surface-2);
	}
	.sidebar a.active {
		background: var(--surface);
		color: var(--text);
		box-shadow: var(--shadow-1);
	}
	.count {
		margin-inline-start: auto;
		padding: 0 var(--s-2);
		border-radius: var(--r-pill);
		background: var(--accent);
		color: var(--on-accent);
		font-size: var(--fs-xs);
		font-weight: var(--fw-bold);
	}

	.asks {
		display: flex;
		flex-direction: column;
		gap: var(--s-2);
		margin-block-end: var(--s-4);
	}
	@media (min-width: 960px) {
		.asks {
			margin: 0;
			padding: var(--s-6) var(--s-8) 0;
		}
	}

	.down {
		max-inline-size: 460px;
		margin: 15vh auto 0;
		padding: var(--s-6);
		text-align: center;
	}
	.down h1 {
		font-size: var(--fs-xl);
	}
	.down p {
		color: var(--text-2);
	}

	.toast {
		position: fixed;
		inset-block-end: calc(96px + env(safe-area-inset-bottom));
		inset-inline-start: 50%;
		translate: -50% 0;
		z-index: 30;
		max-inline-size: calc(100vw - 32px);
		padding: var(--s-3) var(--s-5);
		border-radius: var(--r-pill);
		background: var(--text);
		color: var(--bg);
		font-weight: var(--fw-medium);
		font-size: var(--fs-sm);
		box-shadow: var(--shadow-2);
		animation: pop var(--dur) var(--ease);
	}
	@media (min-width: 960px) {
		.toast {
			inset-block-end: var(--s-6);
		}
	}
	@keyframes pop {
		from {
			opacity: 0;
			translate: -50% 8px;
		}
	}
</style>
