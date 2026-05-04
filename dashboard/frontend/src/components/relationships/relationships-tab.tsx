import { useCallback, useEffect, useRef, useState } from 'react'

import { PersonOverviewTable } from '@/components/relationships/person-overview'
import { SurfaceTimeline } from '@/components/relationships/surface-timeline'
import { PersonDetailPanel } from '@/components/relationships/person-detail-panel'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  fetchRelationshipsOverview,
  fetchSurfaceTimeline,
  fetchPersonDetail,
} from '@/api'
import type {
  DateRange,
  PersonDetail,
  PersonOverview,
  SurfaceTimelinePoint,
} from '@/types'

type RelationshipsTabProps = {
  range: DateRange
}

export const RelationshipsTab = ({ range }: RelationshipsTabProps) => {
  const [persons, setPersons] = useState<PersonOverview[]>([])
  const [isLoadingPersons, setIsLoadingPersons] = useState(true)

  const [points, setPoints] = useState<SurfaceTimelinePoint[]>([])
  const [isLoadingPoints, setIsLoadingPoints] = useState(true)

  const [selectedPerson, setSelectedPerson] = useState<string | null>(null)
  const [detail, setDetail] = useState<PersonDetail | null>(null)

  const detailRequestIdRef = useRef(0)

  useEffect(() => {
    setIsLoadingPersons(true)
    fetchRelationshipsOverview().then((res) => {
      setPersons(res.items)
      setIsLoadingPersons(false)
    })
  }, [])

  useEffect(() => {
    setIsLoadingPoints(true)
    fetchSurfaceTimeline(range).then((res) => {
      setPoints(res.items)
      setIsLoadingPoints(false)
    })
  }, [range])

  const handleSelectPerson = useCallback((personId: string) => {
    setSelectedPerson(personId)
    setDetail(null)
  }, [])

  useEffect(() => {
    if (!selectedPerson) {
      setDetail(null)
      return
    }
    const requestId = ++detailRequestIdRef.current
    fetchPersonDetail(selectedPerson, range).then((res) => {
      if (requestId === detailRequestIdRef.current) {
        setDetail(res)
      }
    })
  }, [selectedPerson, range])

  const handleCloseDetail = useCallback(() => {
    setSelectedPerson(null)
    setDetail(null)
  }, [])

  return (
    <div className="min-w-0 space-y-4">
      <Card className="min-w-0 overflow-hidden">
        <CardHeader>
          <CardTitle className="text-sm">Person overview</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <PersonOverviewTable
            persons={persons}
            isLoading={isLoadingPersons}
            onSelect={handleSelectPerson}
          />
        </CardContent>
      </Card>

      <div className="min-w-0">
        <SurfaceTimeline
          points={points}
          isLoading={isLoadingPoints}
          persons={persons}
        />
      </div>

      {selectedPerson && detail && (
        <div className="min-w-0">
          <PersonDetailPanel detail={detail} onClose={handleCloseDetail} />
        </div>
      )}
    </div>
  )
}
