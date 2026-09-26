// Drag an item to a cell of a Dashboard's grid, with a mouse or a finger. The item follows the pointer
// cell by cell, keeping the spot it was grabbed by. Items carry data-id, data-x and data-y; the drag
// starts on an element with data-handle inside one, so the rest of the screen still scrolls on a phone.

export interface GridDrag {
	columns: number;
	/** Show the item at this cell now. */
	onmove: (id: string, x: number, y: number) => void;
	/** The pointer let go: keep it there. */
	onend: () => void;
}

/** A Svelte attachment for the grid. */
export function gridDrag(options: () => GridDrag) {
	return (grid: HTMLElement) => {
		let drag: { id: string; dx: number; dy: number; x: number; y: number } | null = null;

		/** The cell under a point, from the grid's own columns, rows and gaps. */
		function cellAt(clientX: number, clientY: number) {
			const { columns } = options();
			const rect = grid.getBoundingClientRect();
			const style = getComputedStyle(grid);
			const colGap = parseFloat(style.columnGap) || 0;
			const rowGap = parseFloat(style.rowGap) || 0;
			const rowH = parseFloat(style.gridAutoRows) || 56;
			const colW = (rect.width - colGap * (columns - 1)) / columns;
			return {
				x: Math.floor((clientX - rect.left + colGap / 2) / (colW + colGap)),
				y: Math.floor((clientY - rect.top + rowGap / 2) / (rowH + rowGap))
			};
		}

		function down(e: PointerEvent) {
			const handle = (e.target as HTMLElement).closest('[data-handle]');
			const item = handle?.closest<HTMLElement>('[data-id]');
			if (!handle || !item || !grid.contains(item) || e.button !== 0) return;
			e.preventDefault();
			const x = Number(item.dataset.x);
			const y = Number(item.dataset.y);
			const at = cellAt(e.clientX, e.clientY);
			drag = { id: item.dataset.id ?? '', dx: at.x - x, dy: at.y - y, x, y };
			grid.setPointerCapture(e.pointerId);
			grid.dataset.dragging = drag.id;
		}

		function move(e: PointerEvent) {
			if (!drag) return;
			const at = cellAt(e.clientX, e.clientY);
			const x = Math.max(0, at.x - drag.dx);
			const y = Math.max(0, at.y - drag.dy);
			if (x === drag.x && y === drag.y) return;
			drag.x = x;
			drag.y = y;
			options().onmove(drag.id, x, y);
		}

		function up() {
			if (!drag) return;
			drag = null;
			delete grid.dataset.dragging;
			options().onend();
		}

		grid.addEventListener('pointerdown', down);
		grid.addEventListener('pointermove', move);
		grid.addEventListener('pointerup', up);
		grid.addEventListener('pointercancel', up);
		return () => {
			grid.removeEventListener('pointerdown', down);
			grid.removeEventListener('pointermove', move);
			grid.removeEventListener('pointerup', up);
			grid.removeEventListener('pointercancel', up);
		};
	};
}
