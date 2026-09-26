// The Hotkeys the Engine keeps, for the Hotkeys page and each Device's and Group's controls.
import { api, type HotkeyList } from '$lib/api';
import { home } from '$lib/home.svelte';
import type { Hotkey, HotkeyAction } from '$lib/types';

class Hotkeys {
	list = $state<Hotkey[]>([]);
	/** The Desktop App is running, so Hotkeys work. */
	listening = $state(false);
	/** Only the computer running Control sets Hotkeys up. */
	canChange = $state(false);
	loaded = $state(false);

	#take(body: HotkeyList) {
		this.list = body.hotkeys;
		this.listening = body.listening;
		this.canChange = body.can_change;
		this.loaded = true;
	}

	async load() {
		try {
			this.#take(await api.hotkeys());
		} catch {
			// The layout already says when the Engine is unreachable.
		}
	}

	forTarget(uid: string) {
		return this.list.filter((h) => h.target === uid);
	}

	/** Create (uid null) or change a Hotkey; returns it, or null if the Engine refused (already said). */
	async save(uid: string | null, keys: string, target: string, action: HotkeyAction): Promise<Hotkey | null> {
		try {
			const saved = uid
				? await api.patchHotkey(uid, { keys, target, action })
				: await api.addHotkey(keys, target, action);
			this.list = uid ? this.list.map((h) => (h.uid === uid ? saved : h)) : [...this.list, saved];
			if (saved.status === 'taken') home.notify(`Another app has ${saved.keys}: pick other keys`);
			return saved;
		} catch (e) {
			home.notify(e instanceof Error ? e.message : String(e));
			return null;
		}
	}

	async remove(uid: string): Promise<boolean> {
		try {
			await api.deleteHotkey(uid);
			this.list = this.list.filter((h) => h.uid !== uid);
			return true;
		} catch (e) {
			home.notify(e instanceof Error ? e.message : String(e));
			return false;
		}
	}
}

export const hotkeys = new Hotkeys();
