import { describe, expect, it } from 'vitest'

import {
  DEFAULT_TRADE_PAGE_SIZE,
  parseTradeRecordsViewState,
  tradeRecordsViewStateToSearchParams,
} from './tradeRecords'

describe('tradeRecords view state helpers', () => {
  it('parses and serializes trade table URL state', () => {
    const state = parseTradeRecordsViewState(
      new URLSearchParams('trade_page=3&trade_page_size=50&trade_search=take_profit'),
    )

    expect(state).toEqual({
      page: 3,
      pageSize: 50,
      search: 'take_profit',
    })
    expect(tradeRecordsViewStateToSearchParams(state).toString()).toBe(
      'trade_page=3&trade_page_size=50&trade_search=take_profit',
    )
  })

  it('falls back to defaults for invalid values and omits default params', () => {
    const state = parseTradeRecordsViewState(new URLSearchParams('trade_page=0&trade_page_size=7'))

    expect(state).toEqual({
      page: 1,
      pageSize: DEFAULT_TRADE_PAGE_SIZE,
      search: '',
    })
    expect(tradeRecordsViewStateToSearchParams(state).toString()).toBe('')
  })
})
