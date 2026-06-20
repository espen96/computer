<script lang="ts">
	import { goto } from '$app/navigation';
	import { toast } from 'svelte-sonner';
	import { get } from 'svelte/store';
	import { mainProjectDirectory, addWorkspace } from '$lib/stores';
	import { createEntry } from '$lib/apis/files';
	import Modal from './Modal.svelte';

	interface Props {
		onclose: () => void;
	}

	let { onclose }: Props = $props();

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
			onclose();
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
</script>

<Modal
	{onclose}
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
			onclick={onclose}
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
