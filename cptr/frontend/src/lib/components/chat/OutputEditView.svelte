<script lang="ts">
	import { onDestroy, tick } from 'svelte';
	import { basicSetup, EditorView } from 'codemirror';
	import { keymap } from '@codemirror/view';
	import { Compartment, EditorState } from '@codemirror/state';
	import { json } from '@codemirror/lang-json';
	import { indentWithTab } from '@codemirror/commands';
	import { indentUnit } from '@codemirror/language';
	import { oneDark } from '@codemirror/theme-one-dark';

	interface Props {
		output: any[];
		onChange: (output: any[]) => void;
	}
	let { output = $bindable(), onChange }: Props = $props();

	let viewMode = $state<'visual' | 'json'>('visual');
	let jsonError = $state('');

	// ── CodeMirror ──────────────────────────────────────────────

	let cmContainer: HTMLDivElement;
	let cmEditor: EditorView | null = null;
	let editorTheme = new Compartment();

	function initCodeMirror() {
		if (cmEditor || !cmContainer) return;
		const isDark = document.documentElement.classList.contains('dark');
		cmEditor = new EditorView({
			state: EditorState.create({
				doc: JSON.stringify(output, null, 2),
				extensions: [
					basicSetup,
					keymap.of([indentWithTab]),
					indentUnit.of('  '),
					json(),
					editorTheme.of(isDark ? oneDark : []),
					EditorView.theme({
						'&': { fontSize: '13px' },
						'.cm-content': { fontFamily: 'ui-monospace, monospace' },
						'.cm-scroller': { maxHeight: '320px', overflow: 'auto' },
						'&.cm-focused': { outline: 'none' }
					}),
					EditorView.updateListener.of((e) => {
						if (e.docChanged) {
							try {
								const parsed = JSON.parse(e.state.doc.toString());
								if (Array.isArray(parsed)) {
									jsonError = '';
									output = parsed;
									onChange(output);
								} else {
									jsonError = 'Must be a JSON array';
								}
							} catch {
								jsonError = 'Invalid JSON';
							}
						}
					})
				]
			}),
			parent: cmContainer
		});
	}

	function destroyCodeMirror() {
		if (cmEditor) {
			cmEditor.destroy();
			cmEditor = null;
		}
	}

	async function switchToJson() {
		viewMode = 'json';
		await tick();
		initCodeMirror();
	}

	function switchToVisual() {
		if (jsonError) return;
		destroyCodeMirror();
		viewMode = 'visual';
	}

	onDestroy(() => destroyCodeMirror());

	// ── Display items ───────────────────────────────────────────

	interface DisplayItem {
		type: 'message' | 'function_call' | 'function_call_output';
		index: number;
		item: any;
		outputItem?: any;
		outputIndex?: number;
	}

	function buildDisplayItems(items: any[]): DisplayItem[] {
		const result: DisplayItem[] = [];
		const outputByCallId: Record<string, { item: any; index: number }> = {};

		for (let i = 0; i < items.length; i++) {
			if (items[i]?.type === 'function_call_output') {
				outputByCallId[items[i].call_id] = { item: items[i], index: i };
			}
		}

		for (let i = 0; i < items.length; i++) {
			const item = items[i];
			const t = item?.type ?? '';
			if (t === 'message') {
				result.push({ type: 'message', index: i, item });
			} else if (t === 'function_call') {
				const paired = outputByCallId[item.call_id];
				result.push({
					type: 'function_call',
					index: i,
					item,
					outputItem: paired?.item,
					outputIndex: paired?.index
				});
			}
			// function_call_output is grouped with function_call
		}
		return result;
	}

	const displayItems = $derived(buildDisplayItems(output));

	// ── Helpers ──────────────────────────────────────────────────

	function getMessageText(item: any): string {
		return (item.content ?? [])
			.filter((p: any) => p.type === 'output_text' || 'text' in p)
			.map((p: any) => p.text ?? '')
			.join('\n');
	}

	function updateMessageText(idx: number, text: string) {
		const next = [...output];
		const item = { ...next[idx] };
		const parts = (item.content ?? []).filter((p: any) => p.type === 'output_text' || 'text' in p);
		item.content = [{ ...(parts[0] ?? { type: 'output_text' }), text }];
		next[idx] = item;
		output = next;
		onChange(output);
	}

	function deleteIndices(indices: number[]) {
		const rm = new Set(indices);
		output = output.filter((_: any, i: number) => !rm.has(i));
		onChange(output);
	}

	function formatArgs(args: any): string {
		if (!args) return '';
		try {
			return typeof args === 'string' ? args : JSON.stringify(args, null, 2);
		} catch {
			return String(args);
		}
	}

	function resizeEl(el: HTMLTextAreaElement) {
		el.style.height = '';
		el.style.height = `${el.scrollHeight}px`;
	}

	function autoResize(e: Event) {
		resizeEl(e.target as HTMLTextAreaElement);
	}

	function fitContent(el: HTMLTextAreaElement) {
		resizeEl(el);
	}

	function getItemLabel(di: DisplayItem): string {
		switch (di.type) {
			case 'message':
				return 'Text';
			case 'function_call':
				return di.item.name ?? 'Tool';
			default:
				return 'Item';
		}
	}
