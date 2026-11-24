# Glass

A liquid-glass AI sidebar for Windows, macOS and Linux. Flick your cursor fast into the left or right edge of the screen and Glass slides out. Ask anything, drop in files, screenshot what you're looking at, or just talk to it.

```
GlassSidebar/
├─ windows/   C# / WPF  → GlassSidebar.exe   (live refraction glass)
├─ mac/       Swift / SwiftUI → Glass.app    (Apple Liquid Glass on macOS 26)
└─ linux/     Python / Qt6 → `glass`         (X11 + XWayland)
```

## Features

| | Windows | macOS | Linux |
|---|---|---|---|
| Flick-to-open from either screen edge | ✅ | ✅ | ✅ X11 / XWayland |
| Glass | Live refraction (custom renderer) | System Liquid Glass (macOS 26), vibrancy on 14–15 | Snapshot refraction + KDE blur |
| Tint (default semi-gray), strength, blur/style | ✅ | ✅ | ✅ |
| Fullscreen mode with chats sidebar | ✅ | ✅ | ✅ |
| Saved chats, search, pin, delete, copy as Markdown, smart AI titles | ✅ | ✅ | ✅ |
| Claude, Gemini (all models), Groq, OpenAI-compatible (OpenRouter, Ollama, LM Studio…) | ✅ | ✅ | ✅ |
| Switch model mid-chat (⌘K / Ctrl+K) with one saved key per provider | ✅ | ✅ | ✅ |
| Attach images, PDFs, text and code (picker, drag-and-drop, paste) | ✅ | ✅ | ✅ |
| Ask about my screen (screenshot of what's *behind* the panel) | ✅ | ✅ | ✅ |
| Edit and resend, regenerate, stop, copy, read aloud | ✅ | ✅ | ✅ |
| Dictation + hands-free voice mode (listen → reply → speak → listen) | ✅ Windows Speech | ✅ on-device Speech | ✅ Whisper via Groq/OpenAI key |
| Markdown, tables, code blocks with copy | ✅ | ✅ | ✅ |

## Getting an API key

| Provider | Where | Looks like |
|---|---|---|
| Claude | console.anthropic.com | `sk-ant-…` |
| Gemini | aistudio.google.com | `AIza…` |
| Groq | console.groq.com | `gsk_…` |
| OpenAI / compatible | your provider | `sk-…` + base URL |

Open **Settings**, then paste the key, or import it from a `.txt`, `.env` or `.json` file. Glass works out which provider a key belongs to from its prefix. Each provider keeps its own key, so you can switch between providers without pasting again.

Keys stay on your machine:
- **Windows:** encrypted with DPAPI.
- **macOS:** Keychain.
- **Linux:** the system keyring, or a `0600` file if there is no keyring.

Keys are only ever sent to the provider's API.

---

## Windows

**Requirements:** Windows 10 2004+ or Windows 11. You don't need to install anything else, because the build uses the C# compiler that ships with .NET Framework 4.

```bat
cd windows
build.bat
```

This produces `windows\GlassSidebar.exe` and starts it. Copy the EXE anywhere you like. To start it at login, put a shortcut to it in `shell:startup`.

- **Open:** flick to an edge, press **Ctrl+Alt+Space**, or use the tray icon.
- **Crash log:** `%TEMP%\GlassSidebar.log`
- **Data:** `%APPDATA%\GlassSidebar\` (settings and `chats\`)

**How the glass works:** Glass hides itself from screen capture (`WDA_EXCLUDEFROMCAPTURE`), so every frame it can capture what's behind the panel. It then blurs that image and refracts it through a rounded bezel, adding chromatic split, rim light and gloss. The result is real refraction of live content, not a static blur.

## macOS

**Requirements:** macOS 14+ and Xcode or the Command Line Tools (`xcode-select --install`). For true Liquid Glass you need macOS 26 and a build made with Xcode 26.

```bash
cd mac
chmod +x build.sh
./build.sh            # builds build/Glass.app and opens it
./build.sh install    # also copies it to /Applications
```

- **Open:** flick to an edge, press **⌃⌥Space**, or use the ✨ menu-bar icon.
- **Permissions:** macOS asks for each one the first time you use the feature.
  - **Microphone** and **Speech Recognition:** dictation and voice mode.
  - **Screen Recording:** "Ask about my screen". Glass leaves its own window out of the screenshot.
- **Data:** `~/Library/Application Support/Glass/chats`, plus `UserDefaults` and the Keychain.

## Linux

**Requirements:** Python 3.9+. Works on X11 and on Wayland through XWayland.

```bash
cd linux
chmod +x install.sh
./install.sh
glass
```

This installs a private virtual environment with PySide6, numpy and keyring into `~/.local/share/glass-app`, the `glass` launcher into `~/.local/bin`, and a desktop entry.

- **Open:** flick to an edge (X11 or XWayland), use the tray icon, or bind **`glass --toggle`** to a keyboard shortcut in your desktop settings.
- **Wayland:** Wayland doesn't let apps place windows or read the global cursor, so Glass runs through XWayland by default. If flicks don't fire, use the shortcut.
- **Glass effect:** Qt can't see behind its own window, so the glass is rendered from a screenshot taken each time the panel opens. KDE Plasma also gets real blur-behind.
- **Optional extras:**
  - Read replies aloud: `speech-dispatcher` or `espeak-ng`.
  - Screenshots on wlroots compositors: `grim`.
  - Voice input: transcribed with Whisper, which needs a Groq key (free tier) or an OpenAI key.
- **Data:** `~/.config/glass`, `~/.local/share/glass/chats`

---

## Shortcuts

Windows/Linux use **Ctrl**; macOS uses **⌘**.

| | |
|---|---|
| Toggle Glass from anywhere | Ctrl+Alt+Space / ⌃⌥Space |
| New chat | Ctrl+N |
| Switch model | Ctrl+K |
| Settings | Ctrl+, |
| Attach files | Ctrl+O |
| Ask about my screen | Ctrl+Shift+S |
| Voice mode | Ctrl+Shift+V |
| Fullscreen | F11 (Win/Linux) · ⌘F (Mac) |
| Keep open / pin | ⌘P (Mac) · pin button |
| Edit last message | ↑ in an empty composer |
| New line | Shift+Enter (Win/Linux) · ⌥⏎ (Mac) |
| Close / stop / back | Esc |

## Flick sensitivity

You can pick **Firm**, **Normal** or **Light** in Settings. Glass opens when the cursor reaches a screen edge fast enough, after travelling a minimum distance in the last ~90 ms:

| Setting | Speed (× screen width per second) | Distance (× screen width) |
|---|---|---|
| Firm | 2.4 | 16% |
| Normal | 1.6 | 10% |
| Light | 1.05 | 6% |

Flicking the same edge again closes the panel.

## Troubleshooting

- **"No API key yet":** open Settings and add a key for the provider shown in the header.
- **API error 404 / model not found:** pick a model from the list in Settings or with Ctrl+K. Gemini and Groq lists come live from your account.
- **Windows build error:** paste the `error CSxxxx` line. Make sure no other GlassSidebar.exe is running; `build.bat` already kills old copies.
- **Mac: the screenshot is blank, or the mic does nothing:** check System Settings → Privacy & Security. You may need to re-run `build.sh` after granting permissions, so the signature matches.
- **Linux: screenshots are black on Wayland:** install `grim`, or use GNOME's or KDE's own screenshot tool. Glass tries each of them in turn.
