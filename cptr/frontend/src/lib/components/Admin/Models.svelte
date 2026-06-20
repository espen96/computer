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
	import ToggleSwitch from '../common/ToggleSwitch.svelte';

	type ParamRow = { key: string; value: string };
	type ModelEntry = {
		id: string;
		originalId?: string;
		name: string;
		provider: string;
		base_model: string;
		is_active: boolean;
		rows: ParamRow[];
		systemPrompt: string;
		visionToolBehavior: string;
		dirty: boolean;
		isNew?: boolean;
	};

	let loading = $state(true);
	let saving = $state(false);
	let refreshing = $state(false);
	let customModels = $state<ModelEntry[]>([]);
	let baseModels = $state<ModelEntry[]>([]);
	let rawModels = $state<{ id: string; name: string; provider: string; connection_id: string }[]>(
		[]
	);
	let selectedModel = $state<ModelEntry | null>(null);
	let modelsToDelete = $state<string[]>([]);

	let customModelsExpanded = $state(true);
	let baseModelsExpanded = $state(false);

	let globalRows = $state<ParamRow[]>([]);
	let globalSystemPrompt = $state('');
	let globalVisionToolBehavior = $state('');
	let globalDirty = $state(false);
	let globalExpanded = $state(false);
	let showVariables = $state(false);

	// Default model
	let defaultModelId = $state('');

	// Context compaction
	let compactTokenThreshold = $state(80000);
	let compactDirty = $state(false);

	// Chat titles
	let autoTitle = $state(true);
	let titleModelType = $state('same'); // 'same' | 'specific'
	let titleModelId = $state('');
	let titlesDirty = $state(false);

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

	let hasDirty = $derived(
		globalDirty ||
			compactDirty ||
			titlesDirty ||
			customModels.some((m) => m.dirty) ||
			baseModels.some((m) => m.dirty) ||
			modelsToDelete.length > 0
	);

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
		const globalCfg = config['*'];
		if (!preserveDirty) {
			globalRows = parseRows(globalCfg);
			globalSystemPrompt = globalCfg?.params?.system_prompt || '';
			globalVisionToolBehavior = globalCfg?.params?.vision_tool_behavior || '';
			globalDirty = false;
		}

		rawModels = data.models || [];

		// 1. Process Base Models (raw models from connections)
		const previousBaseById = new Map(baseModels.map((model) => [model.id, model]));
		baseModels = rawModels.map((rm) => {
			const previous = previousBaseById.get(rm.id);
			if (preserveDirty && previous?.dirty) {
				return previous;
			}
			const mc = config[rm.id];
			return {
				id: rm.id,
				name: rm.name || rm.id,
				provider: rm.provider,
				base_model: '',
				is_active: mc?.is_active !== false,
				rows: parseRows(mc),
				systemPrompt: mc?.params?.system_prompt || '',
				visionToolBehavior: mc?.params?.vision_tool_behavior || '',
				dirty: false,
				isNew: false
			};
		});

		// 2. Process Custom Models (keys in config that are not raw model IDs and not '*')
		const previousCustomById = new Map(customModels.map((model) => [model.id, model]));
		const loadedCustomModels: ModelEntry[] = [];
		const rawModelIds = new Set(rawModels.map((rm) => rm.id));

		for (const [key, val] of Object.entries(config)) {
			if (key === '*' || rawModelIds.has(key)) continue;
			const mc = val as any;
			const isCustom = mc && typeof mc === 'object' && ('base_model' in mc || 'name' in mc);
			if (!isCustom) continue;

			const previous = previousCustomById.get(key);

			if (preserveDirty && previous?.dirty) {
				loadedCustomModels.push(previous);
			} else {
				loadedCustomModels.push({
					id: key,
					originalId: key,
					name: mc.name || key,
					provider: '',
					base_model: mc.base_model || '',
					is_active: mc.is_active !== false,
					rows: parseRows(mc),
					systemPrompt: mc.params?.system_prompt || '',
					visionToolBehavior: mc.params?.vision_tool_behavior || '',
					dirty: false,
					isNew: false
				});
			}
		}

		// Keep any unsaved new custom models
		if (preserveDirty) {
			for (const m of customModels) {
				if (m.isNew && !loadedCustomModels.some((lm) => lm.id === m.id)) {
					loadedCustomModels.push(m);
				}
			}
		}

		customModels = loadedCustomModels;

		// Clean up selectedModel if it was deleted
		if (selectedModel) {
			const exists =
				customModels.some((m) => m === selectedModel) ||
				baseModels.some((m) => m === selectedModel);
			if (!exists) {
				selectedModel = null;
			}
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

			const autoTitleVal = adminCfg['chat.auto_title'];
			autoTitle = autoTitleVal !== false; // defaults to true

			const titleModelVal = adminCfg['chat.title_model'];
			if (typeof titleModelVal === 'string' && titleModelVal !== 'same' && titleModelVal !== '') {
				titleModelType = 'specific';
				titleModelId = titleModelVal;
			} else {
				titleModelType = 'same';
				titleModelId = '';
			}
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
		customModels = [...customModels];
		baseModels = [...baseModels];
	}

	function addCustomModel() {
		let count = 1;
		while (customModels.some((m) => m.id === `custom-model-${count}`)) {
			count++;
		}
		const tempId = `custom-model-${count}`;
		const newModel: ModelEntry = {
			id: tempId,
			name: `Custom Model ${count}`,
			provider: '',
			base_model: rawModels[0]?.id || '',
			is_active: true,
			rows: [],
			systemPrompt: '',
			visionToolBehavior: '',
			dirty: true,
			isNew: true
		};
		customModels = [...customModels, newModel];
		selectedModel = newModel;
		customModelsExpanded = true;
	}

	function deleteModel(e: Event, model: ModelEntry) {
		e.stopPropagation();
		if (model.isNew) {
			customModels = customModels.filter((m) => m.id !== model.id);
			if (selectedModel === model) {
				selectedModel = null;
			}
		} else {
			if (confirm(`Are you sure you want to delete custom model "${model.name}"?`)) {
				modelsToDelete.push(model.id);
				customModels = customModels.filter((m) => m.id !== model.id);
				if (selectedModel === model) {
					selectedModel = null;
				}
			}
		}
	}

	function buildParams(rows: ParamRow[], systemPrompt: string, visionToolBehavior: string): Record<string, unknown> {
		const params: Record<string, unknown> = {};
		const rp = rowsToRequestParams(rows);
		if (Object.keys(rp).length) params.request_params = rp;
		if (systemPrompt.trim()) params.system_prompt = systemPrompt.trim();
		if (visionToolBehavior) params.vision_tool_behavior = visionToolBehavior;
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
						params: buildParams(globalRows, globalSystemPrompt, globalVisionToolBehavior)
					})
				);
			}

			// 3. Process custom models
			for (const model of customModels) {
				const sanitizedId = model.id
					.trim()
					.toLowerCase()
					.replace(/[^a-z0-9_-]/g, '-');
				if (!sanitizedId) {
					toast.error('Model ID cannot be empty');
					saving = false;
					return;
				}

				if (model.dirty || model.isNew || (model.originalId && model.originalId !== model.id)) {
					const updatePayload = {
						is_active: model.is_active,
						name: model.name,
						base_model: model.base_model,
						params: buildParams(model.rows, model.systemPrompt, model.visionToolBehavior)
					};

					if (model.originalId && model.originalId !== model.id) {
						promises.push(deleteModelConfig(model.originalId));
					}

					promises.push(updateModelConfig(sanitizedId, updatePayload));
				}
			}

			// 4. Process base models
			for (const model of baseModels) {
				if (model.dirty) {
					const updatePayload = {
						is_active: model.is_active,
						params: buildParams(model.rows, model.systemPrompt, model.visionToolBehavior)
					};
					promises.push(updateModelConfig(model.id, updatePayload));
				}
			}

			await Promise.all(promises);

			modelsToDelete = [];
			globalDirty = false;
			compactDirty = false;
			for (const m of customModels) {
				m.dirty = false;
				m.isNew = false;
				m.originalId = m.id;
			}
			for (const m of baseModels) {
				m.dirty = false;
			}

			// Save default model and compact threshold
			await updateConfig({
				'chat.compact_token_threshold': compactTokenThreshold,
				'chat.default_model': defaultModelId,
				'chat.auto_title': autoTitle,
				'chat.title_model': titleModelType === 'same' ? 'same' : titleModelId
			});

			titlesDirty = false;

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

