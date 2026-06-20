<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import {
		workspaceList,
		currentWorkspace,
		removeWorkspace,
		renameWorkspace,
		reorderWorkspaces,
		sidebarOpen,
		sidebarWidth,
		appVersion,
		showChangelog,
		showSearch,
		showMemoryModal,
		memoryModalScope,
		chatList,
		renameChat,
		loadChatList,
		workspaceMode
	} from '$lib/stores';
	import Sortable from 'sortablejs';
	import Icon from './Icon.svelte';
	import KeyPill from './KeyPill.svelte';
	import DirectoryPicker from './DirectoryPicker.svelte';
	import NewProjectModal from './NewProjectModal.svelte';
	import DropdownMenu from './DropdownMenu.svelte';
	import SettingsModal, { type Tab } from './SettingsModal.svelte';

	import { tooltip } from '$lib/tooltip';
	import { session, clearSession } from '$lib/session';
	import { getWelcome } from '$lib/apis/state';
	import { getChats, type ChatInfo } from '$lib/apis/chat';
	import ChatItem from './common/ChatItem.svelte';
	import { chatEnabled } from '$lib/stores/chat';
	import { socketStore } from '$lib/stores/socket.svelte';
	import { t } from '$lib/i18n';
	import { keybindings, formatChord } from '$lib/stores/keybindings';

	import { onMount, onDestroy } from 'svelte';

	let showPicker = $state(false);
	let showNewProjectModal = $state(false);
	let showMenu = $state(false);
	let showSettings = $state(false);
	let settingsTab = $state<Tab>('general');
	let wsMenuPath = $state<string | null>(null);
	let wsMenuAnchor = $state<HTMLElement | null>(null);

	let menuButtonEl: HTMLButtonElement | undefined = $state();
	let wsListEl: HTMLDivElement | undefined = $state();
	let sortable: Sortable | null = null;
	let unbindSocketListener: (() => void) | null = null;

	// ── Per-workspace chat history ──────────────────────────────
	let expandedWorkspaces = $state<Set<string>>(new Set());
	let wsChatsCache = $state<Map<string, ChatInfo[]>>(new Map());
	let wsChatsLoading = $state<Set<string>>(new Set());

	// Keybinding shortcut display for search
	let searchShortcut = $derived(formatChord($keybindings.quickOpen));

	function toggleWorkspaceExpand(path: string) {
		const next = new Set(expandedWorkspaces);
		if (next.has(path)) {
			next.delete(path);
		} else {
			next.add(path);
			// Lazy-fetch chats if not cached
			if (!wsChatsCache.has(path)) {
				fetchWorkspaceChats(path);
			}
		}
		expandedWorkspaces = next;
	}

	async function fetchWorkspaceChats(path: string) {
		if (wsChatsLoading.has(path)) return;
		wsChatsLoading = new Set([...wsChatsLoading, path]);
		try {
			const data = await getChats(path, 5, 0, 'updated_at', 'desc');
			wsChatsCache = new Map([...wsChatsCache, [path, data.chats || []]]);
		} catch {
			wsChatsCache = new Map([...wsChatsCache, [path, []]]);
		} finally {
			const next = new Set(wsChatsLoading);
			next.delete(path);
			wsChatsLoading = next;
		}
	}

	function relativeTime(ts: number): string {
		// ts is in milliseconds
		const now = Date.now();
		const diffMs = now - ts;
		const diffSec = Math.floor(diffMs / 1000);
		if (diffSec < 60) return 'now';
		const diffMin = Math.floor(diffSec / 60);
		if (diffMin < 60) return `${diffMin}m`;
		const diffHr = Math.floor(diffMin / 60);
		if (diffHr < 24) return `${diffHr}h`;
		const diffDay = Math.floor(diffHr / 24);
		if (diffDay < 30) return `${diffDay}d`;
		const diffMonth = Math.floor(diffDay / 30);
		return `${diffMonth}mo`;
	}

	function handleSidebarChatClick(chatId: string, wsPath: string, title: string) {
		goto(`/?workspace=${encodeURIComponent(wsPath)}&chatId=${encodeURIComponent(chatId)}`);
		if (typeof window !== 'undefined' && window.innerWidth < 768) {
			sidebarOpen.set(false);
		}
	}

	function handleShowMoreChats(wsPath: string) {
		goto(`/?workspace=${encodeURIComponent(wsPath)}&chatId`);
		if (typeof window !== 'undefined' && window.innerWidth < 768) {
			sidebarOpen.set(false);
		}
	}

	function handleNewChat(wsPath: string) {
		goto(`/?workspace=${encodeURIComponent(wsPath)}&chatId`);
		if (typeof window !== 'undefined' && window.innerWidth < 768) {
			sidebarOpen.set(false);
		}
	}

	// Socket listener for chat events — invalidate cache when chats update
	const seenChatIds = new Set<string>();

	function handleChatEvent(data: {
		chat_id: string;
		done?: boolean;
		title?: string;
		delta?: string;
		workspace?: string;
	}) {
		// Re-fetch on done, title update, or first event of a new chat
		const isNew = !seenChatIds.has(data.chat_id);
		seenChatIds.add(data.chat_id);

		if (!data.done && !data.title && !isNew) return;

		// Invalidate cache for ALL workspaces so re-expanding shows fresh data
		wsChatsCache = new Map();

		// Re-fetch immediately for any currently expanded workspaces
		for (const path of expandedWorkspaces) {
			fetchWorkspaceChats(path);
		}

		// Also reload the chat list so chat-mode titles update in real-time
		loadChatList();
	}

	const MIN_WIDTH = 160;
	const MAX_WIDTH = 400;
	let isResizing = $state(false);

	function startResize(e: PointerEvent) {
		// Only allow resize on md+ screens
		if (typeof window !== 'undefined' && window.innerWidth < 768) return;
		e.preventDefault();
		isResizing = true;
		const startX = e.clientX;
		const startWidth = $sidebarWidth;

		function onMove(ev: PointerEvent) {
			const delta = ev.clientX - startX;
			const newWidth = Math.round(Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, startWidth + delta)));
			sidebarWidth.set(newWidth);
		}

		function onUp() {
			isResizing = false;
			window.removeEventListener('pointermove', onMove);
			window.removeEventListener('pointerup', onUp);
			document.body.style.cursor = '';
			document.body.style.userSelect = '';
		}

		window.addEventListener('pointermove', onMove);
		window.addEventListener('pointerup', onUp);
		document.body.style.cursor = 'col-resize';
		document.body.style.userSelect = 'none';
	}

	// Current workspace path from URL
	const currentPath = $derived($page.url.searchParams.get('workspace'));

	function isTouchDevice(): boolean {
		return (
			typeof window !== 'undefined' && ('ontouchstart' in window || navigator.maxTouchPoints > 0)
		);
	}

	function handleWorkspaceClick(e: MouseEvent, path: string) {
		// Let Cmd/Ctrl+click open in new tab naturally (it's an <a>)
		if (e.metaKey || e.ctrlKey) return;
		e.preventDefault();
		goto(`/?workspace=${encodeURIComponent(path)}`);
		if (typeof window !== 'undefined' && window.innerWidth < 768) {
			sidebarOpen.set(false);
		}
	}

	function openWsMenu(e: MouseEvent, path: string) {
		e.stopPropagation();
		e.preventDefault();
		wsMenuAnchor = e.currentTarget as HTMLElement;
		wsMenuPath = path;
	}

	function closeWsMenu() {
		wsMenuPath = null;
		wsMenuAnchor = null;
	}

	// ── Workspace rename ───────────────────────────────────────────
	let renamingPath = $state<string | null>(null);
	let renameValue = $state('');
	let renameInputEl: HTMLInputElement | undefined = $state();

	// ── Chat-mode workspace rename ────────────────────────────────
	let renamingChatPath = $state<string | null>(null);
	let renameChatValue = $state('');
	let renameChatInputEl: HTMLInputElement | undefined = $state();
	let chatMenuPath = $state<string | null>(null);
	let chatMenuAnchor = $state<HTMLElement | null>(null);

	// ── Workspace expand chat menu ────────────────────────────────
	let wsChatMenuId = $state<string | null>(null);
	let wsChatMenuAnchor = $state<HTMLElement | null>(null);
	let wsChatMenuPath = $state<string | null>(null);

	$effect(() => {
		if (renamingPath && renameInputEl) {
			requestAnimationFrame(() => {
				renameInputEl?.focus();
				renameInputEl?.select();
			});
		}
	});

	function startRename(path: string, currentName: string) {
		renamingPath = path;
		renameValue = currentName;
		closeWsMenu();
	}

	async function commitRename() {
		const path = renamingPath;
		const val = renameValue.trim();
		renamingPath = null;
		if (!path || !val) return;
		await renameWorkspace(path, val);
	}

	function cancelRename() {
		renamingPath = null;
	}

	// ── Chat-mode workspace rename ────────────────────────────────

	$effect(() => {
		if (renamingChatPath && renameChatInputEl) {
			requestAnimationFrame(() => {
				renameChatInputEl?.focus();
				renameChatInputEl?.select();
			});
		}
	});

	function openChatMenu(e: MouseEvent, path: string) {
		e.stopPropagation();
		e.preventDefault();
		chatMenuAnchor = e.currentTarget as HTMLElement;
		chatMenuPath = path;
	}

	function closeChatMenu() {
		chatMenuPath = null;
		chatMenuAnchor = null;
	}

	// ── Workspace expand chat menu ────────────────────────────────

	function openWsChatMenu(e: MouseEvent, chatId: string, wsPath: string) {
		e.stopPropagation();
		e.preventDefault();
		wsChatMenuAnchor = e.currentTarget as HTMLElement;
		wsChatMenuId = chatId;
		wsChatMenuPath = wsPath;
	}

	function closeWsChatMenu() {
		wsChatMenuId = null;
		wsChatMenuAnchor = null;
		wsChatMenuPath = null;
	}

	async function handleDeleteWsChat(chatId: string) {
		closeWsChatMenu();
		const { deleteChat } = await import('$lib/apis/chat');
		await deleteChat(chatId);
		// Refresh the workspace chat cache
		if (wsChatMenuPath) {
			fetchWorkspaceChats(wsChatMenuPath);
		}
	}

	function startRenameChat(path: string, currentName: string) {
		renamingChatPath = path;
		renameChatValue = currentName;
		closeChatMenu();
	}

	async function commitRenameChat() {
		const path = renamingChatPath;
		const val = renameChatValue.trim();
		renamingChatPath = null;
		if (!path || !val) return;
		// Extract chat ID from workspace path (format: {root}/{chat_id})
		const chatId = path.split(/[/\\]/).pop() || '';
		await renameChat(chatId, val);
	}

	function cancelRenameChat() {
		renamingChatPath = null;
	}

	async function handleDeleteChatMode(chatPath: string) {
		closeChatMenu();
		await removeWorkspace(chatPath);
	}

	function closeSidebar() {
		sidebarOpen.set(false);
	}

	function openSettings() {
		showMenu = false;
		showSettings = true;
	}

	function logout() {
		clearSession();
	}

	async function handleRemoveWorkspace(path: string) {
		closeWsMenu();
		await removeWorkspace(path);
		// If we removed the workspace we're currently viewing, go home
		if (currentPath === path) {
			goto('/');
		}
	}

	// ── Chat-mode workspace helpers ──────────────────────────────

	interface ChatDateGroup {
		label: string;
		chats: typeof $chatList;
	}

	let expandedChatGroups = $state<Set<string>>(
		new Set(['today', 'yesterday', 'previous7Days', 'previous30Days', 'older'])
	);

	function toggleChatGroup(label: string) {
		const next = new Set(expandedChatGroups);
		if (next.has(label)) {
			next.delete(label);
		} else {
			next.add(label);
		}
		expandedChatGroups = next;
	}

	function groupChatsByDate(chats: typeof $chatList): ChatDateGroup[] {
		const now = new Date();
		const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
		const yesterdayStart = todayStart - 86400000;
		const weekStart = todayStart - 7 * 86400000;
		const monthStart = todayStart - 30 * 86400000;

		const groups: Record<string, typeof $chatList> = {
			today: [],
			yesterday: [],
			previous7Days: [],
			previous30Days: [],
			older: []
		};

		for (const chat of chats) {
			// Backend stores seconds, JS uses milliseconds
			const ts = (chat.updated_at || chat.created_at) * 1000;
			if (ts >= todayStart) {
				groups.today.push(chat);
			} else if (ts >= yesterdayStart) {
				groups.yesterday.push(chat);
			} else if (ts >= weekStart) {
				groups.previous7Days.push(chat);
			} else if (ts >= monthStart) {
				groups.previous30Days.push(chat);
			} else {
				groups.older.push(chat);
			}
		}

		const result: ChatDateGroup[] = [];
		if (groups.today.length) result.push({ label: 'today', chats: groups.today });
		if (groups.yesterday.length) result.push({ label: 'yesterday', chats: groups.yesterday });
		if (groups.previous7Days.length)
			result.push({ label: 'previous7Days', chats: groups.previous7Days });
		if (groups.previous30Days.length)
			result.push({ label: 'previous30Days', chats: groups.previous30Days });
		if (groups.older.length) result.push({ label: 'older', chats: groups.older });
		return result;
	}

	const chatDateGroups = $derived(groupChatsByDate($chatList));

	function handleChatItemClick(chat: (typeof $chatList)[0]) {
		goto(`/?workspace=${encodeURIComponent(chat.path)}`);
		if (typeof window !== 'undefined' && window.innerWidth < 768) {
			sidebarOpen.set(false);
		}
	}

	function handleNewChatMode() {
		// Navigate to home with a flag that triggers new chat creation
		goto('/?newChat=1');
		if (typeof window !== 'undefined' && window.innerWidth < 768) {
			sidebarOpen.set(false);
		}
	}

	onMount(() => {
		// Enable drag-reorder on non-touch devices
		if (wsListEl && !isTouchDevice()) {
			sortable = Sortable.create(wsListEl, {
				animation: 150,
				ghostClass: 'opacity-30',
				dragClass: 'cursor-grabbing',
				direction: 'vertical',
				onEnd: (evt) => {
					if (evt.oldIndex != null && evt.newIndex != null && evt.oldIndex !== evt.newIndex) {
						reorderWorkspaces(evt.oldIndex, evt.newIndex);
					}
				}
			});
		}

		// Bind socket listener for chat cache invalidation
		unbindSocketListener = socketStore.on('events:chat', handleChatEvent);
	});

	onDestroy(() => {
		sortable?.destroy();
		unbindSocketListener?.();
		unbindSocketListener = null;
	});
