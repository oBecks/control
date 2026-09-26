// The Dashboards the Engine keeps (ADR 0010), shared by the Dashboards list and each Dashboard.
import { api } from '$lib/api';
import { home } from '$lib/home.svelte';
import type { Dashboard, DashboardItem } from '$lib/types';

const POLL_MS = 8000;
/** This browser's "open to" Dashboard. Kept in the browser, so each one (even a phone's Home Screen app) picks its own. */
const OPEN_TO_KEY = 'control.openTo';

class Dashboards {
	list = $state<Dashboard[]>([]);
	loaded = $state(false);
	/** The Dashboard this browser opens to instead of Home, if any. */
	openTo = $state<string | null>(readOpenTo());
	/** A Dashboard just made empty: it opens ready to arrange. */
	arrangeOnOpen = $state<string | null>(null);

	/** Bumped by each change made here, so a reading that left before it doesn't undo it. */
	#changes = 0;
	#pending = 0;

	async load() {
		const changes = this.#changes;
		try {
			const list = await api.dashboards();
			if (changes !== this.#changes || this.#pending) return;
			this.list = list;
			this.loaded = true;
		} catch {
			// The layout already says when the Engine is unreachable.
		}
	}

	/** Keep the list live while a Dashboards screen is showing: another browser may change it. */
	start() {
		const visible = () => document.visibilityState === 'visible';
		this.load();
		const timer = setInterval(() => visible() && this.load(), POLL_MS);
		const onVisible = () => visible() && this.load();
		document.addEventListener('visibilitychange', onVisible);
		return () => {
			clearInterval(timer);
			document.removeEventListener('visibilitychange', onVisible);
		};
	}

	get(uid: string) {
		return this.list.find((d) => d.uid === uid);
	}

	/** Make a Dashboard; returns it, or null if the Engine refused (already said). */
	async create(name: string, columns: number, items: DashboardItem[]): Promise<Dashboard | null> {
		return this.#run(async () => {
			const d = await api.addDashboard(name.trim(), columns, items);
			this.list = [...this.list, d];
			return d;
		});
	}

	/** Change a Dashboard: shown at once, the Engine's answer taken as truth, undone if it refuses. */
	async save(uid: string, patch: { name?: string; columns?: 4 | 6 | 8; items?: DashboardItem[] }): Promise<boolean> {
		const before = this.get(uid);
		if (!before) return false;
		this.list = this.list.map((d) => (d.uid === uid ? { ...d, ...patch } : d));
		const saved = await this.#run(async () => {
			const d = await api.patchDashboard(uid, patch);
			this.list = this.list.map((x) => (x.uid === uid ? d : x));
			return d;
		});
		if (!saved) this.list = this.list.map((d) => (d.uid === uid ? before : d));
		return !!saved;
	}

	async remove(uid: string): Promise<boolean> {
		const done = await this.#run(async () => {
			await api.deleteDashboard(uid);
			this.list = this.list.filter((d) => d.uid !== uid);
			return true;
		});
		if (done && this.openTo === uid) this.setOpenTo(null);
		return !!done;
	}

	async order(uids: string[]) {
		const before = this.list;
		this.list = uids.flatMap((u) => before.filter((d) => d.uid === u));
		const list = await this.#run(() => api.orderDashboards(uids));
		this.list = list ?? before;
	}

	setOpenTo(uid: string | null) {
		this.openTo = uid;
		try {
			if (uid) localStorage.setItem(OPEN_TO_KEY, uid);
			else localStorage.removeItem(OPEN_TO_KEY);
		} catch {
			// Storage blocked (private mode): it holds for this visit only.
		}
	}

	async #run<T>(change: () => Promise<T>): Promise<T | null> {
		this.#changes++;
		this.#pending++;
		try {
			return await change();
		} catch (e) {
			home.notify(e instanceof Error ? e.message : String(e));
			return null;
		} finally {
			this.#pending--;
		}
	}
}

function readOpenTo(): string | null {
	try {
		return localStorage.getItem(OPEN_TO_KEY);
	} catch {
		return null;
	}
}

export const dashboards = new Dashboards();
