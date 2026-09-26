// Thin client for the Engine API (src/control/api/app.py). All device logic lives in the Engine.
import type {
	ClimateFeatures,
	ClimateState,
	Control,
	GroupControl,
	LightFeatures,
	LightState,
	PlugState,
	RemoteFeatures,
	RemoteState,
	CatalogueApp,
	AppShortcut,
	StreamerFeatures,
	StreamerState,
	StateChange,
	Hotkey,
	HotkeyAction,
	KeysCheck,
	PickableKey
} from './types';

export interface Device {
	uid: string;
	name: string;
	category: string;
	kind: 'network' | 'remote';
	control: Control | null;
	brand: string;
	model: string;
	ip: string | null;
	readiness: string;
	online: boolean;
	is_new: boolean;
	/** Setup hint, e.g. how to unlock a device. */
	note: string;
	source: string | null;
	/** Remote Devices: uid of the Hub that sends their Signals. */
	via: string | null;
	/** Why it can't join a Group (e.g. only a Power Toggle); null if it can. */
	group_problem: string | null;
	/** Streamers: a TV running Android TV itself rather than a box plugged into one. */
	is_tv: boolean | null;
}

/** A named set of Devices controlled as one. */
export interface Group {
	uid: string;
	name: string;
	/** Device uids, in the order the user picked them. */
	members: string[];
	/** light or climate when every member is one; otherwise on/off only. */
	control: GroupControl;
	/** The members' Category when they share one, otherwise "mixed". */
	category: string;
	made_by: 'user' | 'assistant';
}

export type DeviceState =
	| { control: 'light'; features: LightFeatures; state: LightState }
	| { control: 'plug'; features: Record<string, never>; state: PlugState }
	| { control: 'climate'; features: ClimateFeatures; state: ClimateState; assumed: true }
	| { control: 'remote'; features: RemoteFeatures; state: RemoteState; assumed: true }
	| { control: 'streamer'; features: StreamerFeatures; state: StreamerState };

/** A Group's members merged into one reading: only what every member supports, on while any is on. */
export type GroupState = (
	| { control: 'light'; features: LightFeatures; state: LightState; assumed: boolean }
	| { control: 'climate'; features: ClimateFeatures; state: ClimateState; assumed: true }
	| { control: 'power'; features: Record<string, never>; state: PlugState; assumed: boolean }
) & {
	on_count: number;
	total: number;
	/** Each member's own reading, for its Tile. */
	members: Record<string, DeviceState>;
	/** Members that didn't answer, or refused the change. */
	failed: Record<string, { reason: string; unreachable: boolean }>;
};

/** Apps to pick from: those installed (read with adb) or Control's catalogue. */
export interface AppChoices {
	installed: boolean;
	apps: CatalogueApp[];
	/** Why the installed list couldn't be read. */
	problem?: string;
}

export interface ScanResult {
	added: string[];
	moved: Record<string, [string, string]>;
	missing: string[];
	errors: Record<string, string>;
	devices: Device[];
}

export class ApiError extends Error {
	constructor(
		public status: number,
		message: string,
		/** Why access was refused: approval_required, phone_access_off… */
		public code?: string
	) {
		super(message);
	}
	/** 503: the device didn't answer. */
	get unreachable() {
		return this.status === 503;
	}
}

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
	let res: Response;
	try {
		res = await fetch(`/api${path}`, {
			method,
			headers: body ? { 'content-type': 'application/json' } : undefined,
			body: body ? JSON.stringify(body) : undefined
		});
	} catch {
		throw new ApiError(0, "Can't reach the Control Engine");
	}
	if (!res.ok) {
		const { detail, code } = await res.json().then(
			(j) => j,
			() => ({ detail: res.statusText })
		);
		throw new ApiError(res.status, typeof detail === 'string' ? detail : JSON.stringify(detail), code);
	}
	return res.status === 204 ? (undefined as T) : res.json();
}

const enc = encodeURIComponent;

