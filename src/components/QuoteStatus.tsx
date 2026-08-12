import { tr } from '../i18n'
import type { Language, QuoteState } from '../types'
import { formatDate } from '../utils'

export function QuoteStatus({ language, quoteState, lastRefresh, quoteError }: { language: Language; quoteState: QuoteState; lastRefresh: string | null; quoteError: string }) {
  return <div className="quote-status">
    <span className={`status-dot ${quoteState === 'ready' ? 'green' : quoteState === 'error' ? 'amber' : ''}`} />
    <span>{quoteState === 'ready' ? `${tr(language, 'liveQuotes')} · ${formatDate(lastRefresh)}` : quoteState === 'loading' ? `${tr(language, 'liveQuotes')}...` : quoteError || tr(language, 'pending')}</span>
  </div>
}
