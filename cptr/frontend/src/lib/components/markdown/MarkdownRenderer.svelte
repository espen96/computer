<script lang="ts">
	/**
	 * General-purpose Markdown renderer.
	 *
	 * Usage:
	 *   <MarkdownRenderer content={markdownString} />
	 *
	 * Parses markdown via marked.lexer() into AST tokens,
	 * then renders each token as a Svelte component.
	 * Styled entirely via Tailwind prose — no custom CSS.
	 */

	import { Lexer } from 'marked';
	import BlockRenderer from './BlockRenderer.svelte';

	interface Props {
		content: string;
	}

	let { content }: Props = $props();

	// Pre-process wikilinks: [[target|label]] → <wikilink target="target">label</wikilink>
	const WIKILINK_RE = /\[\[([^\[\]|]+?)(?:\|([^\[\]]+?))?\]\]/g;

	function preprocessWikilinks(text: string): string {
		return text.replace(WIKILINK_RE, (_match, target, label) => {
			const t = target.trim();
			const l = (label || target).trim();
			return `<wikilink data-target="${t}">${l}</wikilink>`;
		});
	}

	let tokens = $derived.by(() => {
		if (!content) return [];
		try {
			const processed = preprocessWikilinks(content);
			return new Lexer().lex(processed);
		} catch {
			return [];
		}
	});
</script>

<div class="prose prose-sm dark:prose-invert max-w-none break-words prose-p:my-0 prose-headings:my-1 prose-headings:font-semibold prose-strong:font-semibold prose-th:font-semibold prose-code:before:content-none prose-code:after:content-none prose-ul:-my-0 prose-ol:-my-0 prose-li:-my-0 prose-pre:my-0 prose-blockquote:my-0 prose-hr:my-4 prose-img:my-1 prose-table:my-0">
	<BlockRenderer {tokens} />
</div>