{#snippet visionBehaviorField(value: string, onInput: (v: string) => void)}
	<div class="mb-2">
		<span class="text-[10px] text-gray-400 dark:text-gray-600 uppercase tracking-wide font-medium"
			>{$t('models.visionToolBehavior') ?? 'Tool Image Behavior'}</span
		>
		<div class="relative mt-1">
			<select
				value={value}
				onchange={(e) => onInput((e.target as HTMLSelectElement).value)}
				class="w-full h-8 pl-2.5 pr-8 rounded-lg text-[11px] font-mono bg-white dark:bg-white/5 text-gray-800 dark:text-gray-200 border border-gray-200 dark:border-white/8 outline-none focus:border-blue-500 appearance-none cursor-pointer"
			>
				<option value="">Default (Auto)</option>
				<option value="tool">Native Tool Block (Anthropic)</option>
				<option value="user">User Message (OpenAI)</option>
				<option value="assistant">Assistant Message</option>
				<option value="drop">Drop Images</option>
			</select>
			<div class="absolute inset-y-0 right-0 flex items-center pr-2.5 pointer-events-none text-gray-400">
				<Icon name="chevron-down" size={10} />
			</div>
		</div>
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
	<div
		class="mt-2 mb-4 p-3 bg-gray-50/50 dark:bg-white/2 border border-gray-100 dark:border-white/5 rounded-xl space-y-3"
	>
		<!-- Name and ID row -->
		<div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
			<div>
				<label
					class="text-[10px] text-gray-400 dark:text-gray-600 uppercase tracking-wide font-medium"
					for="model-name-{model.id}">Model Name</label
				>
				<input
					id="model-name-{model.id}"
					type="text"
					bind:value={model.name}
					oninput={() => (model.dirty = true)}
					placeholder="e.g. Gemma 4 | 12B"
					class="w-full h-8 px-2.5 mt-1 rounded-lg text-xs bg-white dark:bg-white/5 text-gray-800 dark:text-gray-200 border border-gray-200 dark:border-white/8 outline-none focus:border-blue-500"
				/>
			</div>
			<div>
				<label
					class="text-[10px] text-gray-400 dark:text-gray-600 uppercase tracking-wide font-medium"
					for="model-slug-{model.id}">Model ID / Slug</label
				>
				<input
					id="model-slug-{model.id}"
					type="text"
					bind:value={model.id}
					oninput={() => (model.dirty = true)}
					placeholder="e.g. gemma-4-12b"
					class="w-full h-8 px-2.5 mt-1 rounded-lg text-xs bg-white dark:bg-white/5 text-gray-800 dark:text-gray-200 border border-gray-200 dark:border-white/8 outline-none focus:border-blue-500"
				/>
			</div>
		</div>

		<!-- Base Model selector -->
		<div>
			<label
				class="text-[10px] text-gray-400 dark:text-gray-600 uppercase tracking-wide font-medium"
				for="base-model-{model.id}">Base Model (Inherits From)</label
			>
			<div class="relative mt-1">
				<select
					id="base-model-{model.id}"
					bind:value={model.base_model}
					onchange={() => (model.dirty = true)}
					class="w-full h-8 pl-2.5 pr-8 rounded-lg text-xs bg-white dark:bg-white/5 text-gray-800 dark:text-gray-200 border border-gray-200 dark:border-white/8 outline-none focus:border-blue-500 appearance-none cursor-pointer"
				>
					<option value="" disabled>Select a base model</option>
					{#each rawModels as rm}
						<option value={rm.id}>{rm.name || rm.id} ({rm.provider})</option>
					{/each}
				</select>
				<div
					class="absolute inset-y-0 right-0 flex items-center pr-2.5 pointer-events-none text-gray-400"
				>
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

		<!-- Vision tool behavior override -->
		{@render visionBehaviorField(model.visionToolBehavior, (v) => {
			model.visionToolBehavior = v;
			model.dirty = true;
		})}

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

{#snippet baseModelForm(model: ModelEntry)}
	<div
		class="mt-2 mb-4 p-3 bg-gray-50/50 dark:bg-white/2 border border-gray-100 dark:border-white/5 rounded-xl space-y-3"
	>
		<!-- System prompt override -->
		{@render systemPromptField(
			model.systemPrompt,
			(v) => {
				model.systemPrompt = v;
				model.dirty = true;
			},
			$t('models.systemPromptInherited')
		)}

		<!-- Vision tool behavior override -->
		{@render visionBehaviorField(model.visionToolBehavior, (v) => {
			model.visionToolBehavior = v;
			model.dirty = true;
		})}

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

			<!-- Chat titles -->
			<h3 class="text-xs text-gray-400 dark:text-gray-600 mb-2">{$t('admin.chatTitles')}</h3>

			<div class="flex flex-col gap-2.5 mb-5">
				<div>
					<label class="flex items-center justify-between cursor-pointer">
						<span class="text-xs text-gray-600 dark:text-gray-400"
							>{$t('admin.autoGenerateTitles')}</span
						>
						<ToggleSwitch
							value={autoTitle}
							onchange={(v) => {
								autoTitle = v;
								titlesDirty = true;
							}}
						/>
					</label>
					<p class="text-[11px] text-gray-400 dark:text-gray-600 mt-0.5">
						{$t('admin.autoGenerateTitlesHint')}
					</p>
				</div>

				{#if autoTitle}
					<div class="mt-1 pl-4 border-l-2 border-gray-100 dark:border-white/5 space-y-3">
						<div>
							<span class="text-xs text-gray-600 dark:text-gray-400 block mb-1.5"
								>{$t('admin.titleModelType')}</span
							>
							<div class="flex gap-2">
								{#each [{ value: 'same', label: $t('admin.titleModelSame') }, { value: 'specific', label: $t('admin.titleModelSpecific') }] as opt}
									<button
										class="flex items-center gap-1.5 h-7 px-2.5 rounded-lg text-xs transition-colors duration-100
										{titleModelType === opt.value
											? 'bg-gray-200/50 dark:bg-white/8 text-gray-900 dark:text-white font-medium'
											: 'text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'}"
										onclick={() => {
											titleModelType = opt.value;
											titlesDirty = true;
											if (titleModelType === 'specific' && !titleModelId) {
												titleModelId = defaultModelId || (rawModels[0]?.id ?? '');
											}
										}}
									>
										{opt.label}
									</button>
								{/each}
							</div>
						</div>

						{#if titleModelType === 'specific'}
							<div class="mt-2">
								<label
									class="text-xs text-gray-600 dark:text-gray-400 block mb-1"
									for="title-model-selector">{$t('admin.titleModel')}</label
								>
								<ModelSelector
									bind:selectedModel={titleModelId}
									preferAbove={false}
									align="start"
								/>
							</div>
						{/if}
					</div>
				{/if}
			</div>

			<!-- Global defaults -->
			<button
				class="group flex items-center gap-2 w-full h-7 text-left"
				onclick={() => (globalExpanded = !globalExpanded)}
			>
				<span class="flex-1 text-[13px] text-gray-500 dark:text-gray-400"
					>{$t('models.defaults')}</span
				>
				{#if globalRows.filter((r) => r.key.trim()).length > 0 || globalSystemPrompt.trim() || globalVisionToolBehavior}
					<span class="text-[10px] text-gray-400 dark:text-gray-600">
						{#if globalSystemPrompt.trim()}prompt{/if}
						{#if globalVisionToolBehavior} vision{/if}
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
				{@render visionBehaviorField(globalVisionToolBehavior, (v) => {
					globalVisionToolBehavior = v;
					globalDirty = true;
				})}
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
			<div
				class="flex items-center justify-between mt-6 mb-2 border-t border-gray-100 dark:border-white/5 pt-4"
			>
				<button
					class="flex items-center gap-2 text-left"
					onclick={() => (customModelsExpanded = !customModelsExpanded)}
				>
					<h3
						class="text-xs font-semibold text-gray-400 dark:text-gray-600 uppercase tracking-wider"
					>
						Custom Models
					</h3>
					<Icon
						name={customModelsExpanded ? 'chevron-down' : 'chevron-right'}
						size={10}
						class="shrink-0 text-gray-300 dark:text-gray-700"
					/>
				</button>
				<button
					class="flex items-center gap-1.5 h-6 px-2 text-[11px] font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg shadow-sm transition-colors duration-100"
					onclick={addCustomModel}
				>
					<Icon name="plus" size={10} />
					<span>Add Custom Model</span>
				</button>
			</div>

			<!-- Custom models list -->
			{#if customModelsExpanded}
				{#each customModels as model}
					<button
						class="group flex items-center gap-2 w-full h-8 text-left border-b border-gray-50/50 dark:border-white/2 hover:bg-gray-50/30 dark:hover:bg-white/1 px-1 rounded-lg"
						onclick={() => (selectedModel = selectedModel === model ? null : model)}
					>
						<span
							class="flex-1 text-[13px] font-medium truncate {model.is_active
								? 'text-gray-700 dark:text-gray-300'
								: 'text-gray-400 dark:text-gray-600'}"
						>
							{model.name}
							<span class="text-[10px] text-gray-400 font-normal ml-2">({model.id})</span>
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

				{#if customModels.length === 0}
					<p class="text-[13px] text-gray-400 dark:text-gray-600 py-4">
						No custom models defined. Click '+ Add Custom Model' to create one.
					</p>
				{/if}
			{/if}

			<!-- Base models header -->
			<div class="flex items-center mt-6 mb-2 border-t border-gray-100 dark:border-white/5 pt-4">
				<button
					class="flex items-center gap-2 text-left"
					onclick={() => (baseModelsExpanded = !baseModelsExpanded)}
				>
					<h3
						class="text-xs font-semibold text-gray-400 dark:text-gray-600 uppercase tracking-wider"
					>
						Base Models (Connections)
					</h3>
					<Icon
						name={baseModelsExpanded ? 'chevron-down' : 'chevron-right'}
						size={10}
						class="shrink-0 text-gray-300 dark:text-gray-700"
					/>
				</button>
			</div>

			<!-- Base models list -->
			{#if baseModelsExpanded}
				{#each baseModels as model}
					<button
						class="group flex items-center gap-2 w-full h-8 text-left border-b border-gray-50/50 dark:border-white/2 hover:bg-gray-50/30 dark:hover:bg-white/1 px-1 rounded-lg"
						onclick={() => (selectedModel = selectedModel === model ? null : model)}
					>
						<span
							class="flex-1 text-[13px] font-medium truncate {model.is_active
								? 'text-gray-700 dark:text-gray-300'
								: 'text-gray-400 dark:text-gray-600'}"
						>
							{model.name}
							<span class="text-[10px] text-gray-400 font-normal ml-2">({model.provider})</span>
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
						{@render baseModelForm(model)}
					{/if}
				{/each}

				{#if baseModels.length === 0}
					<p class="text-[13px] text-gray-400 dark:text-gray-600 py-4">
						No base models available. Add a connection first.
					</p>
				{/if}
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
