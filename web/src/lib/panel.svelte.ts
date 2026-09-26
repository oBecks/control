// What the side panel (desktop) or sheet (phone) shows on Home and on a Dashboard:
// a Device's or Group's controls, the Group editor, or the Hotkey editor.
import { home } from './home.svelte';

export class Panel {
	/** A Device's or a Group's uid. */
	selectedUid = $state<string | null>(null);
	/** The Group editor, open on a Group (uid) or on a new one (null). */
	editor = $state<{ uid: string | null } | null>(null);
	/** The Hotkey editor, open on a Hotkey (uid) or a new one (null) for a Device or Group. */
	hotkeyEditor = $state<{ uid: string | null; target: string } | null>(null);

	selected = $derived(home.controllable.find((d) => d.uid === this.selectedUid));
	selectedGroup = $derived(home.groups.find((g) => g.uid === this.selectedUid));

	/** Something to show. */
	get showing() {
		return !!(this.hotkeyEditor || this.editor || this.selectedGroup || this.selected);
	}

	/** The sheet's name, for screen readers. */
	get label() {
		if (this.hotkeyEditor) return 'Hotkey';
		if (this.editor) return 'Group';
		return `${(this.selectedGroup ?? this.selected)?.name} controls`;
	}

	/** Open a Device's or Group's controls. */
	open(uid: string) {
		this.editor = null;
		this.hotkeyEditor = null;
		this.selectedUid = uid;
	}

	openEditor(uid: string | null) {
		this.hotkeyEditor = null;
		this.editor = { uid };
	}

	close() {
		this.editor = null;
		this.hotkeyEditor = null;
		this.selectedUid = null;
	}

	/** Its Tile is the one whose controls show. */
	highlighted(uid: string) {
		return uid === this.selectedUid && !this.editor && !this.hotkeyEditor;
	}
}
