// Fixed agent identity — these colours never change regardless of --accent theme.
export const AGENT_DEFS = {
  scout:  { key: 'scout',  name: 'Scout',  color: '#5b9bff', soft: 'rgba(91,155,255,0.14)',   role: 'Finds roles',      icon: 'compass'  },
  scorer: { key: 'scorer', name: 'Scorer', color: '#b794ff', soft: 'rgba(183,148,255,0.14)',  role: 'Ranks matches',    icon: 'target'   },
  tailor: { key: 'tailor', name: 'Tailor', color: '#3ddc97', soft: 'rgba(61,220,151,0.14)',   role: 'Writes your CV',   icon: 'fileText' },
  coach:  { key: 'coach',  name: 'Coach',  color: '#f5b950', soft: 'rgba(245,185,80,0.14)',   role: 'Preps interviews', icon: 'mic'      },
} as const;

export const PIPELINE = ['scout', 'scorer', 'tailor', 'coach'] as const;
export type AgentKey = keyof typeof AGENT_DEFS;
