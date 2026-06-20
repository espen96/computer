<script lang="ts">
	import { toast } from 'svelte-sonner';
	import Icon from '../Icon.svelte';
	import { theme, streamingBehavior, showUpdateToastPref, mainProjectDirectory, workspaceMode } from '$lib/stores';
	import type { Theme, StreamingBehavior } from '$lib/stores';
	import { t, locale, changeLocale, supportedLocales } from '$lib/i18n';
	import { notificationsEnabled, notificationSound } from '$lib/stores/chat';
	import { fetchJSON } from '$lib/apis';
	import { updateConfig } from '$lib/apis/admin';
	import { getChatWorkspaceRoot, setChatWorkspaceRoot } from '$lib/apis/admin';
	import { session } from '$lib/session';
	import ToggleSwitch from '../common/ToggleSwitch.svelte';
	import { onMount } from 'svelte';

	function setTheme(v: Theme) {
		theme.set(v);
	}

	// ── Webhook URL ─────────────────────────────────────────────
	let webhookUrl = $state('');
	let webhookUrlOriginal = $state('');
	let saving = $state(false);

	// ── Chat workspace root (admin) ─────────────────────────────
	let chatWorkspaceRoot = $state('');
	let chatWorkspaceRootDefault = $state('');
	let chatWorkspaceRootOriginal = $state('');

	let dirty = $derived(
		webhookUrl.trim() !== webhookUrlOriginal ||
			($session?.role === 'admin' && chatWorkspaceRoot.trim() !== chatWorkspaceRootOriginal)
	);

	onMount(async () => {
		try {
			const data = await fetchJSON<{ config: Record<string, any> }>(
				'/api/admin/config/notifications'
			);
			const url = data.config?.['notifications.webhook_url'] || '';
			webhookUrl = url;
			webhookUrlOriginal = url;
		} catch {}

		if ($session?.role === 'admin') {
			try {
				const rootData = await getChatWorkspaceRoot();
				chatWorkspaceRoot = rootData.path;
				chatWorkspaceRootDefault = rootData.default;
				chatWorkspaceRootOriginal = rootData.path;
			} catch {}
		}
	});

	async function save() {
		saving = true;
		try {
			await updateConfig({ 'notifications.webhook_url': webhookUrl.trim() || null });
			webhookUrlOriginal = webhookUrl.trim();

			if ($session?.role === 'admin' && chatWorkspaceRoot.trim() !== chatWorkspaceRootOriginal) {
				await setChatWorkspaceRoot(chatWorkspaceRoot.trim() || chatWorkspaceRootDefault);
				chatWorkspaceRootOriginal = chatWorkspaceRoot.trim();
			}

			toast.success($t('settings.saved'));
		} catch {
			toast.error($t('general.webhookUrlSaveFailed'));
		} finally {
			saving = false;
		}
	}

	async function toggleNotifications() {
		if (!$notificationsEnabled) {
			if ('Notification' in window) {
				const permission = await Notification.requestPermission();
				if (permission === 'granted') {
					notificationsEnabled.set(true);
				} else {
					toast.error($t('general.notificationPermissionDenied'));
				}
			}
		} else {
			notificationsEnabled.set(false);
		}
	}
</script>