</script>

<div class="w-full">
	<!-- View mode tabs -->
	<div class="flex justify-end gap-3 text-[11px] font-medium {viewMode === 'json' ? 'mb-1.5' : ''}">
		<button
			class="pb-0.5 transition-colors duration-100
				{viewMode === 'visual'
					? 'text-gray-700 dark:text-gray-200 border-b border-gray-400 dark:border-gray-400'
					: 'text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300'}"
			onclick={() => { if (viewMode === 'json') switchToVisual(); }}
		>Rich</button>
		<button
			class="pb-0.5 transition-colors duration-100
				{viewMode === 'json'
					? 'text-gray-700 dark:text-gray-200 border-b border-gray-400 dark:border-gray-400'
					: 'text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300'}"
			onclick={() => { if (viewMode === 'visual') switchToJson(); }}
		>JSON</button>
	</div>

	{#if viewMode === 'json'}
		<div
			bind:this={cmContainer}
			class="w-full rounded-xl overflow-hidden border border-gray-100 dark:border-white/8"
		></div>
		{#if jsonError}
			<div class="text-xs text-red-500 mt-1.5 px-1">{jsonError}</div>
		{/if}
	{:else}
		<!-- Visual editor -->
		<div class="space-y-2 p-2 pt-3">
			{#each displayItems as di}
				<div class="flex gap-2 group">
					<!-- Type label -->
					<div class="flex items-start pt-1.5">
						<div class="text-[10px] font-semibold uppercase tracking-wide min-w-[3.5rem] text-gray-400 dark:text-gray-500">
							{getItemLabel(di)}
						</div>
					</div>

					<!-- Content -->
					<div class="flex-1 min-w-0">
						{#if di.type === 'message'}
							<textarea
								use:fitContent
								class="w-full bg-transparent outline-none resize-none overflow-hidden text-[13px] p-1.5 rounded-lg leading-relaxed"
								value={getMessageText(di.item)}
								oninput={(e) => {
									updateMessageText(di.index, (e.target as HTMLTextAreaElement).value);
									autoResize(e);
								}}
								placeholder="Message text..."
								rows="1"
							></textarea>
						{:else if di.type === 'function_call'}
							<div class="text-[12px] p-1.5 text-gray-500 dark:text-gray-400">
								{#if di.item.arguments}
									<pre class="text-[11px] font-mono whitespace-pre-wrap overflow-x-auto pb-0.5">{formatArgs(di.item.arguments)}</pre>
								{/if}
								{#if di.outputItem}
									<pre class="text-[11px] font-mono whitespace-pre-wrap overflow-x-auto mt-1 max-h-32 overflow-y-auto text-gray-400 dark:text-gray-600">{di.outputItem.output}</pre>
								{/if}
							</div>
						{/if}
					</div>

					<!-- Delete -->
					<div class="pt-1.5">
						<button
							class="invisible group-hover:visible p-1 text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 transition rounded-lg"
							onclick={() => {
								const indices = [di.index];
								if (di.outputIndex !== undefined) indices.push(di.outputIndex);
								deleteIndices(indices);
							}}
						>
							<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" class="w-3.5 h-3.5">
								<path stroke-linecap="round" stroke-linejoin="round" d="M15 12H9m12 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
							</svg>
						</button>
					</div>
				</div>
			{/each}

			{#if displayItems.length === 0}
				<div class="text-[12px] text-gray-400 dark:text-gray-500 italic px-1">
					No output items
				</div>
			{/if}
		</div>
	{/if}
</div>
