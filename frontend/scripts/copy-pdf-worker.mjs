import { copyFileSync, mkdirSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const worker = require.resolve('pdfjs-dist/build/pdf.worker.min.mjs');
const target = resolve(root, 'public/pdf.worker.min.mjs');

mkdirSync(dirname(target), { recursive: true });
copyFileSync(worker, target);
console.log(`pdf.worker.min.mjs -> ${target}`);
