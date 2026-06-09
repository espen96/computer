<script lang="ts">
	import { onMount } from 'svelte';

	interface Props {
		onClick?: () => void;
		onclose?: () => void;
		title?: string;
		content?: string;
	}

	let { onClick = () => {}, onclose = () => {}, title = '', content = '' }: Props = $props();

	let closeButtonEl: HTMLButtonElement;
	let startX = 0;
	let startY = 0;
	let moved = false;
	const DRAG_THRESHOLD_PX = 6;

	// ── Sound ──────────────────────────────────────────────────
	onMount(() => {
		if (!navigator.userActivation?.hasBeenActive) return;

		const soundEnabled = localStorage.getItem('notificationSound') !== 'false';
		if (soundEnabled) {
			const audio = new Audio('/audio/notification.mp3');
			audio.play().catch(() => {});
		}
	});

	// ── Interaction ────────────────────────────────────────────
	function onPointerDown(e: PointerEvent) {
		startX = e.clientX;
		startY = e.clientY;
		moved = false;
		(e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId);
	}

	function onPointerMove(e: PointerEvent) {
		if (moved) return;
		const dx = e.clientX - startX;
		const dy = e.clientY - startY;
		if (dx * dx + dy * dy > DRAG_THRESHOLD_PX * DRAG_THRESHOLD_PX) {
			moved = true;
		}
	}

	function onPointerUp(e: PointerEvent) {
		(e.currentTarget as HTMLElement).releasePointerCapture?.(e.pointerId);
		if (
			closeButtonEl &&
			(e.target === closeButtonEl || closeButtonEl.contains(e.target as Node))
		) {
			return;
		}
		if (!moved) {
			onClick();
		}
	}
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div
	role="status"
	aria-live="polite"
	class="notification-toast group"
	onpointerdown={onPointerDown}
	onpointermove={onPointerMove}
	onpointerup={onPointerUp}
	onpointercancel={() => (moved = true)}
>
	<!-- Close button -->
	<button
		bind:this={closeButtonEl}
		class="close-btn"
		aria-label="Dismiss notification"
		onclick={(e) => { e.stopPropagation(); onclose(); }}
	>
		<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-3 h-3">
			<path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
		</svg>
	</button>

	<!-- Icon -->
	<div class="icon-wrap">
		<img src="/favicon.png" alt="cptr" class="w-5 h-5 rounded-full" />
	</div>

	<!-- Content -->
	<div class="content">
		{#if title}
			<div class="title">{title}</div>
		{/if}
		{#if content}
			<div class="body">{content}</div>
		{/if}
	</div>
</div>

<style>
	.notification-toast {
		position: relative;
		display: flex;
		gap: 0.625rem;
		text-align: left;
		width: 100%;
		min-width: var(--width, 300px);
		background: #111;
		color: #e0e0e0;
		border: 1px solid rgba(255, 255, 255, 0.06);
		border-radius: 1rem;
		padding: 0.75rem 1rem;
		cursor: pointer;
		user-select: none;
	}

	:global(.dark) .notification-toast {
		background: #1a1a1a;
	}

	.close-btn {
		position: absolute;
		top: -0.125rem;
		left: -0.125rem;
		padding: 0.125rem;
		border-radius: 9999px;
		opacity: 0;
		background: #222;
		color: #888;
		border: none;
		cursor: pointer;
		transition: opacity 0.15s;
		z-index: 10;
	}

	.group:hover .close-btn {
		opacity: 1;
	}

	.close-btn:hover {
		background: #333;
		color: #ccc;
	}

	.icon-wrap {
		flex-shrink: 0;
		align-self: flex-start;
		transform: translateY(-0.125rem);
	}

	.content {
		min-width: 0;
	}

	.title {
		font-size: 13px;
		font-weight: 500;
		margin-bottom: 0.125rem;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		color: #fff;
	}

	.body {
		font-size: 12px;
		color: #aaa;
		font-weight: 400;
		display: -webkit-box;
		-webkit-line-clamp: 2;
		-webkit-box-orient: vertical;
		overflow: hidden;
	}
</style>
