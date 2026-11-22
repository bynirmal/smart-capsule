# Smart Capsule Capture — Chrome extension (Manifest V3)

Captures a conversation from ChatGPT, Claude or Gemini and hands it to the local
Smart Capsule server, which validates, structures, compresses and stores it.

## Install (unpacked)

1. Start the local server so the bridge token exists:
   ```bash
   .venv\Scripts\python.exe -m webapp
   ```
2. Open `chrome://extensions`, enable **Developer mode**, click **Load unpacked**
   and select this `browser_extension/` folder.
3. Open the extension popup, paste the token from your data folder
   (`bridge_token.txt`, path printed by the server), and press **Save**.

## Use

* Toolbar button → popup → **Capture this conversation**.
* Or open the side panel (**Open side panel**) to keep capture one click away while you work.
* Capture is always user-initiated. The extension never reads the page in the
  background, and never touches cookies, passwords or session storage.

## Adapters

| Adapter | Version | Selector strategy |
| --- | --- | --- |
| `chatgpt` | 1.1.0 | `[data-message-author-role]` nodes |
| `claude` | 1.0.0 | `[data-testid="user-message"]`, `.font-claude-message` |
| `gemini` | 1.0.0 | `<user-query>` / `<model-response>` elements |
| `generic` | 1.0.0 | author-role attributes, then visible text as one message |

Sites change markup, so adapters are versioned, every lookup is defensive, and a
failed adapter reports a warning instead of returning a silently truncated
conversation. When no structure is detected the visible page text is captured as
a single message with an explicit warning.

## Bridge API

```
POST http://127.0.0.1:8765/api/bridge/capture
X-SmartCapsule-Token: <bridge_token.txt contents>
{ "text": "User: …\n\nAssistant: …", "platform": "ChatGPT", "mode": "balanced" }
```

`401` means the token is missing or stale; `400` means the text could not be
parsed. The server only accepts loopback connections.
