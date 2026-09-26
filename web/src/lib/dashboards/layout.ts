// A Dashboard's items (ADR 0009): an ordered list of sized items that the grid packs row by row.
import type { Device, Group } from '../api';
import { SECTIONS } from '../present';
import type { DashboardItem, DashboardItemKind } from '../types';

/** The sizes each kind comes in, the first being its default. Mirrors engine/dashboards.py. */
export const SIZES: { [K in DashboardItemKind]: Extract<DashboardItem, { kind: K }>['size'][] } = {
	tile: ['2x1', '1x1', '2x2'],
	heading: ['full', '4x1', '2x1', '1x1'],
	spacer: ['1x1', '2x1', '4x1']
};

export const SIZE_LABEL: Record<string, string> = {
	full: 'Full width',
	'4x1': 'Extra wide',
	'2x1': 'Wide',
	'1x1': 'Small',
	'2x2': 'Large'
};

/** Grid columns by the Dashboard's own width: phone, tablet, desktop. */
export function columnsFor(width: number): 4 | 6 | 8 {
	return width < 560 ? 4 : width < 900 ? 6 : 8;
}

/** How many columns an item spans: never more than the grid has. */
export function spanOf(item: DashboardItem, columns: number): number {
	if (item.size === 'full') return columns;
	return Math.min(Number(item.size.split('x')[0]), columns);
}

/** How many rows an item spans. */
export function rowsOf(item: DashboardItem): number {
	return item.size === 'full' ? 1 : Number(item.size.split('x')[1]);
}

/** A new item id. Not crypto.randomUUID: phones reach Control over plain http, where it's missing. */
export function newId(): string {
	return Math.random().toString(36).slice(2, 10);
}

export function tileItem(target: string, size: '2x1' | '1x1' | '2x2' = '2x1'): DashboardItem {
	return { id: newId(), kind: 'tile', size, target };
}

/** "Start from Home": Home's Groups and Category sections, each under its heading. */
export function homeItems(groups: Group[], controllable: Device[]): DashboardItem[] {
	const sections = [
		{ title: 'Groups', uids: groups.map((g) => g.uid) },
		...SECTIONS.map((s) => ({
			title: s.title,
			uids: controllable.filter((d) => d.category === s.category).map((d) => d.uid)
		}))
	];
	return sections
		.filter((s) => s.uids.length)
		.flatMap((s) => [
			{ id: newId(), kind: 'heading' as const, size: 'full' as const, text: s.title },
			...s.uids.map((uid) => tileItem(uid))
		]);
}

/** The list with one item moved to another place. */
export function moveItem<T>(items: T[], from: number, to: number): T[] {
	if (from === to || from < 0 || to < 0 || from >= items.length || to >= items.length) return items;
	const next = [...items];
	const [moved] = next.splice(from, 1);
	next.splice(to, 0, moved);
	return next;
}
