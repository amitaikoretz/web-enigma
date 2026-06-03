export const DEFAULT_TRADE_PAGE_SIZE = 25
export const TRADE_PAGE_SIZE_OPTIONS = [10, 25, 50, 100] as const

export const TRADE_PAGE_PARAM = 'trade_page'
export const TRADE_PAGE_SIZE_PARAM = 'trade_page_size'
export const TRADE_SEARCH_PARAM = 'trade_search'

export interface TradeRecordsViewState {
  page: number
  pageSize: number
  search: string
}

function parsePositiveInteger(value: string | null, fallback: number): number {
  if (value === null) {
    return fallback
  }

  const parsed = Number(value)
  if (!Number.isInteger(parsed) || parsed < 1) {
    return fallback
  }

  return parsed
}

export function parseTradeRecordsViewState(searchParams: URLSearchParams): TradeRecordsViewState {
  return {
    page: parsePositiveInteger(searchParams.get(TRADE_PAGE_PARAM), 1),
    pageSize: parseTradePageSize(searchParams.get(TRADE_PAGE_SIZE_PARAM)),
    search: searchParams.get(TRADE_SEARCH_PARAM) ?? '',
  }
}

export function tradeRecordsViewStateToSearchParams(state: TradeRecordsViewState): URLSearchParams {
  const searchParams = new URLSearchParams()

  if (state.page > 1) {
    searchParams.set(TRADE_PAGE_PARAM, String(state.page))
  }
  if (state.pageSize !== DEFAULT_TRADE_PAGE_SIZE) {
    searchParams.set(TRADE_PAGE_SIZE_PARAM, String(state.pageSize))
  }

  const search = state.search.trim()
  if (search.length > 0) {
    searchParams.set(TRADE_SEARCH_PARAM, state.search)
  }

  return searchParams
}

export function parseTradePageSize(value: string | null): number {
  const parsed = parsePositiveInteger(value, DEFAULT_TRADE_PAGE_SIZE)
  return TRADE_PAGE_SIZE_OPTIONS.includes(parsed as (typeof TRADE_PAGE_SIZE_OPTIONS)[number])
    ? parsed
    : DEFAULT_TRADE_PAGE_SIZE
}