</script>

{#if $sidebarOpen}
	<button
		class="fixed inset-0 bg-black/50 z-40 cursor-default md:hidden"
		onclick={closeSidebar}
		aria-label={$t('sidebar.closeSidebar')}
	></button>

	<aside class="sidebar" style="--sw: {$sidebarWidth}px;">
		<!-- Resize handle (md+ only) -->
		<div
			class="resize-handle"
			class:active={isResizing}
			role="separator"
			aria-orientation="vertical"
			onpointerdown={startResize}
			ondblclick={() => sidebarWidth.set(220)}
		></div>
		<!-- Logo header with collapse button -->
		<div
			class="flex items-center justify-between h-9 pl-3.5 pr-1.5 shrink-0 border-b border-gray-200 dark:border-white/6"
		>
			<a
				href="/"
				class="flex items-center gap-1.5 text-xs font-semibold tracking-tight text-gray-900 dark:text-white"
				onclick={(e) => {
					e.preventDefault();
					goto('/');
					if (typeof window !== 'undefined' && window.innerWidth < 768) sidebarOpen.set(false);
				}}><img src="/favicon.png" alt="cptr logo" class="w-4 h-4 hidden" />cptr</a
			>
			<button
				class="flex items-center justify-center w-7 h-7 rounded-lg text-gray-300 hover:text-gray-500 dark:text-gray-600 dark:hover:text-gray-400 transition-colors duration-100"
				onclick={() => sidebarOpen.set(false)}
				aria-label={$t('sidebar.collapse')}
				use:tooltip={$t('sidebar.collapse')}
			>
				<Icon name="sidebar-expand" size={14} />
			</button>
		</div>

		<!-- Search -->
		<div class="px-1.5 mt-1 shrink-0">
			<button
				class="group flex items-center gap-1.5 w-full h-7 px-2 rounded-lg text-xs text-gray-500 hover:text-gray-700 dark:hover:text-gray-300 transition-colors duration-100"
				onclick={() => showSearch.set(true)}
			>
				<Icon name="search" size={14} />
				<span class="flex-1 text-left overflow-hidden text-ellipsis whitespace-nowrap"
					>{$t('search.search')}</span
				>
				<KeyPill
					text={searchShortcut}
					class="ml-auto shrink-0 opacity-0 group-hover:opacity-100 transition-opacity duration-100"
				/>
			</button>
		</div>

		<!-- Automations (only when chat/LLM backend is available) -->
		{#if $chatEnabled}
			<div class="px-1.5 shrink-0">
				<a
					href="/automations"
					class="flex items-center gap-1.5 w-full h-7 px-2 rounded-lg text-xs text-gray-500 hover:text-gray-700 dark:hover:text-gray-300 transition-colors duration-100 no-underline"
					onclick={(e) => {
						e.preventDefault();
						goto('/automations');
						if (typeof window !== 'undefined' && window.innerWidth < 768) sidebarOpen.set(false);
					}}
				>
					<Icon name="clock" size={14} />
					<span class="flex-1 text-left overflow-hidden text-ellipsis whitespace-nowrap"
						>{$t('automations.title')}</span
					>
				</a>
			</div>
		{/if}
		<!-- Workspace section header -->
		<div class="flex items-center justify-between h-8 pl-3.5 pr-1.5 shrink-0">
			<span class="text-xs text-gray-400 dark:text-gray-500 font-bold"
				>{$t('sidebar.workspaces')}</span
			>
			<button
				class="flex items-center justify-center w-7 h-7 rounded-lg text-gray-300 hover:text-gray-500 dark:text-gray-600 dark:hover:text-gray-400 transition-colors duration-100"
				onclick={() => {
					if ($workspaceMode === 'project') {
						showNewProjectModal = true;
					} else {
						showPicker = true;
					}
				}}
				aria-label={$t('sidebar.addWorkspace')}
				use:tooltip={$t('sidebar.addWorkspace')}
			>
				<Icon name="plus" size={16} />
			</button>
		</div>

		<!-- Workspace list -->
		<div bind:this={wsListEl} class="overflow-y-auto px-1.5">
			{#each $workspaceList as ws (ws.path)}
				{@const isExpanded = expandedWorkspaces.has(ws.path)}
				{@const chats = wsChatsCache.get(ws.path)}
				{@const isLoading = wsChatsLoading.has(ws.path)}
				<div class="ws-item">
					<div
						class="group flex items-center gap-1 w-full h-7 px-2 rounded-lg text-xs font-medium transition-colors duration-100
						{ws.path === currentPath
							? 'bg-gray-200/50 text-gray-900 dark:bg-white/8 dark:text-white'
							: 'text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'}"
					>
						<a
							href="/?workspace={encodeURIComponent(ws.path)}"
							class="flex items-center gap-1 flex-1 min-w-0 no-underline text-inherit"
							onclick={(e) => handleWorkspaceClick(e, ws.path)}
						>
							<!-- Icon: folder by default, chevron on hover (when chat enabled) -->
							{#if $chatEnabled}
								<span
									class="ws-icon-toggle shrink-0"
									role="button"
									tabindex="-1"
									onclick={(e) => {
										e.stopPropagation();
										e.preventDefault();
										toggleWorkspaceExpand(ws.path);
									}}
									aria-label={isExpanded ? $t('sidebar.collapse') : $t('sidebar.addWorkspace')}
								>
									<span class="ws-icon-folder"><Icon name="folder" size={14} /></span>
									<span
										class="ws-icon-chevron"
										style="transform: rotate({isExpanded ? '90deg' : '0deg'})"
									>
										<Icon name="chevron-right" size={11} />
									</span>
								</span>
							{:else}
								<Icon name="folder" size={14} />
							{/if}
							{#if renamingPath === ws.path}
								<input
									bind:this={renameInputEl}
									bind:value={renameValue}
									type="text"
									class="flex-1 min-w-0 bg-transparent border-none outline-none text-xs text-gray-900 dark:text-white"
									onclick={(e) => e.stopPropagation()}
									onkeydown={(e) => {
										if (e.key === 'Enter') {
											e.preventDefault();
											commitRename();
										}
										if (e.key === 'Escape') {
											e.preventDefault();
											cancelRename();
										}
									}}
									onblur={commitRename}
									spellcheck="false"
								/>
							{:else}
								<span class="flex-1 text-left overflow-hidden text-ellipsis whitespace-nowrap"
									>{ws.name}</span
								>
							{/if}
						</a>
						<span
							class="flex items-center justify-center w-4 h-4 shrink-0 text-gray-400 opacity-0 group-hover:opacity-100 hover:text-gray-600 dark:hover:text-gray-300 transition-all duration-75"
							role="button"
							tabindex="-1"
							onclick={(e) => openWsMenu(e, ws.path)}
							aria-label={$t('sidebar.workspaceOptions')}
						>
							<Icon name="three-dots" size={11} />
						</span>
						{#if $chatEnabled}
							<span
								class="flex items-center justify-center w-4 h-4 shrink-0 text-gray-400 opacity-0 group-hover:opacity-100 hover:text-gray-600 dark:hover:text-gray-300 transition-all duration-75"
								role="button"
								tabindex="-1"
								onclick={() => handleNewChat(ws.path)}
								aria-label={$t('bar.newChat')}
								use:tooltip={$t('bar.newChat')}
							>
								<Icon name="pencil" size={11} />
							</span>
						{/if}
					</div>

					<!-- Collapsible chat list -->
					{#if $chatEnabled && isExpanded}
						<div class="ws-chats">
							{#if isLoading && !chats}
								<div class="ws-chat-loading">
									<span class="ws-chat-loading-dot"></span>
									<span class="ws-chat-loading-dot"></span>
									<span class="ws-chat-loading-dot"></span>
								</div>
							{:else if chats && chats.length > 0}
								{#each chats as chat (chat.id)}
									<ChatItem
										{chat}
										onclick={() => handleSidebarChatClick(chat.id, ws.path, chat.title)}
										onmenu={(e) => openWsChatMenu(e, chat.id, ws.path)}
									/>
								{/each}
								<button class="ws-chat-show-more" onclick={() => handleShowMoreChats(ws.path)}>
									{$t('sidebar.showMore')}
								</button>
							{:else if chats}
								<!-- No chats yet, show nothing -->
							{/if}
						</div>
					{/if}
				</div>
			{/each}

			{#if $workspaceList.length === 0}
				<div class="flex flex-col items-center justify-center py-12">
					<p class="text-xs text-gray-400 dark:text-gray-600">{$t('sidebar.noWorkspaces')}</p>
				</div>
			{/if}
		</div>

		<!-- Chats section header -->
		{#if $chatEnabled}
			<div class="flex items-center justify-between h-8 pl-3.5 pr-1.5 shrink-0 font-bold">
				<span class="text-xs text-gray-400 dark:text-gray-500">{$t('sidebar.chats')}</span>
				<button
					class="flex items-center justify-center w-7 h-7 rounded-lg text-gray-300 hover:text-gray-500 dark:text-gray-600 dark:hover:text-gray-400 transition-colors duration-100"
					onclick={handleNewChatMode}
					aria-label={$t('sidebar.newChat')}
					use:tooltip={$t('sidebar.newChat')}
				>
					<Icon name="plus" size={16} />
				</button>
			</div>

			<!-- Chat list -->
			<div class="overflow-y-auto px-1.5 flex-1">
				{#if $chatList.length === 0}
					<div class="flex flex-col items-center justify-center py-8">
						<p class="text-xs text-gray-400 dark:text-gray-600">{$t('sidebar.noChats')}</p>
					</div>
				{:else}
					{#each chatDateGroups as group (group.label)}
						<div class="mb-1">
							<button
								class="flex items-center gap-1 w-full h-6 px-2 text-[10px] font-medium text-gray-400 dark:text-gray-600 hover:text-gray-600 dark:hover:text-gray-400 transition-colors duration-75 uppercase tracking-wider"
								onclick={() => toggleChatGroup(group.label)}
							>
								<span
									class="inline-block transition-transform duration-150"
									style="transform: rotate({expandedChatGroups.has(group.label)
										? '90deg'
										: '0deg'})"
								>
									<Icon name="chevron-right" size={9} />
								</span>
								{$t(`sidebar.chatGroup.${group.label}`)}
								<span class="text-gray-300 dark:text-gray-700 font-normal normal-case ml-0.5"
									>{group.chats.length}</span
								>
							</button>
							{#if expandedChatGroups.has(group.label)}
								{#each group.chats as chat (chat.path)}
									<div
										class="group flex items-center gap-1.5 w-full h-7 px-2 rounded-md cursor-pointer transition-colors duration-75
										hover:bg-gray-50 dark:hover:bg-white/3
										{chat.path === currentPath ? 'bg-gray-200/50 dark:bg-white/8' : ''}"
										role="button"
										tabindex="0"
										onclick={() => handleChatItemClick(chat)}
										onkeydown={(e) => {
											if (e.key === 'Enter') handleChatItemClick(chat);
										}}
									>
										{#if renamingChatPath === chat.path}
											<input
												bind:this={renameChatInputEl}
												bind:value={renameChatValue}
												type="text"
												class="flex-1 min-w-0 bg-transparent border-none outline-none text-xs text-gray-900 dark:text-white"
												onclick={(e) => e.stopPropagation()}
												onkeydown={(e) => {
													if (e.key === 'Enter') {
														e.preventDefault();
														commitRenameChat();
													}
													if (e.key === 'Escape') {
														e.preventDefault();
														cancelRenameChat();
													}
												}}
												onblur={commitRenameChat}
												spellcheck="false"
											/>
										{:else}
											<span class="flex-1 text-xs text-gray-500 dark:text-gray-500 truncate min-w-0"
												>{chat.name}</span
											>
										{/if}
										<span
											class="flex items-center justify-center w-4 h-4 shrink-0 text-gray-400 opacity-0 group-hover:opacity-100 hover:text-gray-600 dark:hover:text-gray-300 transition-all duration-75"
											role="button"
											tabindex="-1"
											onclick={(e) => openChatMenu(e, chat.path)}
											aria-label={$t('a11y.chatOptions')}
										>
											<Icon name="three-dots" size={11} />
										</span>
									</div>
								{/each}
							{/if}
						</div>
					{/each}
				{/if}
			</div>
		{/if}

		<!-- Settings and profile footer pinned to the bottom -->
		<div class="relative px-1 pb-0.5 shrink-0">
			<button
				bind:this={menuButtonEl}
				class="flex items-center gap-2 w-full h-8 px-2 rounded-lg text-xs font-medium text-gray-500 hover:text-gray-700 dark:hover:text-gray-300 transition-colors duration-100"
				onclick={() => (showMenu = !showMenu)}
			>
				<img
					src={$session?.profile_image_url || '/user.png'}
					alt="Avatar"
					class="w-5 h-5 rounded-full object-cover shrink-0"
				/>
				<span class="truncate"
					>{$session?.display_name || $session?.username || $t('sidebar.settings')}</span
				>
				{#if $appVersion}
					<button
						onclick={(e) => {
							e.stopPropagation();
							showChangelog.set(true);
						}}
						class="ml-auto text-[10px] text-gray-400 dark:text-gray-600 hover:text-gray-500 dark:hover:text-gray-400 font-mono hover:underline cursor-pointer hidden"
					>
						v{$appVersion}
					</button>
				{/if}
			</button>
		</div>
	</aside>
{/if}

{#if showMenu && menuButtonEl}
	<DropdownMenu
		anchor={menuButtonEl}
		matchWidth
		items={[
			...($session
				? [
						{
							label: $session.display_name || $session.username,
							image: $session.profile_image_url || '/user.png',
							onclick: () => {
								settingsTab = 'account';
								showMenu = false;
								showSettings = true;
							}
						}
					]
				: []),
			...($session ? [{ divider: true, label: '', onclick: () => {} }] : []),
			{
				label: 'Personal Memories',
				icon: 'brain',
				onclick: () => {
					memoryModalScope.set('user');
					showMemoryModal.set(true);
					showMenu = false;
				}
			},
			{
				label: $t('sidebar.settings'),
				icon: 'settings',
				shortcut: formatChord($keybindings.openSettings),
				onclick: openSettings
			},
			{ divider: true, label: '', onclick: () => {} },
			{ label: $t('sidebar.logOut'), icon: 'log-out', onclick: logout }
		]}
		onclose={() => (showMenu = false)}
	/>
{/if}

{#if showPicker}
	<DirectoryPicker onclose={() => (showPicker = false)} />
{/if}

{#if showNewProjectModal}
	<NewProjectModal onclose={() => (showNewProjectModal = false)} />
{/if}

{#if wsMenuPath && wsMenuAnchor}
	<DropdownMenu
		anchor={wsMenuAnchor}
		items={[
			{
				label: $t('sidebar.rename'),
				icon: 'pencil',
				onclick: () => {
					const ws = $workspaceList.find((w) => w.path === wsMenuPath);
					if (ws) startRename(ws.path, ws.name);
				}
			},
			{
				label: 'Workspace Memories',
				icon: 'brain',
				onclick: () => {
					memoryModalScope.set('workspace');
					showMemoryModal.set(true);
					closeWsMenu();
				}
			},
			{
				label: $t('sidebar.remove'),
				icon: 'xmark',
				onclick: () => handleRemoveWorkspace(wsMenuPath!)
			}
		]}
		onclose={closeWsMenu}
	/>
{/if}

{#if chatMenuPath && chatMenuAnchor}
	<DropdownMenu
		anchor={chatMenuAnchor}
		items={[
			{
				label: $t('sidebar.rename'),
				icon: 'pencil',
				onclick: () => {
					const chat = $chatList.find((c) => c.path === chatMenuPath);
					if (chat) startRenameChat(chat.path, chat.name);
				}
			},
			{
				label: $t('sidebar.remove'),
				icon: 'xmark',
				onclick: () => handleDeleteChatMode(chatMenuPath!)
			}
		]}
		onclose={closeChatMenu}
	/>
{/if}

{#if wsChatMenuId && wsChatMenuAnchor}
	<DropdownMenu
		anchor={wsChatMenuAnchor}
		items={[
			{
				label: $t('sidebar.remove'),
				icon: 'xmark',
				onclick: () => handleDeleteWsChat(wsChatMenuId!)
			}
		]}
		onclose={closeWsChatMenu}
	/>
{/if}

{#if showSettings}
	<SettingsModal
		initialTab={settingsTab}
		onclose={() => {
			showSettings = false;
			settingsTab = 'general';
		}}
	/>
{/if}

<style>
	@reference "../../app.css";

	.sidebar {
		position: fixed;
		left: 0;
		top: 0;
		bottom: 0;
		width: 75%;
		z-index: 50;
		display: flex;
		flex-direction: column;
		background: white;
		border-right: 1px solid var(--color-gray-200);
		padding-top: env(safe-area-inset-top, 0px);
	}

	:global(.dark) .sidebar {
		background: #111111;
		border-right-color: rgba(255, 255, 255, 0.06);
	}

	@media (min-width: 768px) {
		.sidebar {
			position: relative;
			z-index: auto;
			width: var(--sw, 220px);
		}
	}

	.resize-handle {
		display: none;
	}

	@media (min-width: 768px) {
		.resize-handle {
			display: block;
			position: absolute;
			right: -3px;
			top: 0;
			bottom: 0;
			width: 6px;
			cursor: col-resize;
			z-index: 10;
			transition: background 0.15s;
		}

		.resize-handle:hover,
		.resize-handle.active {
			background: rgba(150, 150, 150, 0.12);
		}
	}

	/* ── Workspace chat items ────────────────────────────── */

	.ws-item {
		margin-bottom: 2px;
	}

	.ws-expand-btn {
		display: none;
	}

	/* Icon toggle: folder by default, chevron on hover */
	.ws-icon-toggle {
		position: relative;
		display: flex;
		align-items: center;
		justify-content: center;
		width: 14px;
		height: 14px;
		cursor: pointer;
	}

	.ws-icon-folder {
		display: flex;
		transition: opacity 0.1s;
	}

	.ws-icon-chevron {
		position: absolute;
		inset: 0;
		display: flex;
		align-items: center;
		justify-content: center;
		opacity: 0;
		transition:
			opacity 0.1s,
			transform 0.1s;
		color: #9ca3af;
	}

	:global(.dark) .ws-icon-chevron {
		color: #6b7280;
	}

	/* On icon hover only, swap folder → chevron */
	.ws-icon-toggle:hover .ws-icon-folder {
		opacity: 0;
	}

	.ws-icon-toggle:hover .ws-icon-chevron {
		opacity: 1;
	}

	.ws-chats {
		padding-left: 4px;
		padding-bottom: 4px;
	}

	.ws-chat-show-more {
		display: block;
		width: 100%;
		padding: 2px 8px;
		border: none;
		background: none;
		cursor: pointer;
		font-size: 11px;
		color: #b0b5be;
		text-align: left;
		transition: color 0.1s;
	}

	.ws-chat-show-more:hover {
		color: #6b7280;
	}

	:global(.dark) .ws-chat-show-more {
		color: #6b7280;
	}

	:global(.dark) .ws-chat-show-more:hover {
		color: #9ca3af;
	}

	.ws-chat-loading {
		display: flex;
		gap: 4px;
		padding: 6px 8px;
	}

	.ws-chat-loading-dot {
		width: 4px;
		height: 4px;
		border-radius: 50%;
		background: #9ca3af;
		animation: dotPulse 1s ease-in-out infinite;
	}

	:global(.dark) .ws-chat-loading-dot {
		background: #6b7280;
	}

	.ws-chat-loading-dot:nth-child(2) {
		animation-delay: 0.15s;
	}

	.ws-chat-loading-dot:nth-child(3) {
		animation-delay: 0.3s;
	}

	@keyframes dotPulse {
		0%,
		100% {
			opacity: 0.3;
		}
		50% {
			opacity: 1;
		}
	}
</style>
