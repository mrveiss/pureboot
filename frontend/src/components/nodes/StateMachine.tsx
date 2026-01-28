import { cn } from '@/lib/utils'
import { NODE_STATE_COLORS, NODE_STATE_LABELS, NODE_STATE_TRANSITIONS, type NodeState } from '@/types'

interface StateMachineProps {
  currentState?: NodeState
  onStateClick?: (state: NodeState) => void
  highlightTransitions?: boolean
  className?: string
}

// Position each state on a virtual grid
const STATE_POSITIONS: Record<NodeState, { x: number; y: number }> = {
  discovered: { x: 50, y: 100 },
  ignored: { x: 50, y: 200 },
  pending: { x: 200, y: 100 },
  installing: { x: 350, y: 100 },
  install_failed: { x: 350, y: 300 },
  installed: { x: 500, y: 100 },
  active: { x: 650, y: 100 },
  reprovision: { x: 350, y: 200 },
  migrating: { x: 650, y: 200 },
  retired: { x: 650, y: 300 },
  decommissioned: { x: 500, y: 400 },
  wiping: { x: 650, y: 400 },
}

const STATE_RADIUS = 40

interface ArrowProps {
  from: NodeState
  to: NodeState
  isHighlighted: boolean
}

function Arrow({ from, to, isHighlighted }: ArrowProps) {
  const fromPos = STATE_POSITIONS[from]
  const toPos = STATE_POSITIONS[to]

  // Calculate direction vector
  const dx = toPos.x - fromPos.x
  const dy = toPos.y - fromPos.y
  const len = Math.sqrt(dx * dx + dy * dy)

  // Normalize and offset by radius
  const nx = dx / len
  const ny = dy / len

  const startX = fromPos.x + nx * STATE_RADIUS
  const startY = fromPos.y + ny * STATE_RADIUS
  const endX = toPos.x - nx * (STATE_RADIUS + 8) // Extra space for arrow head
  const endY = toPos.y - ny * (STATE_RADIUS + 8)

  // Calculate control point for curved arrow (if same row/col)
  const midX = (startX + endX) / 2
  const midY = (startY + endY) / 2

  // Add curve offset for arrows that go backwards
  const curveOffset = dx < 0 || (dx === 0 && dy < 0) ? 30 : 0
  const controlX = midX + ny * curveOffset
  const controlY = midY - nx * curveOffset

  const pathD = curveOffset
    ? `M ${startX} ${startY} Q ${controlX} ${controlY} ${endX} ${endY}`
    : `M ${startX} ${startY} L ${endX} ${endY}`

  return (
    <g>
      <defs>
        <marker
          id={`arrow-${from}-${to}`}
          markerWidth="10"
          markerHeight="7"
          refX="9"
          refY="3.5"
          orient="auto"
        >
          <polygon
            points="0 0, 10 3.5, 0 7"
            fill={isHighlighted ? '#3b82f6' : '#9ca3af'}
          />
        </marker>
      </defs>
      <path
        d={pathD}
        fill="none"
        stroke={isHighlighted ? '#3b82f6' : '#d1d5db'}
        strokeWidth={isHighlighted ? 2 : 1}
        markerEnd={`url(#arrow-${from}-${to})`}
      />
    </g>
  )
}

interface StateNodeProps {
  state: NodeState
  isCurrent: boolean
  isReachable: boolean
  onClick?: () => void
}

function StateNode({ state, isCurrent, isReachable, onClick }: StateNodeProps) {
  const pos = STATE_POSITIONS[state]
  const baseColor = NODE_STATE_COLORS[state].replace('bg-', '')

  // Map Tailwind colors to actual hex values
  const colorMap: Record<string, string> = {
    'blue-500': '#3b82f6',
    'gray-500': '#6b7280',
    'yellow-500': '#eab308',
    'orange-500': '#f97316',
    'teal-500': '#14b8a6',
    'green-500': '#22c55e',
    'purple-500': '#a855f7',
    'indigo-500': '#6366f1',
    'gray-600': '#4b5563',
    'gray-700': '#374151',
    'red-500': '#ef4444',
  }

  const fillColor = isCurrent ? colorMap[baseColor] : (isReachable ? '#e5e7eb' : '#f3f4f6')
  const strokeColor = isCurrent ? colorMap[baseColor] : (isReachable ? '#3b82f6' : '#d1d5db')
  const textColor = isCurrent ? '#ffffff' : '#374151'

  return (
    <g
      className={cn(
        'transition-all',
        onClick && isReachable && 'cursor-pointer hover:opacity-80'
      )}
      onClick={onClick && isReachable ? onClick : undefined}
    >
      <circle
        cx={pos.x}
        cy={pos.y}
        r={STATE_RADIUS}
        fill={fillColor}
        stroke={strokeColor}
        strokeWidth={isCurrent ? 3 : isReachable ? 2 : 1}
        strokeDasharray={isReachable && !isCurrent ? '4 2' : undefined}
      />
      <text
        x={pos.x}
        y={pos.y}
        textAnchor="middle"
        dominantBaseline="middle"
        fill={textColor}
        fontSize="10"
        fontWeight={isCurrent ? 'bold' : 'normal'}
      >
        {NODE_STATE_LABELS[state]}
      </text>
    </g>
  )
}

export function StateMachine({
  currentState,
  onStateClick,
  highlightTransitions = true,
  className,
}: StateMachineProps) {
  const reachableStates = currentState
    ? new Set(NODE_STATE_TRANSITIONS[currentState])
    : new Set<NodeState>()

  const allStates = Object.keys(STATE_POSITIONS) as NodeState[]

  // Generate all arrows
  const arrows: { from: NodeState; to: NodeState }[] = []
  for (const [from, toStates] of Object.entries(NODE_STATE_TRANSITIONS)) {
    for (const to of toStates) {
      arrows.push({ from: from as NodeState, to })
    }
  }

  return (
    <div className={cn('overflow-auto', className)}>
      <svg viewBox="0 0 750 480" className="w-full h-auto min-w-[600px]">
        {/* Render arrows first (behind nodes) */}
        {arrows.map(({ from, to }) => (
          <Arrow
            key={`${from}-${to}`}
            from={from}
            to={to}
            isHighlighted={highlightTransitions && currentState === from}
          />
        ))}

        {/* Render state nodes */}
        {allStates.map((state) => (
          <StateNode
            key={state}
            state={state}
            isCurrent={currentState === state}
            isReachable={reachableStates.has(state)}
            onClick={onStateClick ? () => onStateClick(state) : undefined}
          />
        ))}

        {/* Legend */}
        <g transform="translate(20, 440)">
          <text x="0" y="0" fontSize="10" fill="#6b7280">
            Click a reachable state (dashed border) to transition
          </text>
        </g>
      </svg>
    </div>
  )
}
