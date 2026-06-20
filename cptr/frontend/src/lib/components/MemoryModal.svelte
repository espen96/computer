<script lang="ts">
	import { onMount } from 'svelte';
	import { toast } from 'svelte-sonner';
	import Modal from '$lib/components/Modal.svelte';
	import Icon from '$lib/components/Icon.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import { currentWorkspace, memoryModalScope } from '$lib/stores';
	import { getMemory, updateMemory } from '$lib/apis/memory';

	let { onclose }: { onclose: () => void } = $props();

	let loading = $state(true);
	let entries = $state<string[]>([]);
	let usage = $state('');
	let searchQuery = $state('');

	const workspace = $derived($currentWorkspace?.path || '');

	onMount(() => {
		load();
	});

	async function load() {
		loading = true;
		try {
			const state = await getMemory($memoryModalScope === 'workspace' ? workspace : '');
			if ($memoryModalScope === 'workspace') {
				entries = state.workspace.entries;
				usage = state.workspace.usage;
			} else {
				entries = state.user.entries;
				usage = state.user.usage;
			}
		} catch {
			toast.error('Failed to load memory');
		} finally {
			loading = false;
		}
	}

	async function removeEntry(entry: string) {
		try {
			await updateMemory(
				$memoryModalScope,
				$memoryModalScope === 'workspace' ? workspace : '',
				[{ action: 'remove', old_text: entry.slice(0, 120) }]
			);
			await load();
		} catch {
			toast.error('Failed to update memory');
		}
	}

	const filteredEntries = $derived(
		entries.filter((e) => e.toLowerCase().includes(searchQuery.toLowerCase()))
	);
</script>

<Modal
	{onclose}
	class="w-full max-w-2xl mx-4 md:mx-0 flex flex-col h-[100vh] md:h-[560px]"
>
	<div class="flex items-center justify-between p-4 md:px-5 border-b border-gray-200 dark:border-white/6 shrink-0">
		<h2 class="text-sm font-medium text-gray-900 dark:text-white">
			{$memoryModalScope === 'user' ? 'Personal Memories' : 'Workspace Memories'}
		</h2>
		<button
			class="p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 rounded-md transition-colors cursor-pointer"
			onclick={onclose}
		>
			<Icon name="x" size={16} />
		</button>
	</div>

	<div class="p-4 md:px-5 shrink-0">
		<div class="relative">
			<Icon
				name="search"
				size={14}
				class="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400"
			/>
			<input
				type="text"
				placeholder="Search memories..."
				bind:value={searchQuery}
				class="w-full h-8 pl-9 pr-3 rounded-lg text-xs bg-gray-100 dark:bg-white/6 text-gray-700 dark:text-gray-300 border border-transparent focus:border-blue-400 dark:focus:border-blue-500 outline-none transition-colors"
			/>
		</div>
	</div>

	<div class="flex-1 overflow-y-auto p-4 md:px-5 pt-0">
		{#if loading}
			<div class="flex justify-center py-8"><Spinner size={16} /></div>
		{:else if filteredEntries.length === 0}
			<div class="flex flex-col items-center justify-center py-12 text-center">
				<Icon name="brain" size={24} class="text-gray-300 dark:text-gray-600 mb-3" />
				<p class="text-xs text-gray-500 dark:text-gray-400">
					{searchQuery ? 'No matching memories found.' : 'No memories saved yet.'}
				</p>
			</div>
		{:else}
			<div class="flex flex-col gap-3">
				{#each filteredEntries as entry}
					<div
						class="flex items-start justify-between gap-4 p-3 rounded-xl border border-gray-100 dark:border-white/6 bg-gray-50/50 dark:bg-white/[0.02]"
					>
						<div class="flex-1 min-w-0 whitespace-pre-wrap break-words text-[13px] text-gray-600 dark:text-gray-300 leading-relaxed">
							{entry}
						</div>
						<button
							class="shrink-0 p-1.5 text-gray-400 hover:text-red-500 dark:hover:text-red-400 rounded-lg hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors cursor-pointer"
							onclick={() => removeEntry(entry)}
							title="Remove memory"
						>
							<Icon name="trash" size={14} />
						</button>
					</div>
				{/each}
			</div>
		{/if}
	</div>

	{#if !loading && usage}
		<div class="shrink-0 p-4 md:px-5 border-t border-gray-200 dark:border-white/6">
			<p class="text-[11px] text-gray-400 dark:text-gray-500">{usage}</p>
		</div>
	{/if}
</Modal>
