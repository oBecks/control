<script lang="ts">
	// A Clock: the time, and the date when it's wide enough. 12 or 24 hours as the browser's language has it.
	// It wakes once a minute, on the minute.
	interface Props {
		/** Wide enough for the date under the time. */
		withDate?: boolean;
	}

	let { withDate = false }: Props = $props();

	let now = $state(new Date());

	$effect(() => {
		let timer: ReturnType<typeof setTimeout>;
		const tick = () => {
			now = new Date();
			timer = setTimeout(tick, 60_000 - (Date.now() % 60_000) + 50);
		};
		tick();
		// A sleeping tab's timers drift: catch up when it's shown again.
		const shown = () => document.visibilityState === 'visible' && (clearTimeout(timer), tick());
		document.addEventListener('visibilitychange', shown);
		return () => {
			clearTimeout(timer);
			document.removeEventListener('visibilitychange', shown);
		};
	});

	const time = $derived(new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' }).format(now));
	const date = $derived(
		new Intl.DateTimeFormat(undefined, { weekday: 'long', day: 'numeric', month: 'long' }).format(now)
	);
</script>

<div class="clock">
	<time class="time num" datetime={now.toISOString()}>{time}</time>
	{#if withDate}<span class="date">{date}</span>{/if}
</div>

<style>
	.clock {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		min-inline-size: 0;
		overflow: hidden;
		padding: var(--s-2);
		border-radius: var(--r-lg);
		background: var(--surface);
		border: 1px solid var(--border);
		container-type: size;
	}
	.time {
		font-size: clamp(var(--fs-lg), min(24cqi, 55cqh), 6rem);
		font-weight: var(--fw-bold);
		line-height: 1;
		letter-spacing: -0.02em;
		white-space: nowrap;
	}
	.date {
		max-inline-size: 100%;
		overflow: hidden;
		margin-block-start: var(--s-1);
		color: var(--text-2);
		font-size: clamp(var(--fs-xs), 12cqh, var(--fs-lg));
		text-overflow: ellipsis;
		white-space: nowrap;
	}
</style>
