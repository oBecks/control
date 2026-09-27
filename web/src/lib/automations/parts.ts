// Automations in the UI: days, times and Run outcomes in words. The Engine checks and labels every
// part (engine/automations.py); this only shapes the builder's forms and the history.
import type { RunOutcome, Weekday } from '$lib/types';

export const EVERY_DAY: Weekday[] = [0, 1, 2, 3, 4, 5, 6];

/** The week in the order this browser's language starts it (Sunday in Israel and the US). */
export function weekOrder(language = navigator.language): Weekday[] {
	let first = 1; // Monday, as Intl counts (1-7)
	try {
		const locale = new Intl.Locale(language) as Intl.Locale & {
			weekInfo?: { firstDay: number };
			getWeekInfo?: () => { firstDay: number };
		};
		first = (locale.getWeekInfo?.() ?? locale.weekInfo)?.firstDay ?? 1;
	} catch {
		// An unknown language: Monday.
	}
	const start = (first - 1) as Weekday; // Intl's Monday is 1, Control's is 0
	return EVERY_DAY.map((d) => ((d + start) % 7) as Weekday);
}

/** Short day names in the browser's language, by Control's weekday number. */
export function dayNames(language = navigator.language): string[] {
	// 2024-01-01 was a Monday.
	const fmt = new Intl.DateTimeFormat(language, { weekday: 'short' });
	return EVERY_DAY.map((d) => fmt.format(new Date(2024, 0, 1 + d)));
}

/** A wait's seconds as hours, minutes and seconds, and back. */
export function splitSeconds(total: number): { h: number; m: number; s: number } {
	return { h: Math.floor(total / 3600), m: Math.floor((total % 3600) / 60), s: total % 60 };
}

export function joinSeconds(t: { h: number; m: number; s: number }): number {
	return (t.h || 0) * 3600 + (t.m || 0) * 60 + (t.s || 0);
}

export const OUTCOMES: Record<RunOutcome, { label: string; tone: 'good' | 'bad' | 'quiet' | 'busy' }> = {
	running: { label: 'Running', tone: 'busy' },
	succeeded: { label: 'Done', tone: 'good' },
	partly_failed: { label: 'Partly failed', tone: 'bad' },
	skipped: { label: 'Skipped: Only if not met', tone: 'quiet' },
	missed: { label: 'Missed: the PC was off or asleep', tone: 'quiet' },
	interrupted: { label: "Interrupted: didn't finish", tone: 'bad' },
	restarted: { label: 'Started again', tone: 'quiet' }
};

/** "Today 07:00", "Yesterday 22:30", "Mon 07:00", or a date further back or ahead. */
export function when(seconds: number, now = new Date(), language = navigator.language): string {
	const at = new Date(seconds * 1000);
	// 24-hour, like the times in the Engine's sentences ("At 07:00, every day").
	const time = at.toLocaleTimeString(language, { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
	const day = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
	const days = Math.round((day(at) - day(now)) / 86_400_000);
	if (days === 0) return `Today ${time}`;
	if (days === -1) return `Yesterday ${time}`;
	if (days === 1) return `Tomorrow ${time}`;
	if (Math.abs(days) < 7) return `${at.toLocaleDateString(language, { weekday: 'short' })} ${time}`;
	return `${at.toLocaleDateString(language, { day: 'numeric', month: 'short' })} ${time}`;
}
