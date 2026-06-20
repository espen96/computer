<script lang="ts">
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import {
		currentWorkspace,
		workspaceList,
		addWorkspace,
		loadWorkspace,
		gitReviewOpen,
		setActiveGroup,
		setSplitRatio,
		openTabInSplit,
		setSplitDirection,
		openChatTab,
		openChatModeTab,
		openFileTab,
		openTerminalTab,
		setFileBrowserCwd,
		createChatModeWorkspace,
		appVersion,
		showChangelog,
		chatModeTabs,
		showSearch,
		pwaPreferences,
		mainProjectDirectory,
		workspaceMode,
		chatList,
		selectedModelId
	} from '$lib/stores';
	import type { Tab, EditorGroup } from '$lib/stores';
	import { t } from '$lib/i18n';
	import { get } from 'svelte/store';
	import { getWelcome } from '$lib/apis/state';
	import { createSession } from '$lib/apis/terminal';
	import { createEntry, writeFile, uploadFiles as uploadFilesApi } from '$lib/apis/files';
	import { deleteSharePayload, getSharePayload } from '$lib/intents/payloadStore';
	import type { LaunchIntent, ShareBehavior, SharePayload } from '$lib/intents/types';
	import FileBrowser from '$lib/components/FileBrowser.svelte';
	import FileEditor from '$lib/components/FileEditor.svelte';
	import GitView from '$lib/components/GitView.svelte';
	import Terminal from '$lib/components/Terminal.svelte';
	import PortPreview from '$lib/components/PortPreview.svelte';
	import ChatPanel from '$lib/components/chat/ChatPanel.svelte';
	import ChatInput from '$lib/components/chat/ChatInput.svelte';
	import DirectoryPicker from '$lib/components/DirectoryPicker.svelte';
	import GroupTabBar from '$lib/components/GroupTabBar.svelte';
	import Icon from '$lib/components/Icon.svelte';
	import WorkspacePicker from '$lib/components/WorkspacePicker.svelte';
	import Modal from '$lib/components/Modal.svelte';
	import SystemInfo from '$lib/components/SystemInfo.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';

	let showPicker = $state(false);
	let pendingIntent = $state<LaunchIntent | null>(null);
	let folderPickerIntent = $state<LaunchIntent | null>(null);
	let folderPickerWorkspace = $state<string | null>(null);
	const INTENT_URL_KEYS = [
		'intent',
		'chatId',
		'file',
		'dir',
		'targetDir',
		'payload',
		'shareBehavior',
		'title',
		'text',
		'url'
	];

	// ── URL-driven workspace loading ───────────────────────────────
	// The workspace path comes from the URL query param: ?workspace=/path/to/dir
	// Each browser tab has its own URL → its own workspace.
	// Intent params (chatId, file, dir) are processed AFTER loading.

	let lastLoadedPath = $state<string | null>(null);
	type LaunchQueueWindow = Window & {
		__cptrLaunchQueueBound?: boolean;
		launchQueue?: {
			setConsumer: (
				consumer: (params: { files?: { getFile: () => Promise<File> }[] }) => void
			) => void;
		};
	};

	function urlIntent(url: URL): LaunchIntent | null {
		const protocol = webCptrIntent(url.searchParams.get('intent'));
		const params = protocol?.params ?? url.searchParams;
		const intent = protocol?.intent ?? url.searchParams.get('intent');
		const workspace = params.get('workspace') || undefined;
		const chatId = params.get('chatId');
		const filePath = params.get('file');
		const dirPath = params.get('dir');

		if (intent === 'newNote') return { kind: 'newNote', workspace };
		if (intent === 'newChat') return { kind: 'newChat', workspace };
		if (intent === 'newTerminal') return { kind: 'newTerminal', workspace };
		if (intent === 'openWorkspace') return { kind: 'openWorkspace' };
		if (intent === 'search') return { kind: 'search', workspace };
		if (intent === 'importFiles') {
			return { kind: 'importFiles', workspace, targetDir: params.get('targetDir') || undefined };
		}
		if (intent === 'share') {
			return {
				kind: 'share',
				workspace,
				payloadId: params.get('payload') || undefined,
				targetDir: params.get('targetDir') || undefined,
				shareBehavior: (params.get('shareBehavior') || undefined) as ShareBehavior | undefined,
				share: {
					title: params.get('title') || undefined,
					text: params.get('text') || undefined,
					url: params.get('url') || undefined
				}
			};
		}
		if (chatId !== null) return { kind: 'openChat', workspace, chatId: chatId || null };
		if (filePath) return { kind: 'openFile', workspace, filePath };
		if (dirPath) return { kind: 'openDir', workspace, dirPath };
		return null;
	}

	function webCptrIntent(
		raw: string | null
	): { intent: string | null; params: URLSearchParams } | null {
		if (!raw) return null;
		let decoded = raw;
		try {
			decoded = decodeURIComponent(raw);
		} catch {}
		if (!decoded.startsWith('web+cptr:')) return null;
		try {
			const parsed = new URL(decoded);
			return {
				intent:
					parsed.searchParams.get('intent') ||
					parsed.hostname ||
					parsed.pathname.replace(/^\/+/, '') ||
					null,
				params: parsed.searchParams
			};
		} catch {
			const rest = decoded.replace(/^web\+cptr:(\/\/)?/, '');
			const [intentPart, query = ''] = rest.split('?');
			return { intent: intentPart.replace(/^\/+/, '') || null, params: new URLSearchParams(query) };
		}
	}

	function clearIntentUrl(url: URL): string {
		const next = new URL(url);
		for (const key of INTENT_URL_KEYS) next.searchParams.delete(key);
		return next.pathname + next.search;
	}

	function noteBaseName(now = new Date()): string {
		const pad = (n: number) => String(n).padStart(2, '0');
		return `note-${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}-${pad(
			now.getHours()
		)}${pad(now.getMinutes())}`;
	}

	function shareMarkdown(payload: SharePayload): string {
		const lines: string[] = [];
		if (payload.title) lines.push(`# ${payload.title.trim()}`, '');
		if (payload.text) lines.push(payload.text.trim(), '');
		if (payload.url) lines.push(payload.url.trim(), '');
		if (payload.files?.length) {
			lines.push('Files:', ...payload.files.map((file) => `- ${file.name}`), '');
		}
		return lines.join('\n').trimEnd() + '\n';
	}

	async function processIntentParams() {
		const url = new URL($page.url);
		const parsed = urlIntent(url);
		if (parsed) history.replaceState(history.state, '', clearIntentUrl(url));
		if (!parsed) return;
		await handleIntent(parsed);
	}

	async function handleIntent(intent: LaunchIntent) {
		if (intent.kind === 'openWorkspace') {
			showPicker = true;
			return;
		}

		const targetWorkspace = intent.workspace;
		const needsWorkspace = intentNeedsExplicitWorkspace(intent.kind);
		if (needsWorkspace && !targetWorkspace) {
			pendingIntent = intent;
			return;
		}

		switch (intent.kind) {
			case 'newNote':
				await createNote(targetWorkspace!);
				break;
			case 'newChat':
				openChatTab();
				break;
			case 'newTerminal':
				await openTerminalTab();
				break;
			case 'search':
				showSearch.set(true);
				break;
			case 'openChat':
				openChatTab(intent.chatId ?? undefined);
				break;
			case 'openFile':
				if (intent.filePath) openFileTab(intent.filePath);
				break;
			case 'openDir':
				if (intent.dirPath) setFileBrowserCwd(intent.dirPath);
				break;
			case 'share':
				await handleShareIntent(intent, targetWorkspace!);
				break;
			case 'importFiles':
				await importIntentFiles(intent, targetWorkspace!);
				break;
		}
	}

	function intentNeedsExplicitWorkspace(kind: LaunchIntent['kind']): boolean {
		return !['openWorkspace', 'search'].includes(kind);
	}

	async function createNote(workspacePath: string, content = '') {
		if (get(currentWorkspace)?.path !== workspacePath) {
			await loadWorkspace(workspacePath);
		}

		const base = noteBaseName();
		for (let i = 1; i < 100; i += 1) {
			const suffix = i === 1 ? '' : `-${i}`;
			const path = `${workspacePath}/${base}${suffix}.md`;
			try {
				await createEntry(path, 'file');
				if (content) await writeFile(path, content);
				openFileTab(path, undefined, { edit: true });
				return path;
			} catch (e: any) {
				if (e?.status !== 409) throw e;
			}
		}
		throw new Error('Could not create note');
	}

	async function handleShareIntent(intent: LaunchIntent, workspacePath: string) {
		const behavior = intent.shareBehavior ?? get(pwaPreferences).shareBehavior;
		if (behavior === 'ask') {
			pendingIntent = intent;
			return;
		}

		let share = intent.share;
		if (intent.payloadId) {
			share = (await getSharePayload(intent.payloadId)) ?? share;
			await deleteSharePayload(intent.payloadId).catch(() => {});
		}
		if (!share) return;

		if (behavior === 'chatDraft') {
			sessionStorage.setItem(`cptr:intent:chatDraft:${workspacePath}`, shareMarkdown(share));
			openChatTab();
			return;
		}
		await createNote(workspacePath, shareMarkdown(share));
	}

	async function importIntentFiles(intent: LaunchIntent, workspacePath: string) {
		const files = intent.importFiles?.files;
		if (!files?.length) return;
		const prefs = get(pwaPreferences);
		if (prefs.importDestination === 'askFolder' && !intent.targetDir) {
			folderPickerIntent = intent;
			folderPickerWorkspace = workspacePath;
			showPicker = true;
			return;
		}
		const directory = resolveImportDirectory(workspacePath, intent.targetDir);
		for (const file of files) {
			const form = new FormData();
			form.append('file', file, file.name);
			form.append('directory', directory);
			await uploadFilesApi(directory, form);
		}
	}

	function resolveImportDirectory(workspacePath: string, targetDir?: string): string {
		if (targetDir) return targetDir;
		const prefs = get(pwaPreferences);
		if (prefs.importDestination !== 'configuredFolder' || !prefs.importFolder?.trim()) {
			return workspacePath;
		}
		const folder = prefs.importFolder.trim();
		if (folder.startsWith('/')) return folder;
		return `${workspacePath}/${folder.replace(/^\/+/, '')}`;
	}

	async function chooseIntentWorkspace(path: string, behavior?: ShareBehavior) {
		if (!pendingIntent) return;
		addWorkspace(path);
		const intent: LaunchIntent = {
			...pendingIntent,
			workspace: path,
			shareBehavior: behavior ?? pendingIntent.shareBehavior
		};
		pendingIntent = null;
		const params = new URLSearchParams({ workspace: path });
		await goto(`/?${params.toString()}`, { replaceState: true });
		if (get(currentWorkspace)?.path !== path) await loadWorkspace(path);
		await handleIntent(intent);
	}

	function handlePickedImportFolder(path: string) {
		if (!folderPickerIntent || !folderPickerWorkspace) return;
		const intent: LaunchIntent = {
			...folderPickerIntent,
			workspace: folderPickerWorkspace,
			targetDir: path
		};
		folderPickerIntent = null;
		folderPickerWorkspace = null;
		showPicker = false;
		void handleIntent(intent);
	}

	$effect(() => {
		const url = $page.url;
		const wsPath = url.searchParams.get('workspace');
		const newChat = url.searchParams.get('newChat');

		if (wsPath && wsPath !== lastLoadedPath) {
			// New workspace — load then process intents
			lastLoadedPath = wsPath;
			loadWorkspace(wsPath).then(() => {
				processIntentParams();
				// Handle ?newChat=1 after workspace is loaded
				if (newChat) {
					openChatModeTab();
					// Clean up ?newChat from URL
					const u = new URL(window.location.href);
					u.searchParams.delete('newChat');
					history.replaceState(history.state, '', u.pathname + u.search);
				}
			});
		} else if (wsPath && wsPath === lastLoadedPath) {
			// Same workspace — process intents immediately
			processIntentParams();
		} else if (!wsPath && newChat) {
			// New chat from welcome page — create workspace in-memory, no server hit
			const tempPath = `~/.cptr/chat-workspaces/temp-${Date.now()}`;
			lastLoadedPath = tempPath;
			currentWorkspace.set(createChatModeWorkspace(tempPath));
			openChatModeTab();
			// Clean up URL
			const u = new URL(window.location.href);
			u.searchParams.delete('newChat');
			history.replaceState(history.state, '', u.pathname + u.search);
		} else if (!wsPath) {
			lastLoadedPath = null;
			currentWorkspace.set(null);
			processIntentParams();
		}
	});

	$effect(() => {
		if (typeof window === 'undefined') return;
		const w = window as LaunchQueueWindow;
		if (!w.launchQueue || w.__cptrLaunchQueueBound) return;
		w.__cptrLaunchQueueBound = true;
		w.launchQueue.setConsumer(async (launchParams) => {
			const handles = launchParams.files ?? [];
			if (!handles.length) return;
			const files: File[] = [];
			for (const handle of handles) {
				try {
					files.push(await handle.getFile());
				} catch {}
			}
			if (files.length) await handleIntent({ kind: 'importFiles', importFiles: { files } });
		});
	});

	// Welcome page data
	let welcomeData = $state<{
		hostname: string;
		platform: string;
		version: string;
		system: {
			os: string;
			arch: string;
			python: string;
			cpu_count: number;
			memory_total?: number;
			memory_available?: number;
			disk_total?: number;
			disk_used?: number;
			disk_free?: number;
			uptime_seconds?: number;
			load_avg?: number[];
			cpu_usage?: number;
			network?: { name: string; ip: string }[];
		};
		processes: { pid: number; cpu: number; mem: number; name: string }[];
		suggestions: { name: string; path: string }[];
		recent: { name: string; path: string }[];
	} | null>(null);

	import { chatModels, defaultModel } from '$lib/stores/chat';
	import { toast } from 'svelte-sonner';

	let welcomeInputText = $state('');
	let welcomeSelectedModel = $state('');
	let welcomeSending = $state(false);

	$effect(() => {
		const models = get(chatModels);
		const saved = get(selectedModelId);
		const dm = get(defaultModel);
		if (saved && models.some((m) => m.id === saved)) welcomeSelectedModel = saved;
		else if (dm) welcomeSelectedModel = dm;
		else if (models.length) welcomeSelectedModel = models[0].id;
	});

	$effect(() => {
		if (welcomeSelectedModel) selectedModelId.set(welcomeSelectedModel);
	});

	async function handleWelcomeSend() {
		const text = welcomeInputText.trim();
		if (!text || !welcomeSelectedModel) return;
		welcomeSending = true;

		// Resolve workspace path
		let tempPath = '';
		if (get(workspaceMode) === 'project') {
			const root = get(mainProjectDirectory);
			if (!root) {
				toast.error('Please configure your Main Project Directory in Settings first.');
				welcomeSending = false;
				return;
			}
			tempPath = `${root}/chats/temp-${Date.now()}`;
		} else {
			tempPath = `~/.cptr/chat-workspaces/temp-${Date.now()}`;
		}

		try {
			// Save draft and auto-send key in sessionStorage
			sessionStorage.setItem(`cptr:intent:chatDraft:${tempPath}`, text);
			sessionStorage.setItem(`cptr:intent:chatAutoSend:${tempPath}`, 'true');

			// Create in-memory workspace
			lastLoadedPath = tempPath;
			currentWorkspace.set(createChatModeWorkspace(tempPath));
			openChatModeTab();

			welcomeInputText = '';
		} catch (e) {
			console.error(e);
			toast.error('Failed to start chat');
		} finally {
			welcomeSending = false;
		}
	}

	let showNewProjectModal = $state(false);
	let newProjectName = $state('');
	let creatingProject = $state(false);

	async function handleCreateProject() {
		const name = newProjectName.trim();
		if (!name) return;

		const root = get(mainProjectDirectory);
		if (!root) {
			toast.error('Please configure your Main Project Directory in Settings first.');
			return;
		}

		creatingProject = true;
		// Create project folder path
		const projectPath = `${root}/${name}`;
		try {
			// Create directory on disk
			await createEntry(projectPath, 'directory');

			// Add workspace and redirect
			addWorkspace(projectPath, name);
			goto(`/?workspace=${encodeURIComponent(projectPath)}`);
			showNewProjectModal = false;
			newProjectName = '';
		} catch (e: any) {
			console.error(e);
			if (e?.status === 409) {
				toast.error('A project with that name already exists.');
			} else {
				toast.error('Failed to create project folder.');
			}
		} finally {
			creatingProject = false;
		}
	}

	// Fetch welcome data whenever no workspace is active
	$effect(() => {
		if (!$currentWorkspace) {
			getWelcome()
				.then((data) => {
					welcomeData = data as typeof welcomeData;
				})
				.catch(() => {});
		}
	});

	// Lazy-init terminal sessions for any group's active tab
	let initingTerminal = $state(false);
	$effect(() => {
		const ws = $currentWorkspace;
		if (!ws || initingTerminal) return;

		// Find any terminal tab across all groups that needs a session
		for (const group of ws.groups) {
			const tab = group.tabs.find((t) => t.id === group.activeTabId);
			if (tab && tab.type === 'terminal' && !tab.sessionId) {
				initingTerminal = true;
				createSession(ws.path)
					.then((data) => {
						currentWorkspace.update((w) => {
							if (!w) return w;
							return {
								...w,
								groups: w.groups.map((g) => ({
									...g,
									tabs: g.tabs.map((t) =>
										t.id === tab.id ? { ...t, sessionId: data.session_id } : t
									)
								}))
							};
						});
					})
					.catch((e) => console.error('Failed to init terminal:', e))
					.finally(() => {
						initingTerminal = false;
					});
				return; // Only init one at a time
			}
		}
	});

	function quickOpen(path: string) {
		addWorkspace(path);
		// Carry forward any pending intent params through workspace selection
		const params = new URLSearchParams($page.url.searchParams);
		params.set('workspace', path);
		goto(`/?${params.toString()}`);
	}

	function shortenPath(path: string): string {
		const home = welcomeData?.suggestions?.[0]?.path;
		if (home && path.startsWith(home)) {
			return '~' + path.slice(home.length);
		}
		return path;
	}

	// ── Draggable divider ──────────────────────────────────────────

	let isDragging = $state(false);
	let containerEl: HTMLDivElement | undefined = $state();

	function handleDividerPointerDown(e: PointerEvent) {
		e.preventDefault();
		isDragging = true;
		(e.target as HTMLElement).setPointerCapture(e.pointerId);
	}

	function handleDividerPointerMove(e: PointerEvent) {
		if (!isDragging || !containerEl) return;
		const rect = containerEl.getBoundingClientRect();
		const direction = $currentWorkspace?.splitDirection ?? 'horizontal';

		let ratio: number;
		if (direction === 'horizontal') {
			ratio = (e.clientX - rect.left) / rect.width;
		} else {
			ratio = (e.clientY - rect.top) / rect.height;
		}
		setSplitRatio(ratio);
	}

	function handleDividerPointerUp() {
		isDragging = false;
	}

	// Computed
	let isWideScreen = $state(typeof window !== 'undefined' ? window.innerWidth >= 1024 : false);

	$effect(() => {
		if (typeof window === 'undefined') return;
		function onResize() {
			isWideScreen = window.innerWidth >= 1024;
		}
		window.addEventListener('resize', onResize);
		return () => window.removeEventListener('resize', onResize);
	});

	const allGroups = $derived($currentWorkspace?.groups ?? []);
	const splitDirection = $derived($currentWorkspace?.splitDirection ?? 'horizontal');
	const splitRatio = $derived($currentWorkspace?.splitRatio ?? 0.5);

	// On mobile, collapse to just the active group
	const displayGroups = $derived(
		isWideScreen
			? allGroups
			: allGroups.filter((g) => g.id === $currentWorkspace?.activeGroupId).slice(0, 1)
	);
	const hasSplit = $derived(displayGroups.length > 1);

	function getGroupActiveTab(group: EditorGroup): Tab | null {
		return group.tabs.find((t) => t.id === group.activeTabId) ?? null;
	}

	// ── Drag-to-split ─────────────────────────────────────────────

	let dragOverZone = $state<'right' | 'bottom' | null>(null);

	function handleContainerDragOver(e: DragEvent) {
		if (!containerEl || !isWideScreen) return;
		// Only respond to tab drags, not file uploads
		if (!e.dataTransfer?.types.includes('text/tab-id')) return;
		// Only show drop zones when not already split
		if (hasSplit) return;

		e.preventDefault();
		const rect = containerEl.getBoundingClientRect();
		const xRatio = (e.clientX - rect.left) / rect.width;
		const yRatio = (e.clientY - rect.top) / rect.height;

		if (xRatio > 0.75) {
			dragOverZone = 'right';
		} else if (yRatio > 0.75) {
			dragOverZone = 'bottom';
		} else {
			dragOverZone = null;
		}
	}

	function handleContainerDragLeave(e: DragEvent) {
		// Only reset if leaving the container entirely
		if (containerEl && !containerEl.contains(e.relatedTarget as Node)) {
			dragOverZone = null;
		}
	}

	function handleContainerDrop(e: DragEvent) {
		if (!dragOverZone || !e.dataTransfer) {
			dragOverZone = null;
			return;
		}
		// Don't intercept file uploads
		if (e.dataTransfer.types.includes('Files')) {
			dragOverZone = null;
			return;
		}

		const tabId = e.dataTransfer.getData('text/tab-id');
		const fromGroupId = e.dataTransfer.getData('text/group-id');
		if (!tabId || !fromGroupId) {
			dragOverZone = null;
			return;
		}

		e.preventDefault();
		const direction = dragOverZone === 'right' ? 'horizontal' : 'vertical';
		setSplitDirection(direction as any);

		// Move the dragged tab into a new split pane
		const ws = $currentWorkspace;
		if (ws) {
			const sourceGroup = ws.groups.find((g) => g.id === fromGroupId);
			const tab = sourceGroup?.tabs.find((t) => t.id === tabId);
			if (tab) {
				openTabInSplit(tabId, direction as any);
			}
		}
		dragOverZone = null;
	}