export const api = {
	devices: () => call<Device[]>('GET', '/devices'),
	state: (uid: string) => call<DeviceState>('GET', `/devices/${enc(uid)}/state`),
	setState: (uid: string, change: StateChange) => call<DeviceState>('POST', `/devices/${enc(uid)}/state`, change),
	patch: (uid: string, patch: { name?: string; seen?: boolean }) =>
		call<Device>('PATCH', `/devices/${enc(uid)}`, patch),
	scan: () => call<ScanResult>('POST', '/scan'),
	markAllSeen: () => call<void>('POST', '/devices/seen'),

	// Groups
	groups: () => call<Group[]>('GET', '/groups'),
	addGroup: (name: string, members: string[]) => call<Group>('POST', '/groups', { name, members }),
	patchGroup: (uid: string, patch: { name?: string; members?: string[] }) =>
		call<Group>('PATCH', `/groups/${enc(uid)}`, patch),
	deleteGroup: (uid: string) => call<void>('DELETE', `/groups/${enc(uid)}`),
	groupState: (uid: string) => call<GroupState>('GET', `/groups/${enc(uid)}/state`),
	setGroupState: (uid: string, change: StateChange) => call<GroupState>('POST', `/groups/${enc(uid)}/state`, change),

	// Hotkeys (ADR 0007): set up only on the computer running Control
	hotkeys: () => call<HotkeyList>('GET', '/hotkeys'),
	pickableKeys: () => call<PickableKey[]>('GET', '/hotkeys/keys'),
	checkKeys: (keys: string, uid?: string) => call<KeysCheck>('POST', '/hotkeys/check', { keys, uid }),
	addHotkey: (keys: string, target: string, action: HotkeyAction) =>
		call<Hotkey>('POST', '/hotkeys', { keys, target, action }),
	patchHotkey: (uid: string, patch: { keys?: string; target?: string; action?: HotkeyAction }) =>
		call<Hotkey>('PATCH', `/hotkeys/${enc(uid)}`, patch),
	deleteHotkey: (uid: string) => call<void>('DELETE', `/hotkeys/${enc(uid)}`),
	/** While on, the Desktop App lets go of every Hotkey, so pressing one reaches the Window. */
	recordingKeys: (on: boolean) => call<void>('PUT', '/hotkeys/recording', { on }),

	// Remote Devices & the Code Set Finder
	searchCodeSets: (brand: string, domain: LibraryDomain = 'climate') =>
		call<CodeSet[]>('GET', `/signal-library/${domain}?brand=${enc(brand)}`),
	probe: (codeSets: number[]) =>
		call<{ assignment: Record<string, number>; skipped: number[] }>('POST', '/remote-devices/probe', {
			code_sets: codeSets
		}),
	testCodeSet: (codeSet: number, temp: number) =>
		call<{ sent: boolean }>('POST', '/remote-devices/test', { code_set: codeSet, temp }),
	addRemote: (name: string, codeSet: number, probeTemp?: number) =>
		call<Device>('POST', '/remote-devices', { name, code_set: codeSet, probe_temp: probeTemp }),

	// Button Remote Devices (TV, fan, other) & Learning
	addButtonRemote: (name: string, kind: RemoteKind, codeSet?: number, via?: string) =>
		call<Device>('POST', '/remote-devices/buttons', { name, kind, code_set: codeSet, via }),
	suggestedButtons: (kind: RemoteKind) =>
		call<{ name: string; label: string }[]>('GET', `/remote-devices/suggested-buttons/${kind}`),
	saveButton: (uid: string, button: string, signal: string) =>
		call<Device>('PUT', `/remote-devices/${enc(uid)}/buttons/${enc(button)}`, { signal }),
	learn: (hubUid: string) => call<{ signal: string }>('POST', `/hubs/${enc(hubUid)}/learn`),
	sendSignal: (hubUid: string, signal: string) =>
		call<{ sent: boolean }>('POST', `/hubs/${enc(hubUid)}/send`, { signal }),
	/** Press a harmless test button from a library code set; says which one it pressed. */
	tryLibraryButton: (domain: 'media_player' | 'fan', codeSet: number, via?: string) =>
		call<{ sent: boolean; button: string; label: string }>('POST', '/signal-library/try-button', {
			domain,
			code_set: codeSet,
			via
		}),

	// Tuya Link
	tuyaStart: (userCode: string) =>
		call<{ token: string; qr_content: string }>('POST', '/links/tuya', { user_code: userCode }),
	tuyaPoll: (token: string) =>
		call<{ status: 'pending' } | { status: 'linked'; devices: { uid: string; name: string; category: string }[] }>(
			'GET',
			`/links/tuya/${enc(token)}`
		),

	// Streamers: the Android TV Link (the TV shows a code) and setup
	androidTvLinkStart: (uid: string) => call<void>('POST', `/links/androidtv/${enc(uid)}`),
	androidTvLinkCode: (uid: string, code: string) =>
		call<{ device: Device; is_tv_guess: boolean; apps: CatalogueApp[] }>('POST', `/links/androidtv/${enc(uid)}/code`, {
			code
		}),
	androidTvLinkCancel: (uid: string) => call<void>('DELETE', `/links/androidtv/${enc(uid)}`),
	streamerCatalogue: (uid: string) => call<AppChoices>('GET', `/streamers/${enc(uid)}/catalogue`),
	/** Waits up to a minute for Allow on the TV. */
	streamerAllowAdb: (uid: string) => call<AppChoices>('PUT', `/streamers/${enc(uid)}/adb`),
	setStreamer: (uid: string, setup: { is_tv?: boolean; apps?: AppShortcut[] }) =>
		call<Device>('PUT', `/streamers/${enc(uid)}`, setup),

	// Phone access & Approved Browsers
	access: () => call<{ access: Access; browser_id: string | null }>('GET', '/access/me'),
	askAccess: () => call<{ claim: string; code: string }>('POST', '/access/requests'),
	claimAccess: (claim: string) =>
		call<{ status: 'pending' | 'approved' | 'denied' | 'expired' }>('GET', `/access/claims/${enc(claim)}`),
	accessRequests: () => call<AccessRequest[]>('GET', '/access/requests'),
	decideAccess: (ref: string, approve: boolean) =>
		call<void>('POST', `/access/requests/${enc(ref)}/${approve ? 'approve' : 'deny'}`),
	approvedBrowsers: () => call<ApprovedBrowser[]>('GET', '/access/browsers'),
	revokeBrowser: (id: string) => call<void>('DELETE', `/access/browsers/${enc(id)}`),
	phoneAccess: () => call<PhoneAccess>('GET', '/access/phone'),
	setPhoneAccess: (on: boolean) => call<PhoneAccess>('PUT', '/access/phone', { on }),

	// The Desktop App
	desktop: () => call<DesktopApp>('GET', '/desktop'),
	setStartWithWindows: (on: boolean) => call<DesktopApp>('PUT', '/desktop/start-with-windows', { on }),
	dismissCloseNote: () => call<void>('DELETE', '/desktop/close-note'),

	// The Assistant (ADR 0005)
	assistant: () => call<Assistant>('GET', '/assistant'),
	connectClaude: () => call<Assistant>('PUT', '/assistant/claude'),
	disconnectClaude: () => call<Assistant>('DELETE', '/assistant/claude'),
	dismissRestartNote: () => call<Assistant>('DELETE', '/assistant/restart-note')
};

