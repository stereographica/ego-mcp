import { useEffect, useState } from 'react'

import { fetchDesireCatalog } from '@/api'
import type { DesireCatalogItem } from '@/types'

export const useDesireCatalog = () => {
  const [desireCatalog, setDesireCatalog] = useState<DesireCatalogItem[]>([])

  useEffect(() => {
    let disposed = false

    const loadCatalog = async () => {
      const response = await fetchDesireCatalog()
      if (disposed) return
      setDesireCatalog(response.items)
    }

    void loadCatalog()

    return () => {
      disposed = true
    }
  }, [])

  return desireCatalog
}
