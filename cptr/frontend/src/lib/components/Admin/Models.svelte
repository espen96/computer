<script lang="ts">
	import { onMount } from 'svelte';
	import { toast } from 'svelte-sonner';
	import {
		getModelConfig,
		refreshModelList,
		updateModelConfig,
		deleteModelConfig,
		getAdminConfig,
		updateConfig,
		type ModelConfigEntry
	} from '$lib/apis/admin';
	import { t } from '$lib/i18n';
	import { tooltip } from '$lib/tooltip';
	import { refreshChatState } from '$lib/stores/chat';
	import Icon from '../Icon.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import ModelSelector from '$lib/components/common/ModelSelector.svelte';

	type ParamRow = { key: string; value: string };
	type ModelEntry = {
		id: string;
		originalId?: string;
		name: string;
		base_model: string;
		is_active: boolean;
		rows: ParamRow[];
		systemPrompt: string;
		dirty: boolean;
		isNew?: boolean;
	};

	let loading = $state(true);
	let saving = $state(false);
	let refreshing = $state(false);
	let models = $state<ModelEntry[]>([]);
	let rawModels = $state<{ id: string; name: string; provider: string; connection_id: string }[]>([]);
	let selectedModel = $state<ModelEntry | null>(null);
	let modelsToDelete = $state<string[]>([]);

	let globalRows = $state<ParamRow[]>([]);
	let globalSystemPrompt = $state('');
	let globalDirty = $state(false);
	let globalExpanded = $state(false);
	let showVariables = $state(false);

	// Default model
	let defaultModelId = $state('');

	// Context compaction
	let compactTokenThreshold = $state(80000);
	let compactDirty = $state(false);

	const TEMPLATE_VARIABLES = [
		{ name: 'CPTR_CONTEXT', desc: 'Runtime, machine, workspace, and tool context' },
		{ name: 'RUNTIME_ENV', desc: 'Runtime environment (host or container)' },
		{ name: 'HOSTNAME', desc: 'Machine hostname' },
		{ name: 'WORKSPACE_NAME', desc: 'Workspace folder name' },
		{ name: 'WORKSPACE_PATH', desc: 'Full workspace path' },
		{ name: 'FILE_TREE', desc: 'File listing (top-level + 1 depth)' },
		{ name: 'INSTRUCTIONS', desc: 'MEMORY.md / AGENTS.md / CLAUDE.md content' },
		{ name: 'OS', desc: 'Operating system (macOS, Linux, Windows)' },
		{ name: 'PLATFORM', desc: 'Detailed platform string' },
		{ name: 'ARCH', desc: 'Machine architecture' },
		{ name: 'SHELL', desc: 'Default shell path' },
		{ name: 'HOME', desc: 'Home directory' },
		{ name: 'CPTR_VERSION', desc: 'cptr version' },
		{ name: 'DATE', desc: 'Current date (ISO format)' },
		{ name: 'MODEL', desc: 'Model ID being used' }
	];

	const DEFAULT_PROMPT_PLACEHOLDER = `You are Computer (cptr), a helpful assistant running inside the user's computer interface. You have access to tools to read, search, and modify files in the workspace, run commands, and use configured tools. Use them to help the user directly. Approach hard requests with initiative and persistence: make the best possible attempt, adapt as needed, and keep going unless a real constraint prevents progress.

{{CPTR_CONTEXT}}

{{INSTRUCTIONS}}

{{SKILLS}}

Date: {{DATE}}
Workspace: {{WORKSPACE_NAME}}
OS: {{OS}}
Files:
{{FILE_TREE}}`;

	let hasDirty = $derived(globalDirty || compactDirty || models.some((m) => m.dirty) || modelsToDelete.length > 0);

	function parseRows(config: ModelConfigEntry | undefined): ParamRow[] {
		const rp = config?.params?.request_params;
		if (!rp || typeof rp !== 'object') return [];
		return Object.entries(rp).map(([key, value]) => ({
			key,
			value: typeof value === 'object' ? JSON.stringify(value) : String(value)
		}));
	}

	function rowsToRequestParams(rows: ParamRow[]): Record<string, unknown> {
		const result: Record<string, unknown> = {};
		for (const { key, value } of rows) {
			if (!key.trim()) continue;
			try {
				result[key.trim()] = JSON.parse(value);
			} catch {
				result[key.trim()] = value;
			}
		}
		return result;
	}

	function applyModelConfig(
		data: Awaited<ReturnType<typeof getModelConfig>>,
		preserveDirty = false
	) {
		const config = data.config || {};
		rawModels = data.models || [];
		const previousById = new Map(models.map((model) => [model.id, model]));

		if (!preserveDirty || !globalDirty) {
			globalRows = parseRows(config['*']);
			globalSystemPrompt = config['*']?.params?.system_prompt || '';
			globalExpanded = globalRows.length > 0 || !!globalSystemPrompt;
		}

		const loadedModels: ModelEntry[] = [];
		for (const [key, val] of Object.entries(config)) {
			if (key === '*') continue;
			const mc = val as any;
			const previous = previousById.get(key);

			if (preserveDirty && previous?.dirty) {
				loadedModels.push(previous);
			} else {
				loadedModels.push({
					id: key,
					originalId: key,
					name: mc.name || key,
					base_model: mc.base_model || '',
					is_active: mc.is_active !== false,
					rows: parseRows(mc),
					systemPrompt: mc.params?.system_prompt || '',
					dirty: false,
					isNew: false
				});
			}
		}

		// Keep any unsaved new models that were added
		if (preserveDirty) {
			for (const m of models) {
				if (m.isNew && !loadedModels.some((lm) => lm.id === m.id)) {
					loadedModels.push(m);
				}
			}
		}

		models = loadedModels;

		if (selectedModel && !models.some((model) => model === selectedModel)) {
			selectedModel = null;
		}
	}

	async function loadModelConfig() {
		try {
			applyModelConfig(await getModelConfig());
		} catch {
			toast.error($t('models.failedToLoad'));
		} finally {
			loading = false;
		}
	}

	onMount(async () => {
		await loadModelConfig();

		// Load admin config (default model, context compaction)
		try {
			const adminCfg = await getAdminConfig();
			compactTokenThreshold = Number(adminCfg['chat.compact_token_threshold']) || 80000;
			defaultModelId =
				typeof adminCfg['chat.default_model'] === 'string' ? adminCfg['chat.default_model'] : '';
		} catch {}
	});

	async function refreshModels() {
		refreshing = true;
		try {
			applyModelConfig(await refreshModelList(), true);
			await refreshChatState();
			toast.success($t('models.refreshed'));
		} catch {
			toast.error($t('models.refreshFailed'));
		} finally {
			refreshing = false;
		}
	}

	function toggleModel(e: Event, model: ModelEntry) {
		e.stopPropagation();
		model.is_active = !model.is_active;
		model.dirty = true;
		models = [...models];
	}

	function addCustomModel() {
		let count = 1;
		while (models.some((m) => m.id === `custom-model-${count}`)) {
			count++;
		}
		const tempId = `custom-model-${count}`;
		const newModel: ModelEntry = {
			id: tempId,
			name: `Custom Model ${count}`,
			base_model: rawModels[0]?.id || '',
			is_active: true,
			rows: [],
			systemPrompt: '',
			dirty: true,
			isNew: true
		};
		models = [...models, newModel];
		selectedModel = newModel;
	}

	function deleteModel(e: Event, model: ModelEntry) {
		e.stopPropagation();
		if (model.isNew) {
			models = models.filter((m) => m.id !== model.id);
			if (selectedModel === model) {
				selectedModel = null;
			}
		} else {
			if (confirm(`Are you sure you want to delete custom model "${model.name}"?`)) {
				modelsToDelete.push(model.id);
				models = models.filter((m) => m.id !== model.id);
				if (selectedModel === model) {
					selectedModel = null;
				}
			}
		}
	}

	function buildParams(rows: ParamRow[], systemPrompt: string): Record<string, unknown> {
		const params: Record<string, unknown> = {};
		const rp = rowsToRequestParams(rows);
		if (Object.keys(rp).length) params.request_params = rp;
		if (systemPrompt.trim()) params.system_prompt = systemPrompt.trim();
		return params;
	}

	async function saveAll() {
		saving = true;
		try {
			const promises: Promise<unknown>[] = [];

			// 1. Process deletions
			for (const id of modelsToDelete) {
				promises.push(deleteModelConfig(id));
			}

			// 2. Process global default config
			if (globalDirty) {
				promises.push(
					updateModelConfig('*', {
						params: buildParams(globalRows, globalSystemPrompt)
					})
				);
			}

			// 3. Process custom models
			for (const model of models) {
				const sanitizedId = model.id.trim().toLowerCase().replace(/[^a-z0-9_-]/g, '-');
				if (!sanitizedId) {
					toast.error("Model ID cannot be empty");
					saving = false;
					return;
				}

				if (model.dirty || model.isNew || (model.originalId && model.originalId !== model.id)) {
					const updatePayload = {
						is_active: model.is_active,
						name: model.name,
						base_model: model.base_model,
						params: buildParams(model.rows, model.systemPrompt)
					};

					if (model.originalId && model.originalId !== model.id) {
						promises.push(deleteModelConfig(model.originalId));
					}

					promises.push(updateModelConfig(sanitizedId, updatePayload));
				}
			}

			await Promise.all(promises);

			modelsToDelete = [];
			globalDirty = false;
			compactDirty = false;
			for (const m of models) {
				m.dirty = false;
				m.isNew = false;
				m.originalId = m.id;
			}

			// Save default model and compact threshold
			await updateConfig({
				'chat.compact_token_threshold': compactTokenThreshold,
				'chat.default_model': defaultModelId
			});

			await refreshChatState();
			toast.success($t('settings.saved'));
		} catch {
			toast.error($t('models.failedToSave'));
		} finally {
			saving = false;
		}
	}
