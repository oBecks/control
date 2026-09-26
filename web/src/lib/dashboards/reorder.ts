// Drag to reorder, with a mouse or a finger: the item follows the pointer's place in the list.
// Items carry data-index; the drag starts on an element with data-handle inside one of them, so
// the rest of the screen still scrolls on a phone.

export interface Reorder {
	/** Show the item at `from` at `to` now (the list re-renders around it). */
	onmove: (from: number, to: number) => void;
	/** The pointer let go: keep the new order. */
	onend: () => void;
}

/** A Svelte attachment for the list's container. */
export function reorder(options: () => Reorder) {
	return (container: HTMLElement) => {
		let dragging: number | null = null;

		function indexAt(x: number, y: number): number | null {
			const el = document.elementFromPoint(x, y)?.closest<HTMLElement>('[data-index]');
			return el && container.contains(el) ? Number(el.dataset.index) : null;
		}

		function down(e: PointerEvent) {
			const handle = (e.target as HTMLElement).closest('[data-handle]');
			const item = handle?.closest<HTMLElement>('[data-index]');
			if (!handle || !item || !container.contains(item) || e.button !== 0) return;
			e.preventDefault();
			dragging = Number(item.dataset.index);
			container.setPointerCapture(e.pointerId);
			container.dataset.dragging = String(dragging);
		}

		function move(e: PointerEvent) {
			if (dragging === null) return;
			const to = indexAt(e.clientX, e.clientY);
			if (to === null || to === dragging) return;
			options().onmove(dragging, to);
			dragging = to;
			container.dataset.dragging = String(to);
		}

		function up() {
			if (dragging === null) return;
			dragging = null;
			delete container.dataset.dragging;
			options().onend();
		}

		container.addEventListener('pointerdown', down);
		container.addEventListener('pointermove', move);
		container.addEventListener('pointerup', up);
		container.addEventListener('pointercancel', up);
		return () => {
			container.removeEventListener('pointerdown', down);
			container.removeEventListener('pointermove', move);
			container.removeEventListener('pointerup', up);
			container.removeEventListener('pointercancel', up);
		};
	};
}
