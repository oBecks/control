<script lang="ts">
	import { ChevronRight } from '@lucide/svelte';
	import type { Hotkey } from '$lib/types';
	import { keyCaps } from './keys';

	interface Props {
		list: Hotkey[];
		/** Say which Device or Group each one is for (Settings lists them all). */
		showTarget?: boolean;
		onopen: (uid: string) => void;
	}

	let { list, showTarget = false, onopen }: Props = $props();
</script>

<ul>
	{#each list as h (h.uid)}
		<li>
			<button type="button" class="row" onclick={() => onopen(h.uid)}>
				<span class="caps">
					{#each keyCaps(h.keys) as k, i (i)}<kbd>{k}</kbd>{/each}
				</span>
				<span class="text">
					<span class="does">{showTarget ? `${h.target_name}: ${h.action_label}` : h.action_label}</span>
					{#if h.status === 'taken'}
						<span class="problem">Another app has these keys</span>
					{:else if h.made_by === 'assistant'}
						<span class="note">Made by the Assistant</span>
					{/if}
				</span>
				<ChevronRight size={16} strokeWidth={2.4} />
			</button>
		</li>
	{/each}
</ul>

<style>
	ul {
		display: flex;
		flex-direction: column;
		gap: var(--s-1);
		margin: 0;
		padding: 0;
		list-style: none;
	}
	.row {
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
		transition: background-color var(--dur-fast) var(--ease);
	}
	.row:hover {
		background: var(--surface-2);
	}
	.caps {
		display: flex;
		flex-shrink: 0;
		gap: 3px;
	}
	kbd {
		min-inline-size: 26px;
		padding: 2px 6px;
		border-radius: var(--r-sm);
		border: 1px solid var(--border);
		border-block-end-width: 2px;
		background: var(--surface);
		color: var(--text);
		font-family: inherit;
		font-size: var(--fs-xs);
		font-weight: var(--fw-bold);
		text-align: center;
	}
	.text {
		display: flex;
		flex-direction: column;
		flex: 1;
		min-inline-size: 0;
	}
	.does {
		overflow: hidden;
		color: var(--text);
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.note,
	.problem {
		font-size: var(--fs-xs);
		color: var(--text-2);
	}
	.problem {
		color: var(--danger);
	}
	:global([dir='rtl']) .row > :global(svg:last-child) {
		transform: scaleX(-1);
	}
</style>
