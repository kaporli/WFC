const WIKI_API = 'https://wiki.warframe.com/api.php';
const BATCH_SIZE = 50;
const HEADERS = { 'User-Agent': 'warframe-planner/0.1 (educational; github.com/warframe-planner)' };
const RATE_LIMIT_MS = 200;  // polite delay between wiki API calls
const MAX_RETRIES = 3;

export interface ItemRef {
  uniqueName: string;
  name: string;
  wikiaThumbnail?: string;
}

export type ImageMap = Record<string, Record<string, string>>; // uniqueName → { filename → cdnUrl }

function normName(s: string): string {
  return s.toLowerCase().replace(/[^a-z0-9]/g, '');
}

function isRelevantFile(filename: string, itemNorm: string): boolean {
  if (!/\.(png|jpg|jpeg)$/i.test(filename)) return false;
  const fileNorm = normName(filename.replace(/\.[^.]+$/, ''));
  return fileNorm.includes(itemNorm);
}

function sleep(ms: number): Promise<void> {
  return new Promise(r => setTimeout(r, ms));
}

async function fetchJson(params: URLSearchParams): Promise<unknown> {
  for (let attempt = 0; attempt < MAX_RETRIES; attempt++) {
    if (attempt > 0) await sleep(RATE_LIMIT_MS * (attempt + 1) * 2); // backoff
    try {
      const res = await fetch(`${WIKI_API}?${params}`, { headers: HEADERS });
      if (res.status === 429 || res.status >= 500) continue; // retry
      if (!res.ok) return null;
      return await res.json();
    } catch {
      // network error — retry
    }
  }
  return null;
}

type ImagesPage = { title: string; missing?: boolean; images?: Array<{ title: string }> };
type ImageInfoPage = { title: string; imageinfo?: Array<{ url: string }> };
type RedirectEntry = { from: string; to: string };

// Returns map from ORIGINAL requested title → all image filenames on the resolved page.
// Handles redirects: "Ash Prime" → wiki page "Ash", keyed back as "Ash Prime".
async function fetchPageImages(titles: string[]): Promise<Map<string, string[]>> {
  const resolvedTitle = new Map<string, string>(titles.map(t => [t, t]));
  const accumulated = new Map<string, Set<string>>();
  let imcontinue: string | undefined;

  do {
    await sleep(RATE_LIMIT_MS);
    const params = new URLSearchParams({
      action: 'query',
      titles: titles.join('|'),
      prop: 'images',
      redirects: '1',
      imlimit: '500',
      format: 'json',
      formatversion: '2',
    });
    if (imcontinue) params.set('imcontinue', imcontinue);

    const data = await fetchJson(params) as {
      query?: {
        redirects?: RedirectEntry[];
        normalized?: RedirectEntry[];
        pages?: ImagesPage[];
      };
      continue?: { imcontinue?: string };
    } | null;
    if (!data) break;

    for (const r of data.query?.redirects ?? []) resolvedTitle.set(r.from, r.to);
    for (const n of data.query?.normalized ?? []) resolvedTitle.set(n.from, n.to);

    for (const page of data.query?.pages ?? []) {
      if (page.missing) continue;
      const set = accumulated.get(page.title) ?? new Set<string>();
      for (const img of page.images ?? []) {
        set.add(img.title.replace(/^File:/i, ''));
      }
      accumulated.set(page.title, set);
    }
    imcontinue = data.continue?.imcontinue;
  } while (imcontinue);

  const result = new Map<string, string[]>();
  for (const origTitle of titles) {
    const target = resolvedTitle.get(origTitle) ?? origTitle;
    const files = accumulated.get(target);
    if (files) result.set(origTitle, [...files]);
  }
  return result;
}

async function resolveFileUrls(filenames: string[]): Promise<Map<string, string>> {
  const result = new Map<string, string>();
  for (let i = 0; i < filenames.length; i += BATCH_SIZE) {
    await sleep(RATE_LIMIT_MS);
    const batch = filenames.slice(i, i + BATCH_SIZE);
    const params = new URLSearchParams({
      action: 'query',
      titles: batch.map(f => `File:${f}`).join('|'),
      prop: 'imageinfo',
      iiprop: 'url',
      format: 'json',
      formatversion: '2',
    });
    const data = await fetchJson(params) as { query?: { pages?: ImageInfoPage[] } } | null;
    if (!data) continue;
    for (const page of data.query?.pages ?? []) {
      const url = page.imageinfo?.[0]?.url;
      if (url) result.set(page.title.replace(/^File:/i, ''), url);
    }
  }
  return result;
}

export async function fetchWikiImages(items: ItemRef[]): Promise<ImageMap> {
  const result: ImageMap = {};
  const filesByUniqueName = new Map<string, string[]>();

  // ── Step 1: fetch all image filenames per item page (redirect-aware) ───────
  for (let i = 0; i < items.length; i += BATCH_SIZE) {
    const batch = items.slice(i, i + BATCH_SIZE);
    const titleToItem = new Map(batch.map(item => [item.name, item]));
    const pageFileMap = await fetchPageImages(batch.map(b => b.name));

    for (const [origTitle, files] of pageFileMap) {
      const item = titleToItem.get(origTitle);
      if (!item) continue;
      const norm = normName(item.name);
      const relevant = files.filter(f => isRelevantFile(f, norm));
      if (relevant.length > 0) filesByUniqueName.set(item.uniqueName, relevant);
    }

    // Fallback for items with no wiki page: use wikiaThumbnail directly
    for (const item of batch) {
      if (!filesByUniqueName.has(item.uniqueName) && item.wikiaThumbnail) {
        try {
          const raw = new URL(item.wikiaThumbnail).pathname;
          const filename = raw.split('/').find(seg => /\.(png|jpg)$/i.test(seg));
          if (filename) filesByUniqueName.set(item.uniqueName, [filename]);
        } catch { /* invalid url */ }
      }
    }

    const pct = Math.round((i + batch.length) / items.length * 100);
    process.stdout.write(`\r  fetching images... ${pct}% (${i + batch.length}/${items.length})`);
  }
  process.stdout.write('\n');

  // ── Step 2: resolve all unique filenames to CDN URLs ─────────────────────
  const allFiles = [...new Set([...filesByUniqueName.values()].flat())];
  const fileToUrl = await resolveFileUrls(allFiles);

  // ── Step 3: build final map ───────────────────────────────────────────────
  for (const [uniqueName, files] of filesByUniqueName) {
    const images: Record<string, string> = {};
    for (const f of files) {
      const url = fileToUrl.get(f);
      if (url) images[f] = url;
    }
    if (Object.keys(images).length > 0) result[uniqueName] = images;
  }

  return result;
}