</script>

{#snippet systemPromptField(value: string, onInput: (v: string) => void, placeholder: string)}
	<div class="mb-2">
		<span class="text-[10px] text-gray-400 dark:text-gray-600 uppercase tracking-wide"
			>{$t('models.systemPrompt')}</span
		>
		<textarea
			class="w-full mt-1 bg-gray-50 dark:bg-white/4 border border-gray-200 dark:border-white/8 rounded-lg px-2.5 py-2 text-[11px] font-mono text-gray-600 dark:text-gray-400 placeholder:text-gray-300 dark:placeholder:text-gray-700 outline-none resize-y leading-relaxed"
			rows="6"
			{placeholder}
			{value}
			oninput={(e) => onInput((e.target as HTMLTextAreaElement).value)}
			spellcheck="false"
		></textarea>
		<div class="flex items-center gap-2 mt-1">
			<button
				class="text-[10px] text-gray-400 dark:text-gray-600 hover:text-gray-600 dark:hover:text-gray-400 transition-colors duration-75"
				onclick={() => (showVariables = !showVariables)}
			>
				{$t('models.templateVariables')}
				{showVariables ? '▾' : '▸'}
			</button>
			{#if value.trim()}
				<button
					class="text-[10px] text-gray-400 dark:text-gray-600 hover:text-gray-600 dark:hover:text-gray-400 transition-colors duration-75"
					onclick={() => onInput('')}
				>
					{$t('models.resetToDefault')}
				</button>
			{/if}
		</div>
		{#if showVariables}
			<div
				class="mt-1 rounded-lg bg-gray-50 dark:bg-white/3 border border-gray-100 dark:border-white/5 px-2.5 py-2"
			>
				{#each TEMPLATE_VARIABLES as v}
					<div class="flex items-baseline gap-2 h-5">
						<code class="text-[10px] font-mono text-gray-500 dark:text-gray-500 shrink-0 select-all"
							>{`{{${v.name}}}`}</code
						>
						<span class="text-[10px] text-gray-400 dark:text-gray-600 truncate">{v.desc}</span>
					</div>
				{/each}
			</div>
		{/if}
	</div>
{/snippet}

{#snippet paramRows(
	rows: ParamRow[],
	onInput: () => void,
	onRemove: (i: number) => void,
	onAdd: () => void
)}
	<div class="mb-2">
		<span class="text-[10px] text-gray-400 dark:text-gray-600 uppercase tracking-wide"
			>request params</span
		>
		{#each rows as row, i}
			<div class="group/row flex items-center gap-1.5 h-6">
				<input
					type="text"
					placeholder="key"
					bind:value={row.key}
					oninput={onInput}
					autocomplete="off"
					spellcheck="false"
					class="w-24 shrink-0 bg-transparent text-[11px] font-mono text-gray-500 dark:text-gray-500 placeholder:text-gray-300 dark:placeholder:text-gray-700 outline-none"
				/>
				<input
					type="text"
					placeholder="value"
					bind:value={row.value}
					oninput={onInput}
					autocomplete="off"
					spellcheck="false"
					class="flex-1 min-w-0 bg-transparent text-[11px] font-mono text-gray-500 dark:text-gray-500 placeholder:text-gray-300 dark:placeholder:text-gray-700 outline-none"
				/>
				<button
					type="button"
					onclick={() => onRemove(i)}
					class="shrink-0 text-gray-300 dark:text-gray-700 opacity-0 group-hover/row:opacity-100 hover:text-gray-500 dark:hover:text-gray-400 transition-colors duration-75"
					aria-label="Remove"
				>
					<Icon name="xmark" size={8} />
				</button>
			</div>
		{/each}
		<button
			class="flex items-center gap-1 h-6 text-[11px] text-gray-400 dark:text-gray-600 hover:text-gray-600 dark:hover:text-gray-400 transition-colors duration-75"
			onclick={onAdd}
		>
			<Icon name="plus" size={10} />
			<span>Add</span>
		</button>
	</div>
{/snippet}

{#snippet modelForm(model: ModelEntry)}
	<div class="mt-2 mb-4 p-3 bg-gray-50/50 dark:bg-white/2 border border-gray-100 dark:border-white/5 rounded-xl space-y-3">
		<!-- Name and ID row -->
		<div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
			<div>
				<label class="text-[10px] text-gray-400 dark:text-gray-600 uppercase tracking-wide font-medium" for="model-name-{model.id}">Model Name</label>
				<input
					id="model-name-{model.id}"
					type="text"
					bind:value={model.name}
					oninput={() => model.dirty = true}
					placeholder="e.g. Gemma 4 | 12B"
					class="w-full h-8 px-2.5 mt-1 rounded-lg text-xs bg-white dark:bg-white/5 text-gray-800 dark:text-gray-200 border border-gray-200 dark:border-white/8 outline-none focus:border-blue-500"
				/>
			</div>
			<div>
				<label class="text-[10px] text-gray-400 dark:text-gray-600 uppercase tracking-wide font-medium" for="model-slug-{model.id}">Model ID / Slug</label>
				<input
					id="model-slug-{model.id}"
					type="text"
					bind:value={model.id}
					oninput={() => model.dirty = true}
					placeholder="e.g. gemma-4-12b"
					class="w-full h-8 px-2.5 mt-1 rounded-lg text-xs bg-white dark:bg-white/5 text-gray-800 dark:text-gray-200 border border-gray-200 dark:border-white/8 outline-none focus:border-blue-500"
				/>
			</div>
		</div>

		<!-- Base Model selector -->
		<div>
			<label class="text-[10px] text-gray-400 dark:text-gray-600 uppercase tracking-wide font-medium" for="base-model-{model.id}">Base Model (Inherits From)</label>
			<div class="relative mt-1">
				<select
					id="base-model-{model.id}"
					bind:value={model.base_model}
					onchange={() => model.dirty = true}
					class="w-full h-8 pl-2.5 pr-8 rounded-lg text-xs bg-white dark:bg-white/5 text-gray-800 dark:text-gray-200 border border-gray-200 dark:border-white/8 outline-none focus:border-blue-500 appearance-none cursor-pointer"
				>
					<option value="" disabled>Select a base model</option>
					{#each rawModels as rm}
						<option value={rm.id}>{rm.name || rm.id} ({rm.provider})</option>
					{/each}
				</select>
				<div class="absolute inset-y-0 right-0 flex items-center pr-2.5 pointer-events-none text-gray-400">
					<Icon name="chevron-down" size={10} />
				</div>
			</div>
		</div>

		<!-- System prompt override -->
		{@render systemPromptField(
			model.systemPrompt,
			(v) => {
				model.systemPrompt = v;
				model.dirty = true;
			},
			$t('models.systemPromptInherited')
		)}

		<!-- Request parameters -->
		{@render paramRows(
			model.rows,
			() => (model.dirty = true),
			(i) => {
				model.rows = model.rows.filter((_, idx) => idx !== i);
				model.dirty = true;
			},
			() => {
				model.rows = [...model.rows, { key: '', value: '' }];
				model.dirty = true;
			}
		)}

		<!-- Action buttons -->
		<div class="flex justify-end pt-1">
			<button
				class="flex items-center gap-1 text-[11px] text-red-500 hover:text-red-600 dark:hover:text-red-400 transition-colors duration-75 font-medium"
				onclick={(e) => deleteModel(e, model)}
			>
				<Icon name="trash" size={10} />
				<span>Delete Model</span>
			</button>
		</div>
	</div>
{/snippet}

<div class="flex flex-col h-full">
	{#if loading}
		<div class="flex justify-center py-8"><Spinner size={16} /></div>
	{:else}
		<div class="flex-1 min-h-0 overflow-y-auto">
			<div class="flex items-center justify-between mb-4">
				<h2 class="text-sm font-medium text-gray-900 dark:text-white">
					{$t('admin.models')}
				</h2>
				<button
					class="flex items-center justify-center w-6 h-6 rounded-lg text-gray-400 hover:text-gray-700 disabled:opacity-50 disabled:hover:text-gray-400 dark:text-gray-600 dark:hover:text-gray-300 dark:disabled:hover:text-gray-600 transition-colors duration-75"
					onclick={refreshModels}
					disabled={refreshing || saving}
					aria-label={$t('models.refresh')}
					use:tooltip={$t('models.refresh')}
				>
					<Icon name="refresh" size={13} class={refreshing ? 'animate-spin' : ''} />
				</button>
			</div>

			<!-- Default model -->
			<h3 class="text-xs text-gray-400 dark:text-gray-600 mb-2">
				{$t('models.defaultModel')}
			</h3>
			<div class="mb-1">
				<ModelSelector bind:selectedModel={defaultModelId} preferAbove={false} align="start" />
			</div>
			<p class="text-[11px] text-gray-400 dark:text-gray-600 mb-5">
				{$t('models.defaultModelHint')}
			</p>

			<!-- Context compaction -->
			<h3 class="text-xs text-gray-400 dark:text-gray-600 mb-2">{$t('admin.contextCompaction')}</h3>

			<div class="flex flex-col gap-2.5 mb-5">
				<div>
					<label class="text-xs text-gray-600 dark:text-gray-400" for="compact-threshold"
						>{$t('admin.compactTokenThreshold')}</label
					>
					<div class="flex items-center gap-1.5 mt-1">
						<input
							id="compact-threshold"
							type="number"
							bind:value={compactTokenThreshold}
							oninput={() => (compactDirty = true)}
							min="10000"
							max="1000000"
							step="10000"
							class="w-24 h-7 px-2 rounded-lg text-xs bg-gray-100 dark:bg-white/6 text-gray-700 dark:text-gray-300 border border-gray-200 dark:border-white/8 outline-none focus:border-blue-400 dark:focus:border-blue-500 transition-colors"
						/>
						<span class="text-[11px] text-gray-400 dark:text-gray-600"
							>{$t('admin.compactTokenThresholdUnit')}</span
						>
					</div>
					<p class="text-[11px] text-gray-400 dark:text-gray-600 mt-0.5">
						{$t('admin.compactTokenThresholdHint')}
					</p>
				</div>
			</div>

			<!-- Global defaults -->
			<button
				class="group flex items-center gap-2 w-full h-7 text-left"
				onclick={() => (globalExpanded = !globalExpanded)}
			>
				<span class="flex-1 text-[13px] text-gray-500 dark:text-gray-400"
					>{$t('models.defaults')}</span
				>
				{#if globalRows.filter((r) => r.key.trim()).length > 0 || globalSystemPrompt.trim()}
					<span class="text-[10px] text-gray-400 dark:text-gray-600">
						{#if globalSystemPrompt.trim()}prompt{/if}
						{#if globalRows.filter((r) => r.key.trim()).length > 0}
							{globalRows.filter((r) => r.key.trim()).length} params
						{/if}
					</span>
				{/if}
				<Icon
					name={globalExpanded ? 'chevron-down' : 'chevron-right'}
					size={10}
					class="shrink-0 text-gray-300 dark:text-gray-700"
				/>
			</button>

			{#if globalExpanded}
				{@render systemPromptField(
					globalSystemPrompt,
					(v) => {
						globalSystemPrompt = v;
						globalDirty = true;
					},
					DEFAULT_PROMPT_PLACEHOLDER
				)}
				{@render paramRows(
					globalRows,
					() => (globalDirty = true),
					(i) => {
						globalRows = globalRows.filter((_, idx) => idx !== i);
						globalDirty = true;
					},
					() => {
						globalRows = [...globalRows, { key: '', value: '' }];
						globalDirty = true;
					}
				)}
			{/if}

			<!-- Custom models header -->
			<div class="flex items-center justify-between mt-6 mb-2 border-t border-gray-100 dark:border-white/5 pt-4">
				<h3 class="text-xs font-semibold text-gray-400 dark:text-gray-600 uppercase tracking-wider">
					Custom Models
				</h3>
				<button
					class="flex items-center gap-1.5 h-6 px-2 text-[11px] font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg shadow-sm transition-colors duration-100"
					onclick={addCustomModel}
				>
					<Icon name="plus" size={10} />
					<span>Add Custom Model</span>
				</button>
			</div>

			<!-- Per-model list -->
			{#each models as model}
				<button
					class="group flex items-center gap-2 w-full h-8 text-left border-b border-gray-50/50 dark:border-white/2 hover:bg-gray-50/30 dark:hover:bg-white/1 px-1 rounded-lg"
					onclick={() => (selectedModel = selectedModel === model ? null : model)}
				>
					<span
						class="flex-1 text-[13px] font-medium truncate {model.is_active
							? 'text-gray-700 dark:text-gray-300'
							: 'text-gray-400 dark:text-gray-600'}"
					>
						{model.name} <span class="text-[10px] text-gray-400 font-normal ml-2">({model.id})</span>
					</span>
					<!-- svelte-ignore a11y_no_static_element_interactions -->
					<span
						class="relative w-6 h-3.5 rounded-full shrink-0 cursor-pointer transition-colors duration-150
							{model.is_active ? 'bg-gray-900 dark:bg-white' : 'bg-gray-200 dark:bg-gray-700'}"
						role="switch"
						tabindex="-1"
						aria-checked={model.is_active}
						onclick={(e) => toggleModel(e, model)}
						onkeydown={(e) => {
							if (e.key === 'Enter' || e.key === ' ') {
								e.preventDefault();
								toggleModel(e, model);
							}
						}}
					>
						<span
							class="absolute top-0.5 w-2.5 h-2.5 rounded-full transition-all duration-150
							{model.is_active ? 'left-3 bg-white dark:bg-gray-900' : 'left-0.5 bg-white dark:bg-gray-500'}"
						></span>
					</span>
				</button>

				{#if selectedModel === model}
					{@render modelForm(model)}
				{/if}
			{/each}

			{#if models.length === 0}
				<p class="text-[13px] text-gray-400 dark:text-gray-600 py-4">
					No custom models defined. Click '+ Add Custom Model' to create one.
				</p>
			{/if}
		</div>

		<div class="shrink-0 pt-3 flex justify-end">
			<button
				class="text-[13px] text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-colors duration-100"
				onclick={saveAll}
			>
				{#if saving}{$t('settings.saving')}{:else}{$t('settings.save')}{/if}
			</button>
		</div>
	{/if}
</div>
