---
paths:
  - "**/manifest.json"
  - "**/manifest.webmanifest"
  - "**/*.webmanifest"
  - "**/vercel.json"
---

# PWA and Android manifests

General rules for any project that ships a web app manifest (learned the hard way: on Android a PWA only became a shortcut):

- One icon entry per size (192x192 and 512x512 PNG), each with `"purpose": "any maskable"`. Never list the same file twice with different purposes.
- Set `id`, `start_url` and `scope` explicitly and keep them consistent; `display` is `standalone`.
- Serve the manifest as `application/manifest+json`; make sure rewrites (for example a catch-all to `index.html`) do not intercept the manifest, icons or the service worker.
- A service worker is not needed to install the app; add one only for push or offline.
- When something does not install, compare with a PWA that does before theorising, and test on a real Android phone: remove the old shortcut, fully close Chrome (it caches the manifest), wait about 30 seconds on the page, then use "Install app".
