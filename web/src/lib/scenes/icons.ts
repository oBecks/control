// The icons a Scene can have, by the name the Engine keeps (engine/scenes.py ICONS), in picker order.
import type { Component } from 'svelte';
import Bed from '@lucide/svelte/icons/bed';
import BookOpen from '@lucide/svelte/icons/book-open';
import Briefcase from '@lucide/svelte/icons/briefcase';
import Clapperboard from '@lucide/svelte/icons/clapperboard';
import Coffee from '@lucide/svelte/icons/coffee';
import Leaf from '@lucide/svelte/icons/leaf';
import Moon from '@lucide/svelte/icons/moon';
import PartyPopper from '@lucide/svelte/icons/party-popper';
import Sofa from '@lucide/svelte/icons/sofa';
import Sparkles from '@lucide/svelte/icons/sparkles';
import Sun from '@lucide/svelte/icons/sun';
import Utensils from '@lucide/svelte/icons/utensils';

export const SCENE_ICONS: Record<string, Component> = {
	sparkles: Sparkles,
	clapperboard: Clapperboard,
	sun: Sun,
	moon: Moon,
	sofa: Sofa,
	utensils: Utensils,
	bed: Bed,
	briefcase: Briefcase,
	book: BookOpen,
	coffee: Coffee,
	party: PartyPopper,
	leaf: Leaf
};

export const sceneIcon = (name: string): Component => SCENE_ICONS[name] ?? Sparkles;
