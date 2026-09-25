// Thin client for the Engine API (src/control/api/app.py). All device logic lives in the Engine.
import type {
	ClimateFeatures,
	ClimateState,
	Control,
	LightFeatures,
	LightState,
	PlugState,
	RemoteFeatures,
	RemoteState,
	StateChange
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
}

export type DeviceState =
	| { control: 'light'; features: LightFeatures; state: LightState }
	| { control: 'plug'; features: Record<string, never>; state: PlugState }
	| { control: 'climate'; features: ClimateFeatures; state: ClimateState; assumed: true }
	| { control: 'remote'; features: RemoteFeatures; state: RemoteState; assumed: true };

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
	setPhoneAccess: (on: boolean) => call<PhoneAccess>('PUT', '/access/phone', { on })
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
