import { describe, expect, it } from 'vitest';
import { dayNames, joinSeconds, splitSeconds, weekOrder, when } from './parts';

describe('days', () => {
	it('starts the week where the language does', () => {
		expect(weekOrder('en-GB')).toEqual([0, 1, 2, 3, 4, 5, 6]);
		expect(weekOrder('he-IL')).toEqual([6, 0, 1, 2, 3, 4, 5]);
		expect(weekOrder('en-US')).toEqual([6, 0, 1, 2, 3, 4, 5]);
	});

	it('names Control’s weekday numbers', () => {
		expect(dayNames('en-GB')[0]).toBe('Mon');
		expect(dayNames('en-GB')[6]).toBe('Sun');
	});
});

describe('waits', () => {
	it('splits and joins seconds', () => {
		expect(splitSeconds(3905)).toEqual({ h: 1, m: 5, s: 5 });
		expect(joinSeconds({ h: 1, m: 5, s: 5 })).toBe(3905);
		expect(joinSeconds({ h: 0, m: NaN, s: 30 })).toBe(30);
	});
});

describe('when', () => {
	const now = new Date(2026, 8, 27, 12, 0);
	const at = (d: number, h: number) => new Date(2026, 8, d, h, 0).getTime() / 1000;

	it('says today, yesterday, a weekday or a date', () => {
		expect(when(at(27, 7), now, 'en-GB')).toBe('Today 07:00');
		expect(when(at(26, 22), now, 'en-GB')).toBe('Yesterday 22:00');
		expect(when(at(28, 7), now, 'en-GB')).toBe('Tomorrow 07:00');
		expect(when(at(23, 7), now, 'en-GB')).toBe('Wed 07:00');
		expect(when(at(10, 7), now, 'en-GB')).toBe('10 Sept 07:00');
	});

	it('writes 24-hour times like the Engine’s sentences, in any language', () => {
		expect(when(at(27, 18), now, 'en-US')).toBe('Today 18:00');
	});
});
