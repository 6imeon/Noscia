// The active vertical, shared across the app (MULTI_INDUSTRY.md Phase C). Search,
// Structured, and Corpus all read it from context rather than prop-drilling through the
// OutputPane tab chrome. App owns the state; this is just the read seam + the localStorage
// key that lets a returning user skip the setup gate.
import { createContext, useContext } from 'react'
import { DEFAULT_INDUSTRY, type Industry } from '../lib/api'

export const INDUSTRY_KEY = 'noscia.industry' // localStorage fast-path (server pref is source of truth)

export interface IndustryCtx {
  activeIndustry: string
  industries: Industry[]
  openPicker: () => void // re-open the setup/switcher (the Rail-header control)
}

const Ctx = createContext<IndustryCtx>({
  activeIndustry: DEFAULT_INDUSTRY,
  industries: [],
  openPicker: () => {},
})

export const IndustryProvider = Ctx.Provider
export const useIndustry = (): IndustryCtx => useContext(Ctx)
