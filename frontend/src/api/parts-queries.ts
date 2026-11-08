import { queryOptions } from '@tanstack/react-query';
import { api, ApiError } from './client';
export const serverComponentsQuery = (id: string) => queryOptions({ queryKey: ['fleet', 'server-components', id], queryFn: async () => {
  const data = await api.fleetServerComponents(id);
  if (!Array.isArray(data.components)) throw new ApiError('Invalid server components response.', null, 'invalid_response');
  return data;
}, refetchInterval: api.mode === 'live' ? 1000 : false, retry: false });
export const serverComponentQuery = (id: string, cid: string) => queryOptions({ queryKey: ['fleet', 'server-component', id, cid, 60], queryFn: () => api.fleetServerComponent(id, cid), refetchInterval: api.mode === 'live' ? 1000 : false, retry: false });