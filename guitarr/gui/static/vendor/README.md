# Vendored third-party files

These files are copied verbatim so the web UI works offline, with no Node/npm and no build step.

| Path | Package | Version | License | Source |
|---|---|---|---|---|
| `i18next/i18next.js` | i18next (ESM build, `dist/esm/i18next.js`) | 23.16.8 | MIT (see `i18next/LICENSE`) | https://www.npmjs.com/package/i18next |
| `tasks-vision/vision_bundle.mjs` | @mediapipe/tasks-vision | 1.1.1 | Apache-2.0 | https://www.npmjs.com/package/@mediapipe/tasks-vision |
| `mediapipe/wasm/*` | @mediapipe/tasks-vision (`wasm/`) | 1.1.1 | Apache-2.0 | same package |
| `mediapipe/hand_landmarker.task` | MediaPipe Hand Landmarker model (float16) | 1 | Apache-2.0 | https://ai.google.dev/edge/mediapipe/solutions/vision/hand_landmarker |

To update one, download the new package (`npm pack <name>@<version>`), copy the same files, and update this table.
