<script lang="ts">
	// Settings → Assistant (ADR 0005): Connect Claude writes Claude Desktop's config so Claude starts
	// Control's MCP server; Claude Code gets a command to paste. Only on the computer running Control,
	// since both are about that computer's programs.
	import { Check, Copy } from '@lucide/svelte';
	import { api, type Assistant } from '$lib/api';
	import { home } from '$lib/home.svelte';
	import Button from '$lib/ui/Button.svelte';

	let status = $state<Assistant | null>(null);
	let busy = $state(false);
	/** Claude reads its config when it starts. */
	let restart = $state(false);
	let copied = $state(false);

	$effect(() => {
		api.assistant().then(
			(s) => (status = s),
			() => {} // the layout already tells the user when the Engine is unreachable
		);
	});

	async function setConnected(on: boolean) {
		busy = true;
		try {
			status = await (on ? api.connectClaude() : api.disconnectClaude());
			restart = true;
		} catch (e) {
			home.notify(e instanceof Error ? e.message : String(e));
		} finally {
			busy = false;
		}
	}

	async function dismiss() {
		try {
			status = await api.dismissRestartNote();
		} catch (e) {
			home.notify(e instanceof Error ? e.message : String(e));
		}
	}

	async function copyCommand() {
		if (!status) return;
		try {
			await navigator.clipboard.writeText(status.claude_code_command);
			copied = true;
			setTimeout(() => (copied = false), 2000);
		} catch {
			home.notify('Couldn’t copy. Select the command and copy it instead.');
		}
	}
</script>

{#if status?.can_change}
	<section>
		<h2>Assistant</h2>
		<p class="lead">
			Ask Claude to turn things on and off, dim the lights or set the AC. It sees and controls your devices; setting
			them up stays here.
		</p>

		<div class="row">
			<span class="what">
				<strong>Claude Desktop</strong>
				<small>
					{#if status.claude_desktop === 'missing'}
						Not installed on this computer
					{:else if status.claude_desktop === 'connected'}
						Connected
					{:else if status.claude_desktop === 'outdated'}
						Connected to another copy of Control
					{:else}
						Not connected
					{/if}
				</small>
			</span>
			{#if status.claude_desktop === 'connected'}
				<Button size="sm" variant="ghost" disabled={busy} onclick={() => setConnected(false)}>Disconnect</Button>
			{:else if status.claude_desktop !== 'missing'}
				<Button size="sm" variant="primary" disabled={busy} onclick={() => setConnected(true)}>
					{status.claude_desktop === 'outdated' ? 'Connect again' : 'Connect Claude'}
				</Button>
			{/if}
		</div>
		{#if restart}
			<p class="note" role="status">Quit Claude from its tray icon and open it again to apply this.</p>
		{:else if status.restart_claude}
			<div class="note updated" role="status">
				<p>
					Control was updated to {status.restart_claude}. Quit Claude from its tray icon and open it again to get the
					new Assistant tools.
				</p>
				<Button size="sm" variant="ghost" onclick={dismiss}>Dismiss</Button>
			</div>
		{/if}

		<div class="code">
			<span class="what">
				<strong>Claude Code</strong>
				<small>Run this once in a terminal:</small>
			</span>
			<div class="command">
				<code>{status.claude_code_command}</code>
				<Button size="sm" variant="ghost" onclick={copyCommand} aria-label="Copy the command">
					{#if copied}<Check size={16} strokeWidth={2.3} />{:else}<Copy size={16} strokeWidth={2.3} />{/if}
				</Button>
			</div>
		</div>
		<p class="hint">
			Claude asks you before it changes anything, unless you tell it not to. Other assistants that support MCP can run
			the same command.
		</p>
	</section>
{/if}

<style>
	section {
		display: flex;
		flex-direction: column;
		gap: var(--s-3);
	}
	h2 {
		margin: 0;
		font-size: var(--fs-lg);
	}
	p {
		margin: 0;
	}
	.lead {
		color: var(--text-2);
	}
	.hint {
		color: var(--text-2);
		font-size: var(--fs-sm);
	}
	.row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--s-4);
	}
	.what {
		display: flex;
		flex-direction: column;
	}
	.what small {
		color: var(--text-2);
		font-size: var(--fs-sm);
	}
	.note {
		padding: var(--s-3) var(--s-4);
		border-radius: var(--r-lg);
		border: 1px solid color-mix(in oklab, var(--accent) 45%, var(--border));
		background: color-mix(in oklab, var(--accent) 14%, var(--surface));
		font-size: var(--fs-sm);
	}
	.updated {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--s-3);
	}
	.code {
		display: flex;
		flex-direction: column;
		gap: var(--s-2);
	}
	.command {
		display: flex;
		align-items: center;
		gap: var(--s-2);
		padding-inline-start: var(--s-3);
		border-radius: var(--r-md);
		border: 1px solid var(--border);
		background: var(--surface);
	}
	code {
		flex: 1;
		min-inline-size: 0;
		padding-block: var(--s-2);
		overflow-wrap: break-word;
		font-size: var(--fs-sm);
	}
</style>
