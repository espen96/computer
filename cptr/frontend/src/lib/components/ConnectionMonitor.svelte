<script lang="ts">
	import { onMount } from 'svelte';
	import { toast } from 'svelte-sonner';
	import { t } from '$lib/i18n';

	let isOnline = $state(true);
	let toastId: string | number | undefined;
	let healthTimer: ReturnType<typeof setInterval> | null = null;

	function showOffline() {
		if (!isOnline) return;
		isOnline = false;
		toastId = toast.error($t('pwa.reconnecting'), { duration: Infinity });
		startPolling();
	}

	function showOnline() {
		if (isOnline) return;
		isOnline = true;
		if (toastId) toast.dismiss(toastId);
		toastId = undefined;
		stopPolling();
	}

	function checkHealth() {
		fetch('/api/health', { method: 'HEAD', cache: 'no-store' })
			.then((res) => {
				if (res.ok) showOnline();
			})
			.catch(() => {});
	}

	function startPolling() {
		stopPolling();
		healthTimer = setInterval(checkHealth, 5000);
	}

	function stopPolling() {
		if (healthTimer) {
			clearInterval(healthTimer);
			healthTimer = null;
		}
	}

	onMount(() => {
		// Only react to browser offline/online events.
		// Don't probe on mount; if we loaded, we're online.
		window.addEventListener('offline', showOffline);
		window.addEventListener('online', () => {
			// Browser says online, verify with a real request
			checkHealth();
		});

		return () => {
			window.removeEventListener('offline', showOffline);
			window.removeEventListener('online', checkHealth);
			stopPolling();
			if (toastId) toast.dismiss(toastId);
		};
	});
</script>
