import type { ApiClient } from './client';
import { ApiError } from './client';
import type { Asset } from './types';
/** Fetch every page before presenting compatible options. No partial list on failure. */
export async function listAllAssets(client: ApiClient): Promise<Asset[]> {
  if (client.mode === 'fixture') return (await client.listAssets()).items;
  const items: Asset[] = [];
  let offset = 0;
  let target: number | undefined;
  do {
    const page = await client.listAssets({ limit: 200, offset });
    target ??= page.total;
    if (page.offset !== offset || !Number.isSafeInteger(page.total) || page.total < 0 || (page.items.length === 0 && offset < target)) {
      throw new ApiError('Asset pagination did not advance. Compatible assets could not be loaded completely.', null, 'INVALID_PAGINATION');
    }
    items.push(...page.items);
    offset += page.items.length;
  } while (offset < target);
  return items;
}