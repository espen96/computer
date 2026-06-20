<script lang="ts">
	interface Props {
		canSend: boolean;
		streaming: boolean;
		onsend: () => void;
		oncancel?: () => void;
		onvoice?: () => void;
		voiceActive?: boolean;
	}
	let { canSend, streaming, onsend, oncancel, onvoice, voiceActive = false }: Props = $props();

	// Show send when there's sendable text, even during streaming (enqueue).
	// Show stop only when streaming with nothing to send.
	const showStop = $derived(streaming && !canSend && !!oncancel);
	const showVoice = $derived(!streaming && !canSend && !!onvoice);
</script>

{#if showStop}
	<button
		class="bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-white hover:bg-gray-200 dark:hover:bg-gray-600 transition rounded-md p-1"
		onclick={oncancel}
	>
		<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" class="size-4">
			<path
				fill-rule="evenodd"
				d="M2.25 12c0-5.385 4.365-9.75 9.75-9.75s9.75 4.365 9.75 9.75-4.365 9.75-9.75 9.75S2.25 17.385 2.25 12zm6-2.438c0-.724.588-1.312 1.313-1.312h4.874c.725 0 1.313.588 1.313 1.313v4.874c0 .725-.588 1.313-1.313 1.313H9.564a1.312 1.312 0 01-1.313-1.313V9.564z"
				clip-rule="evenodd"
			/>
		</svg>
	</button>
{:else if showVoice}
	<button
		class="flex items-center justify-center rounded-md p-1 transition
			{voiceActive
			? 'bg-gray-900 text-white dark:bg-white dark:text-black'
			: 'bg-gray-100 text-gray-800 hover:bg-gray-200 dark:bg-white/90 dark:text-black dark:hover:bg-white'}"
		onclick={onvoice}
		aria-label="Voice mode"
		title="Voice mode"
	>
		<svg
			xmlns="http://www.w3.org/2000/svg"
			viewBox="0 0 24 24"
			fill="none"
			stroke="currentColor"
			stroke-width="2"
			stroke-linecap="round"
			stroke-linejoin="round"
			class="size-4 {voiceActive ? 'animate-pulse' : ''}"
		>
			<path d="M4 14V10" />
			<path d="M8 18V6" />
			<path d="M12 21V3" />
			<path d="M16 18V6" />
			<path d="M20 14V10" />
		</svg>
	</button>
{:else}
	<button
		class="{canSend
			? 'bg-black/80 text-white hover:bg-gray-900 dark:bg-olive-600 dark:text-white/70 dark:hover:bg-olive-500'
			: 'text-white bg-gray-200 dark:text-gray-800 dark:bg-gray-700 cursor-default'} transition rounded-md p-1 self-center"
		onclick={onsend}
		disabled={!canSend}
	>
		<svg
			class="size-4 p-0.5"
			viewBox="0 0 12 12"
			fill="currentColor"
			xmlns="http://www.w3.org/2000/svg"
		>
			<path
				d="M11.3333 0C11.7014 2.72075e-05 11.9999 0.298494 11.9999 0.666667V5.33333C11.9999 6.21738 11.6485 7.06499 11.0234 7.6901C10.3983 8.31521 9.55065 8.66665 8.66662 8.66667H2.27599L4.4713 10.862C4.73162 11.1223 4.73162 11.5443 4.4713 11.8047C4.21096 12.065 3.78895 12.065 3.5286 11.8047L0.195262 8.47135C-0.0650874 8.21101 -0.0650874 7.789 0.195262 7.52865L3.5286 4.19531C3.78895 3.93499 4.21096 3.93497 4.4713 4.19531C4.73162 4.45566 4.73162 4.87768 4.4713 5.13802L2.27599 7.33333H8.66662L8.86453 7.32357C9.32227 7.27805 9.75256 7.07552 10.0807 6.7474C10.4557 6.37233 10.6666 5.86375 10.6666 5.33333V0.666667C10.6666 0.298477 10.9651 0 11.3333 0Z"
			/>
		</svg>
	</button>
{/if}
