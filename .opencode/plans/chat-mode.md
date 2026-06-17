# Plan: Basic Chat Mode

## Context

The app currently has workspaces (file-system rooted, multi-chat) as the primary unit. The user wants a simpler "chat-first" mode where:
- Each chat is the primary entity, with an auto-generated workspace underneath
- Chats appear in a separate sidebar section grouped by date
- One chat per auto-generated workspace
- Deleting a chat deletes its workspace and files
- The workspace exists to keep tools/artifacts working, not as the user-facing concept

This is analogous to ChatGPT/Claude's web chat containers, but with direct filesystem access.

---

## Architecture Decisions

### Workspace path convention
`~/.cptr/chat-workspaces/{chat_id}/` — each chat gets its own directory under a dedicated parent.

### Database
Add `is_chat` boolean column to the `workspaces` table. This distinguishes chat-mode workspaces (auto-generated, one-chat) from regular workspaces (user-opened folders). No new table needed — the existing Workspace model handles it.

### Sidebar
New "Chats" section above "Workspaces" in the sidebar. Fetches all `is_chat=true` workspaces for the user, groups them by date (Today, Yesterday, Previous 7 Days, Previous 30 Days, Older). Each item shows the chat title and relative time.

### Main view
When a chat-mode workspace is opened, it loads like a normal workspace but:
- Defaults to a single chat tab (no file browser, terminal, etc. by default)
- The file browser is still accessible if the user wants it
- Only one chat exists in this workspace

---

## Implementation Steps

### 1. Database migration: add `is_chat` column to `workspaces`

**File:** `cptr/migrations/versions/0004_add_chat_mode.py` (new)

Add a boolean `is_chat` column (default `False`) to the `workspaces` table. Non-chat workspaces remain unchanged.

### 2. Update Workspace model

**File:** `cptr/models/workspaces.py`

- Add `is_chat = Column(Boolean, nullable=False, default=False)` to the model
- Add `get_chat_workspaces(user_id)` class method: returns all workspaces where `is_chat=True`, ordered by `created_at DESC`
- Add `delete_chat_workspace(user_id, chat_id)` class method: deletes the workspace row + the filesystem directory

### 3. Backend: chat creation auto-generates workspace

**File:** `cptr/routers/chat.py`

Modify the `send_message` POST endpoint:
- When creating a new chat (no `chat_id`), if the workspace path starts with `~/.cptr/chat-workspaces/` (or matches a chat-mode pattern), create a `Workspace` row with `is_chat=True`
- Actually, simpler: add a new flag in the request body (`chat_mode: bool = False`). When `chat_mode=True`:
  - Generate workspace path: `DATA_DIR / "chat-workspaces" / chat_id`
  - Create the directory
  - Create a `Workspace` row with `is_chat=True`
  - Set `chat.meta["workspace"]` to this path

### 4. Backend: new endpoint to list chat-mode workspaces

**File:** `cptr/routers/state.py`

Add `GET /api/state/chats` endpoint:
- Returns all workspaces where `is_chat=True` for the user
- Each entry includes: `path`, `name` (chat title), `created_at`, `updated_at`
- Frontend groups these by date

### 5. Backend: delete chat also deletes workspace

**File:** `cptr/routers/chat.py`

Modify the `delete_chat` endpoint:
- After deleting the chat, check if its `meta.workspace` points to a chat-mode workspace
- If so, delete the `Workspace` row and the filesystem directory

### 6. Frontend: add `getChats()` API call for chat-mode workspaces

**File:** `cptr/frontend/src/lib/apis/state.ts`

Add `getChatWorkspaces()` function that calls `GET /api/state/chats`.

### 7. Frontend: add chat-mode state to stores

**File:** `cptr/frontend/src/lib/stores.ts`

- Add `chatList` store (similar to `workspaceList`)
- Add `loadChatList()` function
- Modify `initState()` to also load chat list

### 8. Frontend: update Sidebar with "Chats" section

**File:** `cptr/frontend/src/lib/components/Sidebar.svelte`

Add a new section above "Workspaces":
- Section header: "Chats" with a "+" button to start new chat
- Fetch chat-mode workspaces from `GET /api/state/chats`
- Group by date: Today, Yesterday, Previous 7 Days, Previous 30 Days, Older
- Each item renders like a `ChatItem` but clicking navigates to `/?workspace={path}&chatId={chatId}`
- Date group headers are collapsible

### 9. Frontend: new chat button creates a chat directly

**File:** `cptr/frontend/src/lib/components/Sidebar.svelte`

The "+" button in the Chats section:
- Opens a new chat tab in the current workspace, OR
- Creates a new chat-mode workspace directly
- Sends the first message which triggers workspace creation on the backend

### 10. Frontend: main view handles chat-mode workspaces

**File:** `cptr/frontend/src/routes/+page.svelte`

When loading a chat-mode workspace:
- Detect via workspace data (`is_chat` flag or path pattern)
- Default to showing just a chat tab (no file browser by default)
- User can still add other tabs if they want

### 11. i18n: add new translation keys

**File:** `cptr/frontend/src/lib/i18n/locales/en.json` (and other locales)

New keys:
- `sidebar.chats`: "Chats"
- `sidebar.newChat`: "New chat"
- `sidebar.noChats`: "No chats yet"
- `sidebar.chatGroup.today`: "Today"
- `sidebar.chatGroup.yesterday`: "Yesterday`
- `sidebar.chatGroup.previous7Days`: "Previous 7 days"
- `sidebar.chatGroup.previous30Days`: "Previous 30 days"
- `sidebar.chatGroup.older`: "Older"

---

## Key Files to Modify

| File | Change |
|------|--------|
| `cptr/migrations/versions/0004_add_chat_mode.py` | New migration |
| `cptr/models/workspaces.py` | Add `is_chat` column + query methods |
| `cptr/routers/chat.py` | Auto-create chat workspace on new chat |
| `cptr/routers/state.py` | New `/api/state/chats` endpoint |
| `cptr/frontend/src/lib/apis/state.ts` | New `getChatWorkspaces()` API call |
| `cptr/frontend/src/lib/stores.ts` | New `chatList` store + load function |
| `cptr/frontend/src/lib/components/Sidebar.svelte` | New "Chats" section with date grouping |
| `cptr/frontend/src/routes/+page.svelte` | Handle chat-mode workspace defaults |
| `cptr/frontend/src/lib/i18n/locales/en.json` | New translation keys |

---

## Verification

1. Run migration: verify `is_chat` column exists in `workspaces` table
2. Create a new chat via the sidebar "+" button: verify workspace is created at `~/.cptr/chat-workspaces/{id}/`
3. Verify the chat appears in the sidebar "Chats" section under the correct date group
4. Open the chat: verify it loads with a single chat tab
5. Delete the chat: verify both the DB row and filesystem directory are removed
6. Verify regular workspaces still work unchanged
7. Run frontend lint/typecheck
