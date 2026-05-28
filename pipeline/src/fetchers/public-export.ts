import { createRequire } from 'node:module';
const _require = createRequire(import.meta.url);
const { LZMA } = _require('lzma/src/lzma_worker.js') as {
  LZMA: { decompress: (data: number[], cb: (result: number[] | string, err: string | null) => void) => void };
};

const INDEX_URL = 'https://origin.warframe.com/PublicExport/index_en.txt.lzma';
const CONTENT_BASE = 'https://content.warframe.com/PublicExport/Manifest/';

const EXPORT_KEYS = [
  'ExportWarframes_en.json',
  'ExportUpgrades_en.json',
  'ExportWeapons_en.json',
] as const;

type ExportKey = (typeof EXPORT_KEYS)[number];

function lzmaDecompress(data: Uint8Array): Promise<string> {
  return new Promise((resolve, reject) => {
    LZMA.decompress(Array.from(data), (result: number[] | string, err: string | null) => {
      if (err) { reject(new Error(String(err))); return; }
      const bytes = typeof result === 'string'
        ? Buffer.from(result, 'binary')
        : Buffer.from(result);
      resolve(bytes.toString('utf8'));
    });
  });
}

// Index format per line: ExportFoo_en.json!<hash>
function parseIndex(text: string): Map<string, string> {
  const map = new Map<string, string>();
  for (const line of text.trim().split('\n')) {
    const bang = line.lastIndexOf('!');
    if (bang === -1) continue;
    const filename = line.slice(0, bang).trim();
    const hash = line.slice(bang + 1).trim();
    if (filename && hash) map.set(filename, hash);
  }
  return map;
}

export interface PublicExportRaw {
  indexHash: string;
  exports: Record<ExportKey, unknown>;
}

export async function fetchPublicExport(): Promise<PublicExportRaw> {
  // Index is LZMA-compressed
  const indexRes = await fetch(INDEX_URL);
  if (!indexRes.ok) throw new Error(`HTTP ${indexRes.status}: ${INDEX_URL}`);
  const indexBytes = new Uint8Array(await indexRes.arrayBuffer());
  const indexText = await lzmaDecompress(indexBytes);
  const pathMap = parseIndex(indexText);

  // Use first export hash as a change-detection token
  const indexHash = [...pathMap.values()][0] ?? '';

  const exports: Partial<Record<ExportKey, unknown>> = {};

  for (const key of EXPORT_KEYS) {
    const hash = pathMap.get(key);
    if (!hash) throw new Error(`Export key not found in index: ${key}`);
    // Content is served as plain JSON; hash is a cache-busting suffix
    const url = `${CONTENT_BASE}${key}!${hash}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${url}`);
    exports[key] = (await res.json()) as unknown;
  }

  return { indexHash, exports: exports as Record<ExportKey, unknown> };
}
