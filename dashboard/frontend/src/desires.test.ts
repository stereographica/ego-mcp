import {
  buildDesireHistoryChartConfig,
  buildDesireHistorySeriesKeys,
  buildDesireRadarSeriesData,
  sortDesireCatalogItems,
} from '@/desires'

describe('desire catalog helpers', () => {
  it('sorts catalog items by maslow level then id', () => {
    expect(
      sortDesireCatalogItems([
        { id: 'zeta', display_name: 'Zeta', maslow_level: 2 },
        { id: 'alpha', display_name: 'Alpha', maslow_level: 1 },
        { id: 'beta', display_name: 'Beta', maslow_level: 1 },
      ]).map((item) => item.id),
    ).toEqual(['alpha', 'beta', 'zeta'])
  })

  it('builds history series keys from catalog first and filters legacy fixed keys', () => {
    const catalog = [
      {
        id: 'information_hunger',
        display_name: 'information hunger',
        maslow_level: 1,
      },
      {
        id: 'social_thirst',
        display_name: 'social thirst',
        maslow_level: 1,
      },
    ]

    expect(
      buildDesireHistorySeriesKeys(catalog, [
        'social_thirst',
        'novelty',
        'cognitive_coherence',
        'momentum',
      ]),
    ).toEqual(['information_hunger', 'social_thirst', 'momentum', 'novelty'])
  })

  it('drops blank discovered keys and deduplicates dynamic series candidates', () => {
    const catalog = [
      {
        id: 'information_hunger',
        display_name: 'information hunger',
        maslow_level: 1,
      },
      {
        id: 'social_thirst',
        display_name: 'social thirst',
        maslow_level: 1,
      },
    ]

    expect(
      buildDesireHistorySeriesKeys(catalog, [
        '',
        'novelty',
        'novelty',
        '  ',
        'cognitive_coherence',
      ]),
    ).toEqual(['information_hunger', 'social_thirst', 'novelty'])
  })

  it('keeps fixed-looking discovered keys visible when the catalog is temporarily empty', () => {
    expect(
      buildDesireHistorySeriesKeys(
        [],
        ['information_hunger', 'social_thirst', 'novelty', ''],
      ),
    ).toEqual(['information_hunger', 'novelty', 'social_thirst'])
  })

  it('builds history chart config with catalog labels and dynamic labels', () => {
    const config = buildDesireHistoryChartConfig(
      [
        {
          id: 'information_hunger',
          display_name: 'information hunger',
          maslow_level: 1,
        },
      ],
      ['information_hunger', 'novelty'],
    )

    expect(config.information_hunger?.label).toBe('information hunger')
    expect(config.novelty?.label).toBe('novelty')
  })

  it('omits legacy fixed keys from history chart configuration', () => {
    const config = buildDesireHistoryChartConfig(
      [
        {
          id: 'information_hunger',
          display_name: 'information hunger',
          maslow_level: 1,
        },
      ],
      ['information_hunger', 'cognitive_coherence', 'novelty'],
    )

    expect(config.information_hunger?.label).toBe('information hunger')
    expect(config.cognitive_coherence).toBeUndefined()
    expect(config.novelty?.label).toBe('novelty')
  })

  it('builds radar series data using catalog items only', () => {
    const radar = buildDesireRadarSeriesData(
      [
        {
          id: 'information_hunger',
          display_name: 'information hunger',
          maslow_level: 1,
        },
        {
          id: 'social_thirst',
          display_name: 'social thirst',
          maslow_level: 1,
        },
      ],
      {
        latest_desires: { information_hunger: 0.8, old_fixed: 0.9 },
        latest_emergent_desires: { novelty: 0.6 },
        latest: { string_metrics: {}, numeric_metrics: {} },
      },
    )

    expect(radar.chartData.map((item) => item.name)).toEqual([
      'information hunger',
      'social thirst',
      'novelty',
    ])
    expect(
      radar.chartData.find((item) => item.name === 'information hunger'),
    ).toMatchObject({ fixed_desires: 0.8 })
    expect(
      radar.chartData.find((item) => item.name === 'novelty'),
    ).toMatchObject({ dynamic_desires: 0.6 })
  })

  it('uses fixed desire payload keys as fallback radar axes when the catalog is empty', () => {
    const legacyFiltered = buildDesireRadarSeriesData([], {
      latest_desires: { predictability: 0.9 },
      latest_emergent_desires: {
        novelty: 0.6,
        predictability: 0.2,
      },
      latest: {
        string_metrics: {},
        numeric_metrics: {},
      },
    })

    expect(legacyFiltered.chartData.map((item) => item.key)).toEqual([
      'predictability',
      'novelty',
    ])
    expect(legacyFiltered.hasDynamicDesires).toBe(true)
    expect(legacyFiltered.boostedDesire).toBeUndefined()
    expect(legacyFiltered.boostAmount).toBeUndefined()

    const emptyRadar = buildDesireRadarSeriesData(
      [
        {
          id: 'information_hunger',
          display_name: 'information hunger',
          maslow_level: 1,
        },
      ],
      null,
    )

    expect(emptyRadar.chartData).toEqual([
      {
        key: 'information_hunger',
        name: 'information hunger',
        fixed_desires: 0,
        dynamic_desires: 0,
        boosted_desire: 0,
      },
    ])
    expect(emptyRadar.hasDynamicDesires).toBe(false)
    expect(emptyRadar.boostedDesire).toBeUndefined()
    expect(emptyRadar.boostAmount).toBeUndefined()
  })

  it('uses latest fixed desires as fallback axes when the catalog has not loaded yet', () => {
    const radar = buildDesireRadarSeriesData([], {
      latest_desires: {
        information_hunger: 0.7,
        social_thirst: 0.5,
      },
      latest_emergent_desires: {
        novelty: 0.6,
      },
      latest: {
        string_metrics: {},
        numeric_metrics: {},
      },
    })

    expect(radar.chartData).toEqual([
      {
        key: 'information_hunger',
        name: 'information hunger',
        fixed_desires: 0.7,
        dynamic_desires: 0,
        boosted_desire: 0,
      },
      {
        key: 'social_thirst',
        name: 'social thirst',
        fixed_desires: 0.5,
        dynamic_desires: 0,
        boosted_desire: 0,
      },
      {
        key: 'novelty',
        name: 'novelty',
        fixed_desires: 0,
        dynamic_desires: 0.6,
        boosted_desire: 0,
      },
    ])
  })
})
