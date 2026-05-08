# Tarteel Apps Config

Centralized configuration for all Tarteel Quran apps. This repository is served via **GitHub Pages** and consumed by all apps for the "More Apps" cross-promotion feature.

## How It Works

- `apps.json` contains metadata for all published apps (name, description, icon, Play Store URL)
- Each app fetches this file at runtime and displays other apps in a premium in-app UI
- The current app is automatically filtered out from the list

## Adding a New App

1. Add the app icon to `icons/` (256×256 PNG recommended)
2. Add a new entry to the `apps` array in `apps.json`
3. Commit and push — the change goes live immediately via GitHub Pages

## JSON Schema

| Field | Type | Description |
|---|---|---|
| `id` | string | Unique app identifier |
| `packageName` | string | Android package name |
| `name` | object | Localized app names (`ar`, `en`, `fr`) |
| `description` | object | Localized short descriptions |
| `icon` | string | URL to app icon (hosted in this repo) |
| `playStoreUrl` | string | Google Play Store link |
| `featured` | boolean | Whether to highlight this app |
| `order` | number | Display order (lower = first) |

## URLs

- **JSON endpoint:** `https://tarteelquranapps.github.io/tarteel-apps-config/apps.json`
- **Icons:** `https://tarteelquranapps.github.io/tarteel-apps-config/icons/<app-id>.png`
