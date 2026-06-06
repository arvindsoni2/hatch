"use client";
import { AGENT_DEFS, type AgentKey } from './agents';
import { HatchIcon } from './HatchIcon';

interface AgentBadgeProps {
  agent: AgentKey;
  size?: number;
  ring?: boolean;
}

export function AgentBadge({ agent, size = 30, ring = false }: AgentBadgeProps) {
  const a = AGENT_DEFS[agent];
  return (
    <span
      style={{
        width: size,
        height: size,
        borderRadius: size * 0.3,
        flexShrink: 0,
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: a.soft,
        color: a.color,
        boxShadow: ring ? `0 0 0 3px ${a.soft}` : 'none',
      }}
    >
      <HatchIcon name={a.icon} size={size * 0.52} color={a.color} strokeWidth={2.1} />
    </span>
  );
}
