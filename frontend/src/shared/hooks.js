import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './api'
import { useToast } from './ui'

export const useGet = (url, opts = {}) =>
  useQuery({ queryKey: [url], queryFn: async () => (await api.get(url)).data, ...opts })

/** Mutation with toast feedback + cache invalidation. fn(vars) -> promise. */
export function useAction(fn, { invalidate = [], success, onSuccess } = {}) {
  const qc = useQueryClient()
  const { toast } = useToast()
  return useMutation({
    mutationFn: fn,
    onSuccess: (data, vars) => {
      invalidate.forEach((k) => qc.invalidateQueries({ queryKey: [k] }))
      if (success) toast(typeof success === 'function' ? success(data) : success)
      onSuccess?.(data, vars)
    },
    onError: (e) => toast.error(e),
  })
}