<div class="flex flex-col h-full">
	<div class="flex-1 min-h-0 overflow-y-auto scrollbar-hover pr-1.5 -mr-1.5">
		<h2 class="text-sm font-medium text-gray-900 dark:text-white mb-4">{$t('general.title')}</h2>

		<h3 class="text-xs text-gray-400 dark:text-gray-600 mb-2">{$t('general.theme')}</h3>
		<div class="flex gap-1">
			{#each [{ value: 'light' as Theme, label: $t('general.light'), icon: 'sun-light' }, { value: 'dark' as Theme, label: $t('general.dark'), icon: 'half-moon' }, { value: 'system' as Theme, label: $t('general.system'), icon: 'monitor' }] as opt}
				<button
					class="flex items-center gap-1.5 h-7 px-2.5 rounded-lg text-xs transition-colors duration-100
					{$theme === opt.value
						? 'bg-gray-200/50 dark:bg-white/8 text-gray-900 dark:text-white font-medium'
						: 'text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'}"
					onclick={() => setTheme(opt.value)}
				>
					<Icon name={opt.icon} size={13} />
					{opt.label}
				</button>
			{/each}
		</div>

		<h3 class="text-xs text-gray-400 dark:text-gray-600 mb-2 mt-5">{$t('general.language')}</h3>
		<select
			class="w-full max-w-[200px] bg-transparent text-[13px] text-gray-700 dark:text-gray-300 outline-none py-1 cursor-pointer"
			value={$locale}
			onchange={(e) => changeLocale((e.currentTarget as HTMLSelectElement).value)}
		>
			{#each supportedLocales as loc}
				<option value={loc.code}>{loc.label}</option>
			{/each}
		</select>

		<!-- Notifications -->
		<h3 class="text-xs text-gray-400 dark:text-gray-600 mb-2 mt-5">
			{$t('general.notifications')}
		</h3>

		<div class="flex flex-col gap-2.5">
			<!-- Browser notifications toggle -->
			<label class="flex items-center justify-between cursor-pointer">
				<span class="text-xs text-gray-600 dark:text-gray-400"
					>{$t('general.browserNotifications')}</span
				>
				<ToggleSwitch value={$notificationsEnabled} onchange={() => toggleNotifications()} />
			</label>
			<p class="text-[11px] text-gray-400 dark:text-gray-600 -mt-1">
				{$t('general.browserNotificationsDesc')}
			</p>

			<!-- Sound toggle -->
			<label class="flex items-center justify-between cursor-pointer">
				<span class="text-xs text-gray-600 dark:text-gray-400"
					>{$t('general.notificationSound')}</span
				>
				<ToggleSwitch value={$notificationSound} onchange={(v) => notificationSound.set(v)} />
			</label>

			<!-- Webhook URL -->
			<div class="mt-1">
				<label class="text-xs text-gray-600 dark:text-gray-400" for="webhook-url">
					{$t('general.webhookUrl')}
				</label>
				<input
					id="webhook-url"
					type="url"
					bind:value={webhookUrl}
					placeholder="https://hooks.slack.com/services/..."
					class="w-full mt-1 h-7 px-2 rounded-lg text-xs bg-gray-100 dark:bg-white/6 text-gray-700 dark:text-gray-300 border border-gray-200 dark:border-white/8 outline-none focus:border-blue-400 dark:focus:border-blue-500 transition-colors"
				/>
				<p class="text-[11px] text-gray-400 dark:text-gray-600 mt-1">
					{$t('general.webhookUrlHint')}
				</p>
			</div>
		</div>

		{#if $session?.role === 'admin'}
			<h3 class="text-xs text-gray-400 dark:text-gray-600 mb-2 mt-5">{$t('general.updates')}</h3>
			<label class="flex items-center justify-between cursor-pointer">
				<span class="text-xs text-gray-600 dark:text-gray-400"
					>{$t('general.updateNotifications')}</span
				>
				<ToggleSwitch value={$showUpdateToastPref} onchange={(v) => showUpdateToastPref.set(v)} />
			</label>
			<p class="text-[11px] text-gray-400 dark:text-gray-600 mt-1">
				{$t('general.updateNotificationsDesc')}
			</p>

			<h3 class="text-xs text-gray-400 dark:text-gray-600 mb-2 mt-5">
				{$t('general.chatWorkspaceRoot')}
			</h3>
			<div>
				<label class="text-xs text-gray-600 dark:text-gray-400" for="chat-workspace-root">
					{$t('general.chatWorkspaceRootPath')}
				</label>
				<input
					id="chat-workspace-root"
					type="text"
					bind:value={chatWorkspaceRoot}
					placeholder={chatWorkspaceRootDefault}
					class="w-full mt-1 h-7 px-2 rounded-lg text-xs bg-gray-100 dark:bg-white/6 text-gray-700 dark:text-gray-300 border border-gray-200 dark:border-white/8 outline-none focus:border-blue-400 dark:focus:border-blue-500 transition-colors font-mono"
				/>
				<p class="text-[11px] text-gray-400 dark:text-gray-600 mt-1">
					{$t('general.chatWorkspaceRootDesc')}
				</p>
			</div>
		{/if}

		<!-- Project Settings -->
		<h3 class="text-xs text-gray-400 dark:text-gray-600 mb-2 mt-5">Project Settings</h3>
		<div class="flex flex-col gap-2.5">
			<div>
				<label class="text-xs text-gray-600 dark:text-gray-400" for="main-project-dir">
					Main Project Directory
				</label>
				<input
					id="main-project-dir"
					type="text"
					value={$mainProjectDirectory}
					oninput={(e) => mainProjectDirectory.set((e.target as HTMLInputElement).value)}
					placeholder="e.g. C:/Users/name/Projects"
					class="w-full mt-1 h-7 px-2 rounded-lg text-xs bg-gray-100 dark:bg-white/6 text-gray-700 dark:text-gray-300 border border-gray-200 dark:border-white/8 outline-none focus:border-blue-400 dark:focus:border-blue-500 transition-colors font-mono"
				/>
				<p class="text-[11px] text-gray-400 dark:text-gray-600 mt-1">
					The directory where new projects will be created.
				</p>
			</div>

			<div>
				<h4 class="text-xs text-gray-600 dark:text-gray-400 mb-2">Workspace Selection Behavior</h4>
				<div class="flex gap-1">
					{#each [{ value: 'computer', label: 'Computer Mode' }, { value: 'project', label: 'Project Mode' }] as opt}
						<button
							class="flex items-center gap-1.5 h-7 px-2.5 rounded-lg text-xs transition-colors duration-100
							{$workspaceMode === opt.value
								? 'bg-gray-200/50 dark:bg-white/8 text-gray-900 dark:text-white font-medium'
								: 'text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'}"
							onclick={() => workspaceMode.set(opt.value as 'project' | 'computer')}
						>
							{opt.label}
						</button>
					{/each}
				</div>
				<p class="text-[11px] text-gray-400 dark:text-gray-600 mt-1">
					{$workspaceMode === 'computer'
						? 'Workspaces are computer paths you select.'
						: 'New chats and projects are created at the path set in the settings.'}
				</p>
			</div>
		</div>

		<h3 class="text-xs text-gray-400 dark:text-gray-600 mb-2 mt-5">{$t('general.messageQueue')}</h3>
		<div class="flex gap-1">
			{#each [{ value: 'queue' as StreamingBehavior, label: $t('general.queue') }, { value: 'interrupt' as StreamingBehavior, label: $t('general.interrupt') }] as opt}
				<button
					class="flex items-center gap-1.5 h-7 px-2.5 rounded-lg text-xs transition-colors duration-100
					{$streamingBehavior === opt.value
						? 'bg-gray-200/50 dark:bg-white/8 text-gray-900 dark:text-white font-medium'
						: 'text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'}"
					onclick={() => streamingBehavior.set(opt.value)}
				>
					{opt.label}
				</button>
			{/each}
		</div>
		<p class="text-[11px] text-gray-400 dark:text-gray-600 mt-1">
			{$streamingBehavior === 'queue' ? $t('general.queueDesc') : $t('general.interruptDesc')}
		</p>
	</div>

	<div class="shrink-0 pt-3 flex justify-end">
		<button
			class="text-[13px] text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-colors duration-100
			disabled:opacity-30 disabled:pointer-events-none"
			onclick={save}
			disabled={saving}
		>
			{#if saving}{$t('settings.saving')}{:else}{$t('settings.save')}{/if}
		</button>
	</div>
</div>
