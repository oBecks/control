import { describe, expect, it } from 'vitest';
import type { Device, Group } from '../api';
import type { DashboardItem } from '../types';
import { columnsFor, homeItems, moveItem, spanOf } from './layout';

const device = (uid: string, category: string) => ({ uid, category }) as Device;
const group = (uid: string) => ({ uid }) as Group;

describe('the grid', () => {
	it('has 4 columns on a phone, 6 on a tablet and 8 on desktop', () => {
		expect([columnsFor(375), columnsFor(700), columnsFor(1100)]).toEqual([4, 6, 8]);
	});

	it('never lets an item span more columns than it has', () => {
		const spacer: DashboardItem = { id: 'a', kind: 'spacer', size: '4x1' };
		const heading: DashboardItem = { id: 'b', kind: 'heading', size: 'full', text: '' };
		expect(spanOf(spacer, 8)).toBe(4);
		expect(spanOf(spacer, 4)).toBe(4);
		expect(spanOf(heading, 6)).toBe(6);
	});
});

describe('homeItems', () => {
	it('copies Home: Groups first, then each Category under its heading, empty ones left out', () => {
		const items = homeItems(
			[group('group:1')],
			[device('plug:1', 'plug'), device('light:1', 'light'), device('light:2', 'light')]
		);
		const read = items.map((i) => (i.kind === 'heading' ? `# ${i.text}` : i.kind === 'tile' ? i.target : i.kind));
		expect(read).toEqual(['# Groups', 'group:1', '# Lights', 'light:1', 'light:2', '# Plugs', 'plug:1']);
		expect(new Set(items.map((i) => i.id)).size).toBe(items.length);
	});

	it('starts with no Groups heading when there are no Groups', () => {
		expect(homeItems([], [device('light:1', 'light')])[0]).toMatchObject({ kind: 'heading', text: 'Lights' });
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
