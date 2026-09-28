// The People (ADR 0014), shared by the Automation builder and the Dashboard's Who's home. Presence
// changes on its own, so whoever shows it asks for fresh readings while it's on screen (`watch`).
import { api } from '$lib/api';
import type { Person } from '$lib/types';

const POLL_MS = 15_000;

class People {
	list = $state<Person[]>([]);
	loaded = $state(false);
	#watchers = 0;
	#timer: ReturnType<typeof setInterval> | undefined;

	/** People Control can tell are home or away: those with a phone. */
	get tracked() {
		return this.list.filter((p) => p.phones.length);
	}

	async refresh() {
		try {
			this.list = await api.people();
			this.loaded = true;
		} catch {
			// The layout already tells the user when the Engine is unreachable.
		}
	}

	/** Keep the list fresh while something shows it; call the returned function to stop. */
	watch(): () => void {
		this.refresh();
		if (this.#watchers++ === 0) {
			this.#timer = setInterval(() => document.visibilityState === 'visible' && this.refresh(), POLL_MS);
		}
		return () => {
			if (--this.#watchers === 0) clearInterval(this.#timer);
		};
	}
}

export const people = new People();
