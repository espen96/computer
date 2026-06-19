<script lang="ts">
	interface Props {
		value: boolean;
		onchange?: (value: boolean) => void;
		disabled?: boolean;
	}
	let { value, onchange, disabled = false }: Props = $props();
</script>

<button
	type="button"
	class="relative w-7 h-4 rounded-full transition-colors duration-150 shrink-0
		{value ? 'bg-gray-900 dark:bg-white' : 'bg-gray-300 dark:bg-gray-700'}"
	onclick={() => onchange?.(!value)}
	{disabled}
	role="switch"
	aria-checked={value}
>
	<span
		class="absolute top-[2px] w-3 h-3 rounded-full transition-all duration-150
			{value ? 'left-[14px] bg-white dark:bg-black' : 'left-[2px] bg-white dark:bg-gray-500'}"
	></span>
</button>
