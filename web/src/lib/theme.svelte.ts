export type ThemePreference = 'system' | 'light' | 'dark';

const KEY = 'control.theme';

function load(): ThemePreference {
	try {
		const v = localStorage.getItem(KEY);
		if (v === 'light' || v === 'dark') return v;
	} catch {
		// storage blocked: fall back to following the system
	}
	return 'system';
}

class Theme {
	preference = $state<ThemePreference>(load());

	set(pref: ThemePreference) {
		this.preference = pref;
		try {
			localStorage.setItem(KEY, pref);
		} catch {
			// not persisted; still applies for this session
		}
	}

	apply() {
		const root = document.documentElement;
		if (this.preference === 'system') root.removeAttribute('data-theme');
		else root.dataset.theme = this.preference;
		// The phone's status bar follows the theme too (app.html has one theme-color per scheme).
		for (const meta of document.querySelectorAll<HTMLMetaElement>('meta[name="theme-color"]')) {
			const scheme = meta.dataset.scheme ?? meta.media.match(/light|dark/)?.[0];
			if (!scheme) continue;
			meta.dataset.scheme = scheme;
			meta.media =
				this.preference === 'system'
					? `(prefers-color-scheme: ${scheme})`
					: scheme === this.preference
						? 'all'
						: 'not all';
		}
	}
}

export const theme = new Theme();
