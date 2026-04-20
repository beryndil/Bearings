#!/usr/bin/env node
// Copies frontend/build/ into src/bearings/web/dist/ so FastAPI serves the
// just-built SvelteKit bundle. Runs as the post-step of `npm run build`.

import { cp, mkdir, rm } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const source = resolve(here, '..', 'frontend', 'build');
const target = resolve(here, '..', 'src', 'bearings', 'web', 'dist');

await rm(target, { recursive: true, force: true });
await mkdir(target, { recursive: true });
await cp(source, target, { recursive: true });
console.log(`synced ${source} -> ${target}`);
