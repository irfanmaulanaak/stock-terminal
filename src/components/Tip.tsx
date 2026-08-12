import { tr } from '../i18n'
import type { Language } from '../types'

export function Tip({ language, label, textKey }: { language: Language; label: string; textKey: string }) {
  const text = tr(language, textKey)
  return <span className="tip-wrap"><span className="tip-label" tabIndex={0} title={text} aria-label={`${label}: ${text}`}>{label}<span className="tip-icon">?</span></span><span className="tip-popup" role="tooltip">{text}</span></span>
}
