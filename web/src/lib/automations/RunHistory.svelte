<script lang="ts">
	// An Automation's last Runs, newest first: what started each, how it ended, and each Action.
	import { ChevronDown } from '@lucide/svelte';
	import type { Run } from '$lib/types';
	import { OUTCOMES, when } from './parts';

	interface Props {
		runs: Run[];
	}

	let { runs }: Props = $props();

	let open = $state<number | null>(null);

	const RESULTS = { done: 'Done', failed: 'Failed', not_run: 'Didn’t run' };
</script>

{#if runs.length}
	<ul>
		{#each runs as run (run.id)}
			{@const outcome = OUTCOMES[run.outcome]}
			{@const details = run.steps.length > 0 && run.outcome !== 'missed' && run.outcome !== 'skipped'}
			<li>
				<button
					type="button"
					class="run"
					aria-expanded={details ? open === run.id : undefined}
					disabled={!details && !run.note}
					onclick={() => (open = open === run.id ? null : run.id)}
				>
					<span class="dot {outcome.tone}" aria-hidden="true"></span>
					<span class="text">
						<span class="line"><b>{when(run.started)}</b> · {run.cause}</span>
						<small class={outcome.tone}>{outcome.label}</small>
					</span>
					{#if details || run.note}<ChevronDown size={16} strokeWidth={2.4} />{/if}
				</button>
				{#if open === run.id}
					<div class="details">
						{#if run.note}<p>{run.note}</p>{/if}
						{#if details}
							<ol>
								{#each run.steps as step, i (i)}
									<li class={step.result}>
										<span>{step.label}</span>
										<small>{RESULTS[step.result]}{step.detail ? `: ${step.detail}` : ''}</small>
									</li>
								{/each}
							</ol>
						{/if}
					</div>
				{/if}
			</li>
		{/each}
	</ul>
{:else}
	<p class="none">It hasn't run yet.</p>
{/if}

<style>
	ul,
	ol {
		display: flex;
		flex-direction: column;
		margin: 0;
		padding: 0;
		list-style: none;
	}
	.run {
		display: flex;
		align-items: center;
		gap: var(--s-3);
		inline-size: 100%;
		padding: var(--s-2);
		border: 0;
		border-radius: var(--r-md);
		background: transparent;
		color: var(--text-3);
		text-align: start;
	}
	.run:disabled {
		cursor: default;
		opacity: 1;
	}
	.run:not(:disabled):hover {
		background: var(--surface-2);
	}
	.run[aria-expanded='true'] > :global(svg) {
		rotate: 180deg;
	}
	.dot {
		flex-shrink: 0;
		inline-size: 8px;
		block-size: 8px;
		border-radius: var(--r-pill);
		background: var(--text-3);
	}
	.dot.good {
		background: oklch(68% 0.14 150);
	}
	.dot.bad {
		background: var(--danger);
	}
	.dot.busy {
		background: var(--accent);
		animation: pulse 1.2s ease-in-out infinite;
	}
	.text {
		display: flex;
		flex-direction: column;
		flex: 1;
		min-inline-size: 0;
	}
	.line {
		overflow: hidden;
		color: var(--text);
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.line b {
		font-weight: var(--fw-medium);
	}
	small {
		font-size: var(--fs-xs);
		color: var(--text-2);
	}
	small.bad {
		color: var(--danger);
	}
	.details {
		display: flex;
		flex-direction: column;
		gap: var(--s-2);
		padding: 0 var(--s-2) var(--s-3) calc(var(--s-2) + 8px + var(--s-3));
		font-size: var(--fs-sm);
	}
	.details p {
		margin: 0;
		color: var(--text-2);
	}
	ol {
		gap: var(--s-2);
	}
	ol li {
		display: flex;
		flex-direction: column;
	}
	ol li.not_run span {
		color: var(--text-3);
	}
	ol li.failed small {
		color: var(--danger);
	}
	.none {
		margin: 0;
		color: var(--text-2);
	}
	@keyframes pulse {
		50% {
			opacity: 0.35;
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.dot.busy {
			animation: none;
		}
	}
</style>