</script>

{#if !$currentWorkspace}
	<div
		class="flex flex-col items-center justify-start h-full p-6 overflow-y-auto bg-gray-50 dark:bg-gray-950/40"
	>
		<div class="w-full max-w-3xl flex flex-col items-center pt-[10dvh]">
			<!-- Header -->
			<div class="mb-6 text-center">
				<h1 class="text-3xl font-light tracking-tight text-gray-950 dark:text-white mb-2">
					Ready when you are.
				</h1>
				<p class="text-xs text-gray-400 dark:text-gray-500 font-normal">
					Start a quick chat below or open a project to begin
				</p>
			</div>

			<!-- Chat Input Area -->
			<div class="w-full max-w-2xl bg-transparent dark:bg-transparent p-1 mb-8">
				<ChatInput
					bind:inputText={welcomeInputText}
					bind:selectedModel={welcomeSelectedModel}
					sending={welcomeSending}
					onsend={handleWelcomeSend}
					placeholder="How can I help you today?"
				/>
			</div>

			<!-- Content Grid -->
			<div class="w-full grid grid-cols-1 md:grid-cols-2 gap-8 mt-4">
				<!-- Recent Chats Column -->
				<div class="flex flex-col">
					<h3
						class="text-xs font-semibold text-gray-400 dark:text-gray-600 uppercase tracking-wider mb-3"
					>
						Recent Chats
					</h3>
					{#if $chatList && $chatList.length > 0}
						<div class="flex flex-col gap-1.5">
							{#each $chatList.slice(0, 5) as chat}
								<button
									class="flex items-center gap-3 p-3 rounded-xl hover:bg-gray-100 dark:hover:bg-white/4 text-left transition-all duration-150 border border-transparent hover:border-gray-200 dark:hover:border-white/8 group cursor-pointer"
									onclick={() => quickOpen(chat.path)}
								>
									<div
										class="flex items-center justify-center w-8 h-8 rounded-lg bg-gray-100 dark:bg-white/6 text-gray-500 dark:text-gray-400 group-hover:bg-gray-200 dark:group-hover:bg-white/10 group-hover:text-gray-700 dark:group-hover:text-gray-200 transition-colors"
									>
										<Icon name="chat-bubble" size={15} />
									</div>
									<div class="flex-1 min-w-0">
										<div
											class="text-[13px] font-medium text-gray-700 dark:text-gray-300 truncate group-hover:text-gray-900 dark:group-hover:text-white"
										>
											{chat.name || 'Untitled Chat'}
										</div>
										<div
											class="text-[10px] text-gray-400 dark:text-gray-500 mt-0.5 truncate font-mono"
										>
											{shortenPath(chat.path)}
										</div>
									</div>
								</button>
							{/each}
						</div>
					{:else}
						<div
							class="p-6 rounded-xl border border-dashed border-gray-200 dark:border-white/6 text-center text-xs text-gray-400 dark:text-gray-600"
						>
							No recent chats yet.
						</div>
					{/if}
				</div>

				<!-- Projects Column -->
				<div class="flex flex-col">
					<div
						class="flex items-center justify-between mb-3 border-b border-gray-100 dark:border-white/6 pb-1.5"
					>
						<h3
							class="text-xs font-semibold text-gray-400 dark:text-gray-600 uppercase tracking-wider"
						>
							Projects
						</h3>
						{#if $workspaceMode === 'project'}
							<button
								class="flex items-center gap-1 text-[11px] font-medium text-blue-500 hover:text-blue-600 dark:text-blue-400 dark:hover:text-blue-300 transition-colors cursor-pointer"
								onclick={() => (showNewProjectModal = true)}
							>
								<Icon name="plus" size={12} />
								Start a new project
							</button>
						{:else}
							<button
								class="flex items-center gap-1 text-[11px] font-medium text-blue-500 hover:text-blue-600 dark:text-blue-400 dark:hover:text-blue-300 transition-colors cursor-pointer"
								onclick={() => (showPicker = true)}
							>
								<Icon name="folder" size={12} />
								Open folder
							</button>
						{/if}
					</div>

					<!-- Recent Projects List -->
					{#if welcomeData?.recent?.length}
						<div class="flex flex-col gap-1.5">
							{#each welcomeData.recent.slice(0, 5) as item}
								<button
									class="flex items-center gap-3 p-3 rounded-xl hover:bg-gray-100 dark:hover:bg-white/4 text-left transition-all duration-150 border border-transparent hover:border-gray-200 dark:hover:border-white/8 group cursor-pointer"
									onclick={() => quickOpen(item.path)}
								>
									<div
										class="flex items-center justify-center w-8 h-8 rounded-lg bg-gray-100 dark:bg-white/6 text-gray-500 dark:text-gray-400 group-hover:bg-gray-200 dark:group-hover:bg-white/10 group-hover:text-gray-700 dark:group-hover:text-gray-200 transition-colors"
									>
										<Icon name="folder" size={14} />
									</div>
									<div class="flex-1 min-w-0">
										<div
											class="text-[13px] font-medium text-gray-700 dark:text-gray-300 truncate group-hover:text-gray-900 dark:group-hover:text-white"
										>
											{item.name}
										</div>
										<div
											class="text-[10px] text-gray-400 dark:text-gray-500 mt-0.5 truncate font-mono"
										>
											{shortenPath(item.path)}
										</div>
									</div>
								</button>
							{/each}
						</div>
					{:else}
						<div
							class="p-6 rounded-xl border border-dashed border-gray-200 dark:border-white/6 text-center text-xs text-gray-400 dark:text-gray-600"
						>
							No recent projects yet.
						</div>
					{/if}

					<!-- Suggestions / Folders in computer mode -->
					{#if $workspaceMode === 'computer' && welcomeData?.suggestions?.length}
						<h3
							class="text-xs font-semibold text-gray-400 dark:text-gray-600 uppercase tracking-wider mt-6 mb-3"
						>
							Suggested Folders
						</h3>
						<div class="flex flex-col gap-1.5">
							{#each welcomeData.suggestions.slice(0, 3) as item}
								<button
									class="flex items-center gap-3 p-2.5 rounded-xl hover:bg-gray-100 dark:hover:bg-white/4 text-left transition-all duration-150 border border-transparent hover:border-gray-200 dark:hover:border-white/8 group cursor-pointer"
									onclick={() => quickOpen(item.path)}
								>
									<Icon
										name="folder"
										size={13}
										class="text-gray-400 dark:text-gray-500 group-hover:text-gray-600 dark:group-hover:text-gray-300"
									/>
									<div class="flex-1 min-w-0 flex items-baseline gap-2">
										<span
											class="text-xs font-medium text-gray-600 dark:text-gray-400 group-hover:text-gray-800 dark:group-hover:text-gray-200 truncate"
										>
											{item.name}
										</span>
										<span class="text-[10px] text-gray-400 dark:text-gray-500 font-mono truncate">
											{shortenPath(item.path)}
										</span>
									</div>
								</button>
							{/each}
						</div>
					{/if}
				</div>
			</div>
		</div>
	</div>
{:else}
	<!-- Editor groups layout -->
	<div
		bind:this={containerEl}
		class="split-container"
		class:split-horizontal={splitDirection === 'horizontal'}
		class:split-vertical={splitDirection === 'vertical'}
		class:is-dragging={isDragging}
		role="presentation"
		ondragover={handleContainerDragOver}
		ondragleave={handleContainerDragLeave}
		ondrop={handleContainerDrop}
	>
		{#each displayGroups as group, i (group.id)}
			{@const groupTab = getGroupActiveTab(group)}

			{#if i > 0}
				<!-- Divider between groups -->
				<!-- svelte-ignore a11y_no_static_element_interactions -->
				<div
					class="split-divider"
					class:split-divider-h={splitDirection === 'horizontal'}
					class:split-divider-v={splitDirection === 'vertical'}
					onpointerdown={handleDividerPointerDown}
					onpointermove={handleDividerPointerMove}
					onpointerup={handleDividerPointerUp}
					onpointercancel={handleDividerPointerUp}
				>
					<div class="split-divider-handle"></div>
				</div>
			{/if}

			<!-- svelte-ignore a11y_no_static_element_interactions -->
			<div
				class="split-pane"
				style={hasSplit
					? splitDirection === 'horizontal'
						? `width: ${i === 0 ? splitRatio * 100 : (1 - splitRatio) * 100}%;`
						: `height: ${i === 0 ? splitRatio * 100 : (1 - splitRatio) * 100}%;`
					: ''}
				onclick={() => setActiveGroup(group.id)}
			>
				<!-- Per-group tab bar -->
				<GroupTabBar {group} canClose={hasSplit} isPrimary={i === 0} />

				<!-- Tab content -->
				<div class="pane-content">
					{#if $gitReviewOpen && i === 0}
						<GitView />
					{:else}
						<!-- Persist all tab instances so state survives tab switches (like VS Code) -->
						{#each group.tabs.filter((t) => t.type === 'file' && t.filePath) as tab (tab.id)}
							<div class="persisted-tab" class:persisted-tab-hidden={tab.id !== group.activeTabId}>
								<FileEditor filePath={tab.filePath!} tabId={tab.id} edit={tab.edit === true} />
							</div>
						{/each}

						{#each group.tabs.filter((t) => t.type === 'chat') as tab (tab.id)}
							<div class="persisted-tab" class:persisted-tab-hidden={tab.id !== group.activeTabId}>
								<ChatPanel
									workspace={$currentWorkspace.path}
									chatId={tab.path?.startsWith('new-') || tab.path?.startsWith('pending-')
										? undefined
										: tab.path}
									tabId={tab.id}
									chatMode={$chatModeTabs.has(tab.id)}
								/>
							</div>
						{/each}

						{#each group.tabs.filter((t) => t.type === 'terminal' && t.sessionId) as tab (tab.id)}
							<div class="persisted-tab" class:persisted-tab-hidden={tab.id !== group.activeTabId}>
								<Terminal sessionId={tab.sessionId!} />
							</div>
						{/each}

						{#each group.tabs.filter((t) => t.type === 'preview' && t.port) as tab (tab.id)}
							<div class="persisted-tab" class:persisted-tab-hidden={tab.id !== group.activeTabId}>
								<PortPreview port={tab.port!} />
							</div>
						{/each}

						<!-- Fallback content for non-persisted states -->
						{#if !groupTab || groupTab.type === 'files'}
							<FileBrowser />
						{:else if groupTab.type === 'terminal' && !groupTab.sessionId}
							<div class="flex items-center justify-center h-full">
								<Spinner size={20} />
							</div>
						{/if}
					{/if}
				</div>
			</div>
		{/each}

		<!-- Drop zone indicators for drag-to-split -->
		{#if dragOverZone === 'right'}
			<div class="split-drop-zone split-drop-right"></div>
		{/if}
		{#if dragOverZone === 'bottom'}
			<div class="split-drop-zone split-drop-bottom"></div>
		{/if}
	</div>
{/if}

{#if pendingIntent}
	<WorkspacePicker
		intent={pendingIntent}
		workspaces={$workspaceList}
		onchoose={chooseIntentWorkspace}
		oncancel={() => (pendingIntent = null)}
	/>
{/if}

{#if showPicker}
	<DirectoryPicker
		onclose={() => {
			showPicker = false;
			folderPickerIntent = null;
			folderPickerWorkspace = null;
		}}
		onselect={folderPickerIntent ? handlePickedImportFolder : undefined}
	/>
{/if}

{#if showNewProjectModal}
	<Modal
		onclose={() => {
			showNewProjectModal = false;
			newProjectName = '';
		}}
		class="w-full max-w-sm p-5 flex flex-col gap-4 bg-white dark:bg-gray-900 rounded-2xl shadow-xl border border-gray-100 dark:border-white/6"
	>
		<h2 class="text-sm font-semibold text-gray-900 dark:text-white">Start a New Project</h2>
		<div class="flex flex-col gap-1.5">
			<label for="project-name-input" class="text-xs text-gray-500 dark:text-gray-400 font-medium"
				>Project Name</label
			>
			<input
				id="project-name-input"
				type="text"
				bind:value={newProjectName}
				placeholder="my-new-app"
				class="w-full h-8 px-2.5 rounded-lg text-xs bg-gray-100 dark:bg-white/6 text-gray-700 dark:text-gray-300 border border-gray-200 dark:border-white/8 outline-none focus:border-blue-400 dark:focus:border-blue-500 transition-colors font-mono"
				onkeydown={(e) => {
					if (e.key === 'Enter') handleCreateProject();
				}}
			/>
		</div>
		<div class="flex items-center justify-end gap-2 shrink-0">
			<button
				class="text-xs text-gray-500 hover:text-gray-700 dark:hover:text-gray-300 px-3 py-1.5 rounded-lg transition-colors duration-100 cursor-pointer"
				onclick={() => {
					showNewProjectModal = false;
					newProjectName = '';
				}}
			>
				Cancel
			</button>
			<button
				class="text-xs text-white dark:text-black bg-gray-950 dark:bg-white hover:bg-gray-800 dark:hover:bg-gray-200 px-3 py-1.5 rounded-lg transition-colors duration-100 font-medium cursor-pointer"
				onclick={handleCreateProject}
				disabled={creatingProject}
			>
				{creatingProject ? 'Creating...' : 'Create'}
			</button>
		</div>
	</Modal>
{/if}

<style>
	@reference "../app.css";

	/* Container */
	.split-container {
		display: flex;
		width: 100%;
		height: 100%;
		position: relative;
		overflow: hidden;
	}

	.split-horizontal {
		flex-direction: row;
	}

	.split-vertical {
		flex-direction: column;
	}

	/* Panes */
	.split-pane {
		display: flex;
		flex-direction: column;
		overflow: hidden;
		min-width: 0;
		min-height: 0;
	}

	/* Single pane takes all space */
	.split-pane:only-child {
		flex: 1;
		width: 100%;
		height: 100%;
	}

	.pane-content {
		flex: 1;
		min-height: 0;
		min-width: 0;
		overflow: hidden;
		position: relative;
	}

	/* ── Divider ─────────────────────────────────────────────── */
	.split-divider {
		flex-shrink: 0;
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 10;
		position: relative;
		transition: background 0.15s;
	}

	.split-divider-h {
		width: 6px;
		cursor: col-resize;
	}

	.split-divider-v {
		height: 6px;
		cursor: row-resize;
	}

	.split-divider-handle {
		display: none;
	}

	.split-divider::before {
		content: '';
		position: absolute;
		z-index: -1;
	}

	.split-divider-h::before {
		width: 1px;
		height: 100%;
		left: 50%;
		transform: translateX(-50%);
		background: oklch(0.92 0 0);
	}

	:global(.dark) .split-divider-h::before {
		background: rgba(255, 255, 255, 0.06);
	}

	.split-divider-v::before {
		height: 1px;
		width: 100%;
		top: 50%;
		transform: translateY(-50%);
		background: oklch(0.92 0 0);
	}

	:global(.dark) .split-divider-v::before {
		background: rgba(255, 255, 255, 0.06);
	}

	.split-divider:hover,
	.is-dragging .split-divider {
		background: rgba(150, 150, 150, 0.12);
	}

	/* Drag state */
	.is-dragging {
		user-select: none;
	}

	.is-dragging.split-horizontal {
		cursor: col-resize;
	}

	.is-dragging.split-vertical {
		cursor: row-resize;
	}

	/* ── Drop zones for drag-to-split ─────────────────── */
	.split-drop-zone {
		position: absolute;
		z-index: 15;
		background: oklch(0.65 0.15 250 / 0.08);
		border: 2px dashed oklch(0.65 0.15 250 / 0.3);
		border-radius: 8px;
		pointer-events: none;
	}

	.split-drop-right {
		top: 8px;
		right: 8px;
		bottom: 8px;
		width: 45%;
	}

	.split-drop-bottom {
		left: 8px;
		right: 8px;
		bottom: 8px;
		height: 45%;
	}

	/* ── Persisted file editor tabs ────────────────────── */
	.persisted-tab {
		position: absolute;
		inset: 0;
		z-index: 1;
		overflow: hidden;
	}

	.persisted-tab-hidden {
		visibility: hidden;
		z-index: 0;
		pointer-events: none;
	}
</style>