/** local: the computer running the Engine. approved: an Approved Browser. */
export type Access = 'local' | 'approved' | 'none';

export interface AccessRequest {
	ref: string;
	code: string;
	/** e.g. "iPhone · Safari" */
	name: string;
	created: number;
}

export interface ApprovedBrowser {
	id: string;
	name: string;
	approved_at: number;
	last_seen: number;
	/** The browser asking. */
	current: boolean;
}

export interface PhoneAccess {
	on: boolean;
	/** What phones open, while the Engine listens on the home network. */
	url: string | null;
	error: string | null;
	/** Why phones may still fail to connect, e.g. Windows treats the network as Public. */
	warning: string | null;
	/** Only on the computer running the Engine. */
	can_change: boolean;
	/** What Windows' "Allow access?" prompt calls Control: "Control", or "Python" when run from source. */
	program: string;
}

export interface HotkeyList {
	hotkeys: Hotkey[];
	/** The Desktop App is running, so Hotkeys work. */
	listening: boolean;
	/** Only the computer running Control sets Hotkeys up. */
	can_change: boolean;
	recording: boolean;
}

export interface DesktopApp {
	version: string;
	/** The Engine runs inside the Desktop App (not `control serve`). */
	app: boolean;
	/** null outside the Desktop App. */
	start_with_windows: boolean | null;
	/** A newer release; `url` is its installer. */
	update: { version: string; url: string } | null;
	/** Claude Desktop uses Control (checked only while there's an update): restart it after updating. */
	claude_connected: boolean;
	/** Say once that closing the Window kept Control running (when Windows notifications are off). */
	close_note: boolean;
	/** Only on the computer running the Engine. */
	can_change: boolean;
}

export interface Assistant {
	/** missing: not installed on this PC. outdated: connected to another copy of Control. */
	claude_desktop: 'missing' | 'connected' | 'outdated' | 'off';
	/** Adds Control to Claude Code. */
	claude_code_command: string;
	/** Control was updated to this version and Claude still runs the old tools: restart Claude. */
	restart_claude: string | null;
	/** Only on the computer running the Engine. */
	can_change: boolean;
}

export type RemoteKind = 'tv' | 'fan' | 'other';
export type LibraryDomain = 'climate' | 'media_player' | 'fan';

export interface CodeSet {
	code: number;
	manufacturer: string;
	models: string[];
	controller: string;
}
