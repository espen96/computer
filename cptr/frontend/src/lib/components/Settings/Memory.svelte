<script lang="ts">
	import { onMount } from 'svelte';
	import { toast } from 'svelte-sonner';
	import ToggleSwitch from '$lib/components/common/ToggleSwitch.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import ModelSelector from '$lib/components/common/ModelSelector.svelte';
	import { currentWorkspace } from '$lib/stores';
	import {
		getMemory,
		updateMemory,
		updateMemorySettings,
		type MemorySettings
	} from '$lib/apis/memory';

	let loading = $state(true);
	let saving = $state(false);
	let settings = $state<MemorySettings | null>(null);
	let userEntries = $state<string[]>([]);
	let userUsage = $state('');
	let reviewModelType = $state('same');

	const workspace = $derived($currentWorkspace?.path || '');

	onMount(() => {
		load();
	});

	async function load() {
		loading = true;
		try {
			const state = await getMemory(workspace);
			settings = state.settings;
			userEntries = state.user.entries;
			userUsage = state.user.usage;
			reviewModelType = settings?.review_model_id ? 'specific' : 'same';
		} catch {
			toast.error('Failed to load memory');
		} finally {
			loading = false;
		}
	}

	async function saveSettings() {
		if (!settings) return;
		saving = true;
		try {
			const result = await updateMemorySettings(settings);
			settings = result.settings;
			toast.success('Saved');
		} catch {
			toast.error('Failed to save memory settings');
		} finally {
			saving = false;
		}
	}

	async function removeUserMemoryEntry(entry: string) {
		try {
			await updateMemory('user', workspace, [{ action: 'remove', old_text: entry.slice(0, 120) }]);
			await load();
		} catch {
			toast.error('Failed to update memory');
		}
	}

</script>

<div class="flex flex-col h-full">
	{#if loading || !settings}
		<div class="flex justify-center py-8"><Spinner size={16} /></div>
	{:else}
		<div class="flex-1 min-h-0 overflow-y-auto scrollbar-hover pr-1.5 -mr-1.5">
			<h2 class="text-sm font-medium text-gray-900 dark:text-white mb-4">Memory</h2>

			<h3 class="text-xs text-gray-400 dark:text-gray-600 mb-2">Behavior</h3>
			<div class="flex flex-col gap-2.5">
				<label class="flex items-center justify-between cursor-pointer">
					<span class="text-xs text-gray-600 dark:text-gray-400">Enable memory</span>
					<ToggleSwitch
						value={settings.enabled}
						onchange={(v) => (settings = { ...settings!, enabled: v })}
					/>
				</label>

				{#if settings.enabled}
					<label class="flex items-center justify-between cursor-pointer">
						<span class="text-xs text-gray-600 dark:text-gray-400">Assistant can save memories</span>
						<ToggleSwitch
							value={settings.tool_enabled}
							onchange={(v) => (settings = { ...settings!, tool_enabled: v })}
						/>
					</label>

					<label class="flex items-center justify-between cursor-pointer">
						<span class="text-xs text-gray-600 dark:text-gray-400">Background review</span>
						<ToggleSwitch
							value={settings.background_review_enabled}
							onchange={(v) => (settings = { ...settings!, background_review_enabled: v })}
						/>
					</label>

					{#if settings.background_review_enabled}
						<div class="mt-1 pl-4 border-l-2 border-gray-100 dark:border-white/5 space-y-3">
							<div>
								<span class="text-xs text-gray-600 dark:text-gray-400 block mb-1.5"
									>Model for background review</span
								>
								<div class="flex gap-2">
									{#each [{ value: 'same', label: 'Same as active model' }, { value: 'specific', label: 'Specific model' }] as opt}
										<button
											class="flex items-center gap-1.5 h-7 px-2.5 rounded-lg text-xs transition-colors duration-100
											{reviewModelType === opt.value
												? 'bg-gray-200/50 dark:bg-white/8 text-gray-900 dark:text-white font-medium'
												: 'text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'}"
											onclick={() => {
												reviewModelType = opt.value;
												if (reviewModelType === 'same') {
													settings = { ...settings!, review_model_id: '' };
												}
											}}
										>
											{opt.label}
										</button>
									{/each}
								</div>
							</div>

							{#if reviewModelType === 'specific'}
								<div class="mt-2">
									<ModelSelector
										bind:selectedModel={settings.review_model_id}
										preferAbove={false}
										align="start"
									/>
								</div>
							{/if}
						</div>
					{/if}
				{/if}
			</div>

			{#if settings.enabled}
				<h3 class="text-xs text-gray-400 dark:text-gray-600 mb-2 mt-5">Limits</h3>
				<div class="flex flex-col gap-2.5">
					<div>
						<label class="text-xs text-gray-600 dark:text-gray-400" for="memory-review-interval">
							Review every
						</label>
						<input
							id="memory-review-interval"
							type="number"
							min="1"
							bind:value={settings.review_interval_turns}
							class="w-full mt-1 h-7 px-2 rounded-lg text-xs bg-gray-100 dark:bg-white/6 text-gray-700 dark:text-gray-300 border border-gray-200 dark:border-white/8 outline-none transition-colors"
						/>
					</div>
					<div>
						<label class="text-xs text-gray-600 dark:text-gray-400" for="memory-user-limit">
							User limit
						</label>
						<input
							id="memory-user-limit"
							type="number"
							min="250"
							bind:value={settings.user_char_limit}
							class="w-full mt-1 h-7 px-2 rounded-lg text-xs bg-gray-100 dark:bg-white/6 text-gray-700 dark:text-gray-300 border border-gray-200 dark:border-white/8 outline-none transition-colors"
						/>
					</div>
				</div>

				{#if userEntries.length > 0}
					<h3 class="text-xs text-gray-400 dark:text-gray-600 mb-2 mt-5">User Memory</h3>
					<div class="flex flex-col gap-2.5">
						{#each userEntries as entry}
							<div class="flex items-start justify-between gap-3">
								<div class="min-w-0 whitespace-pre-wrap break-words text-xs text-gray-600 dark:text-gray-400">
									{entry}
								</div>
								<button
									class="shrink-0 text-xs text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
									onclick={() => removeUserMemoryEntry(entry)}
								>
									Remove
								</button>
							</div>
						{/each}
						<p class="text-[11px] text-gray-400 dark:text-gray-600 -mt-1">{userUsage}</p>
					</div>
				{/if}

			{/if}
		</div>

		<div class="shrink-0 pt-3 flex justify-end">
			<button
				class="text-[13px] text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-colors duration-100 disabled:opacity-50"
				onclick={saveSettings}
				disabled={saving}
			>
				{saving ? 'Saving' : 'Save'}
			</button>
		</div>
	{/if}
</div>
