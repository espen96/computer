<script lang="ts">
	import type { Token } from 'marked';

	interface Props {
		items: Token[];
	}

	let { items }: Props = $props();

	let decoder: HTMLTextAreaElement | undefined;
	function decodeEntities(text: string): string {
		if (typeof document === 'undefined') return text;
		if (!text.includes('&')) return text;
		if (!decoder) decoder = document.createElement('textarea');
		decoder.innerHTML = text;
		return decoder.value;
	}

	const WIKILINK_HTML_RE = /^<wikilink data-target="([^"]+)">([^<]+)<\/wikilink>$/;

	function parseWikilink(raw: string): { target: string; label: string } | null {
		const match = raw.trim().match(WIKILINK_HTML_RE);
		if (match) return { target: match[1], label: match[2] };
		return null;
	}
</script>

{#each items as item}
	{#if item.type === 'text'}
		{#if 'tokens' in item && item.tokens}
			<svelte:self items={item.tokens} />
		{:else}
			{decodeEntities(('text' in item) ? item.text : item.raw)}
		{/if}

	{:else if item.type === 'strong'}
		<strong>{#if 'tokens' in item && item.tokens}<svelte:self items={item.tokens} />{:else}{item.raw}{/if}</strong>

	{:else if item.type === 'em'}
		<em>{#if 'tokens' in item && item.tokens}<svelte:self items={item.tokens} />{:else}{item.raw}{/if}</em>

	{:else if item.type === 'del'}
		<del>{#if 'tokens' in item && item.tokens}<svelte:self items={item.tokens} />{:else}{item.raw}{/if}</del>

	{:else if item.type === 'codespan'}
		<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
		<code
			class="codespan cursor-pointer"
			onclick={() => {
				const text = ('text' in item) ? item.text : item.raw;
				navigator.clipboard.writeText(text);
			}}
		>{('text' in item) ? item.text : item.raw}</code>

	{:else if item.type === 'link'}
		<a href={('href' in item) ? item.href : '#'} target="_blank" rel="noopener noreferrer">
			{#if 'tokens' in item && item.tokens}
				<svelte:self items={item.tokens} />
			{:else}
				{('text' in item) ? item.text : item.raw}
			{/if}
		</a>

	{:else if item.type === 'image'}
		<img
			src={('href' in item) ? item.href : ''}
			alt={('text' in item) ? item.text : ''}
			title={('title' in item) ? item.title : undefined}
			loading="lazy"
		/>

	{:else if item.type === 'br'}
		<br />

	{:else if item.type === 'escape'}
		{('text' in item) ? item.text : item.raw}

	{:else if item.type === 'html'}
		{@const wl = parseWikilink(item.raw)}
		{#if wl}
			<span class="text-blue-500 dark:text-blue-400 bg-blue-500/8 dark:bg-blue-400/10 rounded px-1 cursor-pointer hover:underline transition-colors" title="Link to {wl.target}">{wl.label}</span>
		{/if}
	{/if}
{/each}
