import { queryOptions } from '@tanstack/react-query';
import { api } from './client';
export const serverQuery = (id: string) => queryOptions({ queryKey: ['fleet', 'datacenter', 'server', id, 30], queryFn: () => api.fleetServer(id), refetchInterval: 1000 });