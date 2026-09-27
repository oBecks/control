// The icon a remote button shows on its own (a Single Button); buttons without one show their label.
// Per-icon imports: the barrel pulls in every icon, which makes unit tests very slow to start.
import ChevronDown from '@lucide/svelte/icons/chevron-down';
import ChevronLeft from '@lucide/svelte/icons/chevron-left';
import ChevronRight from '@lucide/svelte/icons/chevron-right';
import ChevronUp from '@lucide/svelte/icons/chevron-up';
import House from '@lucide/svelte/icons/house';
import Minus from '@lucide/svelte/icons/minus';
import Play from '@lucide/svelte/icons/play';
import Plus from '@lucide/svelte/icons/plus';
import Power from '@lucide/svelte/icons/power';
import Undo2 from '@lucide/svelte/icons/undo-2';
import Volume1 from '@lucide/svelte/icons/volume-1';
import Volume2 from '@lucide/svelte/icons/volume-2';
import VolumeX from '@lucide/svelte/icons/volume-x';
import type { Component } from 'svelte';

const ICONS: Record<string, Component> = {
	power: Power,
	power_on: Power,
	power_off: Power,
	volume_up: Volume2,
	volume_down: Volume1,
	mute: VolumeX,
	channel_up: Plus,
	channel_down: Minus,
	speed_up: Plus,
	speed_down: Minus,
	up: ChevronUp,
	down: ChevronDown,
	left: ChevronLeft,
	right: ChevronRight,
	home: House,
	back: Undo2,
	play_pause: Play
};

export function buttonIcon(name: string): Component | undefined {
	return ICONS[name];
}
