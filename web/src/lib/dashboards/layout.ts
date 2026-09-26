// A Dashboard's grid (ADR 0010): each item sits at its own cell, and nothing moves by itself.
// Dropping or growing an item where others are pushes them down just enough, and what's under them moves along.
import type { Device, Group } from '../api';
import { SECTIONS } from '../present';
import type { DashboardItem, DashboardItemKind, NewDashboardItem } from '../types';

export type Columns = 4 | 6 | 8;

/** The sizes each kind comes in. Mirrors engine/dashboards.py. */
export const SIZES: { [K in DashboardItemKind]: Extract<DashboardItem, { kind: K }>['size'][] } = {
	tile: ['1x1', '2x1', '2x2'],
	heading: ['full', '4x1', '2x1', '1x1']
};

export const SIZE_LABEL: Record<string, string> = {
	full: 'Full width',
	'4x1': 'Extra wide',
	'2x1': 'Wide',
	'1x1': 'Small',
	'2x2': 'Large'
};

export const COLUMNS: { value: Columns; label: string }[] = [
	{ value: 4, label: 'Phone' },
	{ value: 6, label: 'Tablet' },
	{ value: 8, label: 'Desktop' }
];

/** The narrowest a column may get before the Dashboard shows in reading order instead. */
export const MIN_CELL = 64;

/** The width a new Dashboard gets on this screen. */
export function columnsFor(screenWidth: number): Columns {
	return screenWidth < 560 ? 4 : screenWidth < 900 ? 6 : 8;
}

/** Whether a grid this many columns wide fits this width without cramming. */
export function fits(columns: number, width: number, gap = 12): boolean {
	return width >= columns * MIN_CELL + (columns - 1) * gap;
}

/** The (w, h) an item takes in grid cells. A row is half a Tile tall: a Tile is 2 rows, a Heading 1. */
export function cellsOf(item: NewDashboardItem, columns: number): { w: number; h: number } {
	if (item.size === 'full') return { w: columns, h: 1 };
	const [w, h] = item.size.split('x').map(Number);
	return { w: Math.min(w, columns), h: item.kind === 'tile' ? h * 2 : 1 };
}

function collide(a: DashboardItem, b: DashboardItem, columns: number): boolean {
	const ca = cellsOf(a, columns);
	const cb = cellsOf(b, columns);
	return a.x < b.x + cb.w && b.x < a.x + ca.w && a.y < b.y + cb.h && b.y < a.y + ca.h;
}

/** Push whatever `moved` lands on down below it, and so on for what those land on. */
function pushDown(items: DashboardItem[], moved: DashboardItem, columns: number) {
	const below = items.filter((o) => o !== moved).sort((a, b) => a.y - b.y || a.x - b.x);
	for (const other of below) {
		if (!collide(moved, other, columns)) continue;
		other.y = moved.y + cellsOf(moved, columns).h;
		pushDown(items, other, columns);
	}
}

function clampX(item: DashboardItem, columns: number) {
	item.x = Math.max(0, Math.min(item.x, columns - cellsOf(item, columns).w));
	item.y = Math.max(0, item.y);
}

/** The items with one of them changed (moved and/or resized); what it now covers is pushed down. */
export function place(
	items: DashboardItem[],
	id: string,
	change: Partial<Pick<DashboardItem, 'x' | 'y' | 'size'>>,
	columns: number
): DashboardItem[] {
	const next = items.map((i) => ({ ...i }));
	const moved = next.find((i) => i.id === id);
	if (!moved) return items;
	Object.assign(moved, change);
	clampX(moved, columns);
	pushDown(next, moved, columns);
	return next;
}

/** The items on a grid of another width: those that no longer fit move left, and down below whatever is there. */
export function withColumns(items: DashboardItem[], columns: number): DashboardItem[] {
	const next = items.map((i) => ({ ...i })).sort((a, b) => a.y - b.y || a.x - b.x);
	const settled: DashboardItem[] = [];
	for (const item of next) {
		clampX(item, columns);
		let hits = settled.filter((s) => collide(item, s, columns));
		while (hits.length) {
			item.y = Math.max(...hits.map((s) => s.y + cellsOf(s, columns).h));
			hits = settled.filter((s) => collide(item, s, columns));
		}
		settled.push(item);
	}
	return settled;
}

/** The first row under every item. */
export function bottomOf(items: DashboardItem[], columns: number): number {
	return Math.max(0, ...items.map((i) => i.y + cellsOf(i, columns).h));
}

/** New items placed under everything, side by side while they fit. Gaps the user left stay gaps. */
export function addBelow(items: DashboardItem[], added: NewDashboardItem[], columns: number): DashboardItem[] {
	return [...items, ...pack(added, columns, bottomOf(items, columns))];
}

/** Items laid out left to right, row by row, from row `top`. */
export function pack(added: NewDashboardItem[], columns: number, top = 0): DashboardItem[] {
	const out: DashboardItem[] = [];
	let x = 0;
	let y = top;
	let rowH = 0;
	for (const item of added) {
		const { w, h } = cellsOf(item, columns);
		if (x + w > columns) {
			x = 0;
			y += rowH;
			rowH = 0;
		}
		out.push({ ...item, x, y } as DashboardItem);
		x += w;
		rowH = Math.max(rowH, h);
	}
	return out;
}

/** Row by row, left to right: how a Dashboard shows on a screen too narrow for its columns. */
export function readingOrder(items: DashboardItem[]): DashboardItem[] {
	return [...items].sort((a, b) => a.y - b.y || a.x - b.x);
}

/** A new item id. Not crypto.randomUUID: phones reach Control over plain http, where it's missing. */
export function newId(): string {
	return Math.random().toString(36).slice(2, 10);
}

export function tileItem(target: string, size: '2x1' | '1x1' | '2x2' = '2x1'): NewDashboardItem {
	return { id: newId(), kind: 'tile', size, target };
}

/** "A copy of Home": Home's Groups and Category sections, each under its heading. */
export function homeItems(groups: Group[], controllable: Device[], columns: number): DashboardItem[] {
	const sections = [
		{ title: 'Groups', uids: groups.map((g) => g.uid) },
		...SECTIONS.map((s) => ({
			title: s.title,
			uids: controllable.filter((d) => d.category === s.category).map((d) => d.uid)
		}))
	];
	let top = 0;
	return sections
		.filter((s) => s.uids.length)
		.flatMap((s) => {
			const heading: NewDashboardItem = { id: newId(), kind: 'heading', size: 'full', text: s.title };
			const placed = pack([heading, ...s.uids.map((uid) => tileItem(uid))], columns, top);
			top = bottomOf(placed, columns);
			return placed;
		});
}

/** The list with one item moved to another place (the Dashboards list's order). */
export function moveItem<T>(items: T[], from: number, to: number): T[] {
	if (from === to || from < 0 || to < 0 || from >= items.length || to >= items.length) return items;
	const next = [...items];
	const [moved] = next.splice(from, 1);
	next.splice(to, 0, moved);
	return next;
}
