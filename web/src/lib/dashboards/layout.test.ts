import { describe, expect, it } from 'vitest';
import type { Device, Group } from '../api';
import type { DashboardItem } from '../types';
import {
	addBelow,
	cellsOf,
	columnsFor,
	fits,
	homeItems,
	moveItem,
	place,
	readingOrder,
	tileLook,
	withColumns
} from './layout';

const device = (uid: string, category: string) => ({ uid, category }) as Device;
const group = (uid: string) => ({ uid }) as Group;
const tile = (id: string, x: number, y: number, w = 2, h = 2): DashboardItem => ({
	id,
	kind: 'tile',
	w,
	h,
	target: id,
	x,
	y
});
const heading = (id: string, x: number, y: number, w = 2): DashboardItem => ({
	id,
	kind: 'heading',
	w,
	h: 1,
	text: id,
	align: 'start',
	text_size: 'm',
	bold: true,
	x,
	y
});
const at = (items: DashboardItem[]) => Object.fromEntries(items.map((i) => [i.id, [i.x, i.y]]));

describe('the grid', () => {
	it('gives a new Dashboard 4 columns on a phone, 6 on a tablet and 8 on desktop', () => {
		expect([columnsFor(375), columnsFor(700), columnsFor(1100)]).toEqual([4, 6, 8]);
	});

	it('never makes an item wider than the grid', () => {
		expect(cellsOf(tile('a', 0, 0, 3, 5), 8)).toEqual({ w: 3, h: 5 });
		expect(cellsOf(heading('h', 0, 0, 8), 6)).toEqual({ w: 6, h: 1 });
	});

	it('gives a Tile the small look at one column and the large look from four rows', () => {
		expect([tileLook({ w: 1, h: 6 }), tileLook({ w: 3, h: 2 }), tileLook({ w: 2, h: 4 })]).toEqual([
			'small',
			'normal',
			'large'
		]);
	});

	it('knows when a screen is too narrow for a Dashboard', () => {
		expect(fits(4, 343)).toBe(true);
		expect(fits(8, 343)).toBe(false);
	});
});

describe('place', () => {
	it('puts an item exactly where it is dropped, leaving gaps alone', () => {
		const items = [tile('a', 0, 0), tile('b', 4, 0)];
		expect(at(place(items, 'a', { x: 2, y: 6 }, 8))).toEqual({ a: [2, 6], b: [4, 0] });
	});

	it('pushes what it lands on down, and what that lands on too', () => {
		const items = [heading('h', 0, 0), tile('a', 0, 1), tile('b', 0, 3), tile('c', 4, 0)];
		// A Tile dropped on the heading: the heading goes under it, then a and b under that.
		expect(at(place(items, 'c', { x: 0, y: 0 }, 8))).toEqual({ h: [0, 2], a: [0, 3], b: [0, 5], c: [0, 0] });
	});

	it('pushes down what a Tile grows over', () => {
		const items = [tile('a', 0, 0), tile('b', 0, 2), tile('c', 2, 0)];
		expect(at(place(items, 'a', { h: 4 }, 8))).toEqual({ a: [0, 0], b: [0, 4], c: [2, 0] });
		expect(at(place(items, 'a', { w: 3 }, 8))).toEqual({ a: [0, 0], b: [0, 2], c: [2, 2] });
	});

	it('keeps an item inside the grid and its size within bounds', () => {
		expect(at(place([tile('a', 0, 0)], 'a', { x: 7, y: -3 }, 8))).toEqual({ a: [6, 0] });
		const [shrunk] = place([tile('a', 0, 0)], 'a', { w: 12, h: 1 }, 8);
		expect([shrunk.w, shrunk.h]).toEqual([8, 2]);
	});

	it('leaves the original list untouched', () => {
		const items = [tile('a', 0, 0), tile('b', 0, 2)];
		place(items, 'b', { y: 0 }, 8);
		expect(at(items)).toEqual({ a: [0, 0], b: [0, 2] });
	});
});

describe('withColumns', () => {
	it('moves items that no longer fit left, pushing down what they land on', () => {
		const items = [tile('a', 0, 0), tile('b', 6, 0)];
		expect(at(withColumns(items, 4))).toEqual({ a: [0, 0], b: [2, 0] });
		const crowded = [tile('a', 2, 0), tile('b', 6, 0)];
		expect(at(withColumns(crowded, 4))).toEqual({ a: [2, 0], b: [2, 2] });
	});
});

describe('addBelow', () => {
	it('adds under everything, side by side while they fit', () => {
		const items = [tile('a', 0, 0), tile('b', 6, 4)];
		const added = addBelow(items, [tile('c', 0, 0), tile('d', 0, 0), tile('e', 0, 0)], 4);
		expect(at(added)).toEqual({ a: [0, 0], b: [6, 4], c: [0, 6], d: [2, 6], e: [0, 8] });
	});
});

describe('readingOrder', () => {
	it('reads row by row, left to right', () => {
		const items = [tile('b', 2, 1), heading('h', 0, 0), tile('a', 0, 1)];
		expect(readingOrder(items).map((i) => i.id)).toEqual(['h', 'a', 'b']);
	});
});

describe('homeItems', () => {
	it('copies Home: Groups first, then each Category under its heading, empty ones left out', () => {
		const items = homeItems(
			[group('group:1')],
			[device('plug:1', 'plug'), device('light:1', 'light'), device('light:2', 'light'), device('light:3', 'light')],
			4
		);
		const read = items.map((i) => [i.kind === 'heading' ? `# ${i.text}` : i.target, i.x, i.y]);
		expect(read).toEqual([
			['# Groups', 0, 0],
			['group:1', 0, 1],
			['# Lights', 0, 3],
			['light:1', 0, 4],
			['light:2', 2, 4],
			['light:3', 0, 6],
			['# Plugs', 0, 8],
			['plug:1', 0, 9]
		]);
		expect(new Set(items.map((i) => i.id)).size).toBe(items.length);
	});
});

describe('moveItem', () => {
	it('moves forward and back', () => {
		expect(moveItem(['a', 'b', 'c', 'd'], 0, 2)).toEqual(['b', 'c', 'a', 'd']);
		expect(moveItem(['a', 'b', 'c', 'd'], 3, 1)).toEqual(['a', 'd', 'b', 'c']);
	});

	it('leaves the list alone for a move nowhere', () => {
		const list = ['a', 'b'];
		expect(moveItem(list, 1, 1)).toBe(list);
		expect(moveItem(list, 0, 5)).toBe(list);
	});
});
