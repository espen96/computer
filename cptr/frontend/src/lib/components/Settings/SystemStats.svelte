<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { getWelcome } from '$lib/apis/state';
	import SystemInfo from '../SystemInfo.svelte';
	import Spinner from '../common/Spinner.svelte';

	let systemData = $state<any>(null);
	let loading = $state(true);
	let timer: any;

	async function fetchStats() {
		try {
			systemData = await getWelcome();
		} catch (e) {
			console.error(e);
		} finally {
			loading = false;
		}
	}

	onMount(() => {
		fetchStats();
		timer = setInterval(fetchStats, 5000);
	});

	onDestroy(() => {
		if (timer) clearInterval(timer);
	});
</script>

<div class="flex flex-col h-full">
	{#if loading && !systemData}
		<div class="flex justify-center py-8">
			<Spinner size={16} />
		</div>
	{:else if systemData}
		<div class="flex-1 min-h-0 overflow-y-auto scrollbar-hover pr-1.5 -mr-1.5">
			<h2 class="text-sm font-medium text-gray-900 dark:text-white mb-4">System Stats</h2>
			{#if systemData.system}
				<div class="border border-gray-100 dark:border-white/6 rounded-xl p-4 bg-gray-50/50 dark:bg-white/2">
					<SystemInfo system={systemData.system} processes={systemData.processes} />
				</div>
			{/if}
		</div>
	{/if}
</div>
