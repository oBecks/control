// The Automations the Engine keeps, for the Automations pages.
import { api, type AutomationDraft } from '$lib/api';
import { home } from '$lib/home.svelte';
import type { Automation, Run } from '$lib/types';

const POLL_MS = 8000;
/** While a Run is going, its steps are followed more closely. */
const RUNNING_POLL_MS = 2000;

class Automations {
	list = $state<Automation[]>([]);
	loaded = $state(false);

	async load() {
		try {
			this.list = await api.automations();
			this.loaded = true;
		} catch {
			// The layout already says when the Engine is unreachable.
		}
	}

	/** Keep the list fresh while a page shows it: faster while something runs. */
	start() {
		let timer: ReturnType<typeof setTimeout>;
		let stopped = false;
		const visible = () => document.visibilityState === 'visible';
		const tick = async (first = false) => {
			clearTimeout(timer);
			if (first || visible()) await this.load();
			if (stopped) return;
			// A tick that started meanwhile (the page became visible) scheduled one already: keep a single chain.
			clearTimeout(timer);
			timer = setTimeout(tick, this.list.some((a) => a.running) ? RUNNING_POLL_MS : POLL_MS);
		};
		const onVisible = () => visible() && tick();
		tick(true);
		document.addEventListener('visibilitychange', onVisible);
		return () => {
			stopped = true;
			clearTimeout(timer);
			document.removeEventListener('visibilitychange', onVisible);
		};
	}

	get(uid: string) {
		return this.list.find((a) => a.uid === uid);
	}

	#put(a: Automation) {
		this.list = this.list.some((x) => x.uid === a.uid)
			? this.list.map((x) => (x.uid === a.uid ? a : x))
			: [...this.list, a];
	}

	/** Create (uid null) or change one; returns it, or null if the Engine refused (already said). */
	async save(uid: string | null, draft: AutomationDraft): Promise<Automation | null> {
		try {
			const saved = uid ? await api.patchAutomation(uid, draft) : await api.addAutomation(draft);
			this.#put(saved);
			return saved;
		} catch (e) {
			home.notify(message(e));
			return null;
		}
	}

	async setEnabled(uid: string, enabled: boolean) {
		const before = this.get(uid);
		if (before) this.#put({ ...before, enabled });
		try {
			this.#put(await api.patchAutomation(uid, { enabled }));
		} catch (e) {
			if (before) this.#put(before);
			home.notify(message(e));
		}
	}

	async run(uid: string): Promise<Run | null> {
		try {
			const run = await api.runAutomation(uid);
			const a = this.get(uid);
			if (a) this.#put({ ...a, running: true, last_run: run });
			return run;
		} catch (e) {
			home.notify(message(e));
			return null;
		}
	}

	async remove(uid: string): Promise<boolean> {
		try {
			await api.deleteAutomation(uid);
			this.list = this.list.filter((a) => a.uid !== uid);
			return true;
		} catch (e) {
			home.notify(message(e));
			return false;
		}
	}
}

function message(e: unknown) {
	return e instanceof Error ? e.message : String(e);
}

export const automations = new Automations();
