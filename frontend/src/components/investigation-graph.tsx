import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import ForceGraph2D, {
  type ForceGraphMethods,
  type NodeObject,
  type LinkObject,
} from 'react-force-graph-2d'
import { forceCollide } from 'd3-force-3d'
import {
  AlertTriangle,
  Eye,
  EyeOff,
  Info,
  Maximize2,
  Minimize2,
  Scan,
  X,
  ZoomIn,
  ZoomOut,
} from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { cn } from '@/lib/utils'

// ── Types ──

interface GraphNode {
  id: string
  type: 'seed' | 'account' | 'discovery'
  label: string
  platform?: string | null
  identifier_type?: string
  display_name?: string | null
  bio?: string | null
  location?: string | null
  avatar?: string | null
  url?: string | null
  category?: string
  follower_count?: number | null
  following_count?: number | null
  size: number
}

interface GraphEdge {
  source: string
  target: string
  type: string
  label: string
  confidence: number
  band?: string
  evidence_class: string
  evidence_type?: string
  shap?: Record<string, unknown>
  tier1_links?: string[]
  detail?: string
  platform?: string
}

interface GraphStats {
  total_nodes: number
  total_edges: number
  seeds: number
  accounts: number
  discoveries: number
  hard_links: number
  correlations: number
  network_edges: number
  mutual_connections: number
  mutual_total_shared: number
}

interface GraphData {
  nodes: GraphNode[]
  edges: GraphEdge[]
  stats: GraphStats
}

interface InvestigationGraphProps {
  caseId: string
  apiBase: string
}

// ── Platform colors ──

const PLATFORM_COLORS: Record<string, string> = {
  reddit: '#FF4500',
  twitter: '#1DA1F2',
  github: '#8B5CF6',
  instagram: '#E1306C',
  telegram: '#0088CC',
  whatsapp: '#25D366',
  gravatar: '#1E8CBE',
  facebook: '#1877F2',
  youtube: '#FF0000',
  linkedin: '#0A66C2',
  default: '#6B7280',
}

const NODE_TYPE_COLORS: Record<string, string> = {
  seed: '#F59E0B',
  account: '#3B82F6',
  discovery: '#6B7280',
}

const EDGE_CLASS_COLORS: Record<string, string> = {
  hard_link: '#10B981',
  deterministic: '#10B981',
  probabilistic: '#F59E0B',
  network: '#8B5CF6',
  behavioral: '#EC4899',
  discovery: '#6B7280',
}

const EDGE_DASH: Record<string, number[] | undefined> = {
  hard_link: undefined,
  deterministic: undefined,
  probabilistic: [5, 3],
  network: [2, 2],
  behavioral: [8, 4],
  discovery: [3, 6],
}

const EDGE_CLASS_LABELS: Record<string, string> = {
  hard_link: 'Hard Links',
  deterministic: 'Hard Links',
  probabilistic: 'Correlations',
  network: 'Network',
  behavioral: 'Behavioral',
  discovery: 'Discoveries',
}

const EVIDENCE_PRIORITY: Record<string, number> = {
  hard_link: 6,
  deterministic: 5,
  probabilistic: 4,
  behavioral: 3,
  network: 2,
  discovery: 1,
}

const DEFAULT_HEIGHT = 700
const FULLSCREEN_OFFSET = 120

// ── Component ──

export function InvestigationGraph({ caseId, apiBase }: InvestigationGraphProps) {
  const graphRef = useRef<ForceGraphMethods<NodeObject<GraphNode>>>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [graphData, setGraphData] = useState<GraphData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null)
  const [selectedEdge, setSelectedEdge] = useState<GraphEdge | null>(null)
  const [dimensions, setDimensions] = useState({ width: 800, height: DEFAULT_HEIGHT })
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [showDiscoveries, setShowDiscoveries] = useState(true)
  const [visibleEdgeClasses, setVisibleEdgeClasses] = useState<Set<string>>(
    new Set(['hard_link', 'deterministic', 'probabilistic', 'network', 'behavioral', 'discovery'])
  )
  const [highlightNodes, setHighlightNodes] = useState<Set<string>>(new Set())
  const [highlightEdges, setHighlightEdges] = useState<Set<string>>(new Set())
  const [hoverNode, setHoverNode] = useState<string | null>(null)
  const didFitRef = useRef(false)
  const hoverTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const graphHeight = isFullscreen ? window.innerHeight - FULLSCREEN_OFFSET : DEFAULT_HEIGHT

  useEffect(() => {
    setLoading(true)
    fetch(`${apiBase}/api/cases/${caseId}/graph`, { credentials: 'include' })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then((data: GraphData) => {
        setGraphData(data)
        setError(null)
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [caseId, apiBase])

  // Configure force simulation — scales with node count
  useEffect(() => {
    if (!graphRef.current || !graphData) return
    const fg = graphRef.current
    const nodeCount = graphData.nodes.length

    // Strong repulsion — scales aggressively with node count to prevent clumping
    const baseCharge = -400
    const perNodeCharge = -30
    fg.d3Force('charge')?.strength((node: any) => {
      const n = node as GraphNode
      const multiplier = n.type === 'seed' ? 2 : n.type === 'discovery' ? 0.5 : 1
      return (baseCharge + nodeCount * perNodeCharge) * multiplier
    })

    // Link distance: hard links short, weak links long, scales with graph size
    fg.d3Force('link')?.distance((link: any) => {
      const confidence = link.confidence || 0.3
      const base = 80 + nodeCount * 4
      return base + (1 - confidence) * 120
    })

    // Collision detection — radius includes label space below node
    fg.d3Force('collide', forceCollide((node: any) => {
      return (node as GraphNode).size + 28
    }).strength(0.9).iterations(3))

    // Weaker centering so graph can spread
    fg.d3Force('center')?.strength(0.03)

    fg.d3ReheatSimulation()
  }, [graphData])

  // Auto-fit after initial layout stabilizes
  useEffect(() => {
    if (!graphData || didFitRef.current) return
    const timer = setTimeout(() => {
      graphRef.current?.zoomToFit(400, 60)
      didFitRef.current = true
    }, 1500)
    return () => clearTimeout(timer)
  }, [graphData])

  // Resize observer
  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setDimensions({
          width: entry.contentRect.width,
          height: Math.max(entry.contentRect.height, DEFAULT_HEIGHT),
        })
      }
    })
    observer.observe(container)
    return () => observer.disconnect()
  }, [])

  // Filter nodes & edges, consolidate parallel edges between same node pair
  const filteredData = useMemo(() => {
    if (!graphData) return { nodes: [], links: [] }

    const visibleNodes = showDiscoveries
      ? graphData.nodes
      : graphData.nodes.filter((n) => n.type !== 'discovery')

    const visibleIds = new Set(visibleNodes.map((n) => n.id))

    const rawLinks = graphData.edges.filter((e) => {
      if (!visibleIds.has(e.source) || !visibleIds.has(e.target)) return false
      return visibleEdgeClasses.has(e.evidence_class)
    })

    const pairMap = new Map<string, GraphEdge[]>()
    for (const edge of rawLinks) {
      const key = [edge.source, edge.target].sort().join('|')
      if (!pairMap.has(key)) pairMap.set(key, [])
      pairMap.get(key)!.push(edge)
    }

    const links = [...pairMap.values()].map((group) => {
      const sorted = [...group].sort(
        (a, b) => (EVIDENCE_PRIORITY[b.evidence_class] || 0) - (EVIDENCE_PRIORITY[a.evidence_class] || 0)
      )
      const best = sorted[0]
      return {
        ...best,
        source: best.source,
        target: best.target,
        confidence: Math.max(...group.map((e) => e.confidence)),
        _subEdges: group,
      }
    })

    return { nodes: [...visibleNodes], links }
  }, [graphData, showDiscoveries, visibleEdgeClasses])

  // Node interactions — delayed clear so cursor can reach the dossier panel
  const clearHoverState = useCallback(() => {
    setHighlightNodes(new Set())
    setHighlightEdges(new Set())
    setHoverNode(null)
  }, [])

  const cancelHoverTimeout = useCallback(() => {
    if (hoverTimeoutRef.current) {
      clearTimeout(hoverTimeoutRef.current)
      hoverTimeoutRef.current = null
    }
  }, [])

  const startHoverTimeout = useCallback(() => {
    cancelHoverTimeout()
    hoverTimeoutRef.current = setTimeout(clearHoverState, 300)
  }, [cancelHoverTimeout, clearHoverState])

  const handleNodeHover = useCallback(
    (node: NodeObject<GraphNode> | null) => {
      cancelHoverTimeout()

      if (!node) {
        startHoverTimeout()
        return
      }
      const nid = node.id as string
      setHoverNode(nid)
      const connectedNodes = new Set<string>([nid])
      const connectedEdges = new Set<string>()

      filteredData.links.forEach((link, i) => {
        const src = typeof link.source === 'object' ? (link.source as any).id : link.source
        const tgt = typeof link.target === 'object' ? (link.target as any).id : link.target
        if (src === nid || tgt === nid) {
          connectedNodes.add(src)
          connectedNodes.add(tgt)
          connectedEdges.add(`${i}`)
        }
      })
      setHighlightNodes(connectedNodes)
      setHighlightEdges(connectedEdges)
    },
    [filteredData.links, cancelHoverTimeout, startHoverTimeout]
  )

  const handleNodeClick = useCallback(
    (node: NodeObject<GraphNode>) => {
      setSelectedEdge(null)
      setSelectedNode(node as unknown as GraphNode)
      graphRef.current?.centerAt(node.x, node.y, 500)
      graphRef.current?.zoom(2, 500)
    },
    []
  )

  const handleLinkClick = useCallback(
    (link: LinkObject) => {
      setSelectedNode(null)
      setSelectedEdge(link as unknown as GraphEdge)
    },
    []
  )

  const toggleEdgeClass = (cls: string) => {
    setVisibleEdgeClasses((prev) => {
      const next = new Set(prev)
      if (next.has(cls)) next.delete(cls)
      else next.add(cls)
      return next
    })
  }

  // Dossier data — deduplicated, with clean separation of edge types
  const dossierData = useMemo(() => {
    if (!hoverNode || !graphData) return null
    const node = graphData.nodes.find((n) => n.id === hoverNode)
    if (!node) return null

    const connections: Array<{
      otherId: string
      otherLabel: string
      otherPlatform: string | null
      otherType: string
      edges: GraphEdge[]
    }> = []

    const seen = new Map<string, number>()
    for (const edge of graphData.edges) {
      const src = typeof edge.source === 'object' ? (edge.source as any).id : edge.source
      const tgt = typeof edge.target === 'object' ? (edge.target as any).id : edge.target
      if (src !== hoverNode && tgt !== hoverNode) continue

      const otherId = src === hoverNode ? tgt : src
      const idx = seen.get(otherId)
      if (idx != null) {
        connections[idx].edges.push(edge)
      } else {
        const otherNode = graphData.nodes.find((n) => n.id === otherId)
        seen.set(otherId, connections.length)
        connections.push({
          otherId,
          otherLabel: otherNode?.label || otherId,
          otherPlatform: otherNode?.platform || null,
          otherType: otherNode?.type || 'account',
          edges: [edge],
        })
      }
    }

    // Deduplicate edges per connection: same type+label = keep one
    for (const conn of connections) {
      const dedupMap = new Map<string, GraphEdge>()
      for (const edge of conn.edges) {
        const key = `${edge.type}|${edge.label}`
        if (!dedupMap.has(key)) dedupMap.set(key, edge)
      }
      conn.edges = [...dedupMap.values()]
    }

    connections.sort((a, b) => {
      const maxA = Math.max(...a.edges.map((e) => e.confidence))
      const maxB = Math.max(...b.edges.map((e) => e.confidence))
      return maxB - maxA
    })

    return { node, connections }
  }, [hoverNode, graphData])

  // Custom node rendering — always-visible, readable labels, strong dim on non-connected
  const drawNode = useCallback(
    (node: NodeObject<GraphNode>, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const n = node as unknown as GraphNode & { x: number; y: number }
      const size = n.size || 8
      const hovering = highlightNodes.size > 0
      const isHighlighted = !hovering || highlightNodes.has(n.id)
      const isHovered = hoverNode === n.id
      // When hovering: connected=1.0, non-connected=0.04 (nearly invisible)
      const opacity = hovering ? (isHighlighted ? 1 : 0.04) : 1

      ctx.save()
      ctx.globalAlpha = opacity

      const nodeColor = n.type === 'seed'
        ? NODE_TYPE_COLORS.seed
        : n.type === 'discovery'
          ? NODE_TYPE_COLORS.discovery
          : PLATFORM_COLORS[n.platform || 'default'] || PLATFORM_COLORS.default

      // Hover glow ring
      if (isHovered) {
        ctx.beginPath()
        ctx.arc(n.x, n.y, size + 10, 0, 2 * Math.PI)
        ctx.fillStyle = nodeColor
        ctx.globalAlpha = 0.2
        ctx.fill()
        ctx.globalAlpha = opacity
      }

      // Outer ring for seeds
      if (n.type === 'seed') {
        ctx.beginPath()
        ctx.arc(n.x, n.y, size + 4, 0, 2 * Math.PI)
        ctx.strokeStyle = NODE_TYPE_COLORS.seed
        ctx.lineWidth = 2.5
        ctx.stroke()
      }

      // Node circle
      ctx.beginPath()
      ctx.arc(n.x, n.y, size, 0, 2 * Math.PI)
      ctx.fillStyle = nodeColor
      if (n.type === 'discovery') {
        ctx.setLineDash([2, 2])
        ctx.strokeStyle = '#9CA3AF'
        ctx.lineWidth = 1
        ctx.stroke()
        ctx.setLineDash([])
      }
      ctx.fill()

      // Platform icon letter
      const iconSize = Math.max(size * 0.9, 5)
      ctx.font = `bold ${iconSize}px Inter, system-ui, sans-serif`
      ctx.textAlign = 'center'
      ctx.textBaseline = 'middle'
      ctx.fillStyle = '#FFFFFF'
      const icon = n.type === 'seed'
        ? '◎'
        : n.platform
          ? n.platform.charAt(0).toUpperCase()
          : '?'
      ctx.fillText(icon, n.x, n.y)

      // Label — always visible, bigger font, dark pill background
      const label = n.label || ''
      const maxLen = globalScale > 1.2 ? 28 : 22
      const truncated = label.length > maxLen ? label.slice(0, maxLen - 1) + '…' : label
      const labelSize = Math.max(5, Math.min(14, 13 / globalScale))
      ctx.font = `600 ${labelSize}px Inter, system-ui, sans-serif`
      const textWidth = ctx.measureText(truncated).width
      const labelY = n.y + size + labelSize + 4

      // Background rounded-rect pill
      const pillPadX = 4
      const pillPadY = 2
      const pillW = textWidth + pillPadX * 2
      const pillH = labelSize + pillPadY * 2
      const pillR = pillH / 2
      ctx.fillStyle = isHighlighted ? 'rgba(0, 0, 0, 0.8)' : 'rgba(0, 0, 0, 0.4)'
      ctx.beginPath()
      ctx.moveTo(n.x - pillW / 2 + pillR, labelY - pillH / 2)
      ctx.lineTo(n.x + pillW / 2 - pillR, labelY - pillH / 2)
      ctx.arc(n.x + pillW / 2 - pillR, labelY, pillR, -Math.PI / 2, Math.PI / 2)
      ctx.lineTo(n.x - pillW / 2 + pillR, labelY + pillH / 2)
      ctx.arc(n.x - pillW / 2 + pillR, labelY, pillR, Math.PI / 2, -Math.PI / 2)
      ctx.closePath()
      ctx.fill()

      // Label text
      ctx.textAlign = 'center'
      ctx.textBaseline = 'middle'
      ctx.fillStyle = isHighlighted ? '#FFFFFF' : '#9CA3AF'
      ctx.fillText(truncated, n.x, labelY)

      ctx.restore()
    },
    [highlightNodes, hoverNode]
  )

  // Custom link rendering — clean single line per node pair, no floating labels
  const drawLink = useCallback(
    (link: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const edge = link as GraphEdge & { source: { x: number; y: number }; target: { x: number; y: number }; _subEdges?: GraphEdge[] }
      if (!edge.source || !edge.target) return

      const src = edge.source as any
      const tgt = edge.target as any
      if (!src.x || !tgt.x) return

      const linkIdx = filteredData.links.indexOf(link)
      const hovering = highlightEdges.size > 0
      const isHighlighted = !hovering || highlightEdges.has(`${linkIdx}`)
      const opacity = hovering ? (isHighlighted ? 0.9 : 0.02) : 0.5

      const color = EDGE_CLASS_COLORS[edge.evidence_class] || '#6B7280'
      const dash = EDGE_DASH[edge.evidence_class]
      const subCount = edge._subEdges?.length || 1
      const baseWidth = Math.max(1, (edge.confidence || 0.3) * 4)
      const width = baseWidth + Math.min(subCount - 1, 3) * 0.5

      ctx.save()
      ctx.globalAlpha = opacity
      ctx.strokeStyle = color
      ctx.lineWidth = isHighlighted ? width / globalScale : (width * 0.5) / globalScale

      if (dash) ctx.setLineDash(dash.map((d) => d / globalScale))
      else ctx.setLineDash([])

      const midX = (src.x + tgt.x) / 2
      const midY = (src.y + tgt.y) / 2
      const dx = tgt.x - src.x
      const dy = tgt.y - src.y
      const dist = Math.sqrt(dx * dx + dy * dy) || 1
      const normX = dy / dist
      const normY = -(dx / dist)
      const curveOffset = 12
      const cpX = midX + normX * curveOffset
      const cpY = midY + normY * curveOffset

      ctx.beginPath()
      ctx.moveTo(src.x, src.y)
      ctx.quadraticCurveTo(cpX, cpY, tgt.x, tgt.y)
      ctx.stroke()
      ctx.setLineDash([])

      // Small count badge on hover for consolidated edges
      if (isHighlighted && hovering && subCount > 1) {
        const badgeX = (src.x + 2 * cpX + tgt.x) / 4
        const badgeY = (src.y + 2 * cpY + tgt.y) / 4
        const badgeR = 8 / globalScale
        ctx.globalAlpha = 0.9
        ctx.fillStyle = '#1a1a2e'
        ctx.beginPath()
        ctx.arc(badgeX, badgeY, badgeR, 0, 2 * Math.PI)
        ctx.fill()
        ctx.strokeStyle = color
        ctx.lineWidth = 1 / globalScale
        ctx.stroke()
        ctx.fillStyle = color
        ctx.font = `bold ${Math.max(4, 9 / globalScale)}px Inter, system-ui, sans-serif`
        ctx.textAlign = 'center'
        ctx.textBaseline = 'middle'
        ctx.fillText(`${subCount}`, badgeX, badgeY)
      }

      ctx.restore()
    },
    [highlightEdges, filteredData.links]
  )

  // Controls
  const handleZoomIn = () => graphRef.current?.zoom(graphRef.current.zoom() * 1.5, 300)
  const handleZoomOut = () => graphRef.current?.zoom(graphRef.current.zoom() / 1.5, 300)
  const handleFit = () => graphRef.current?.zoomToFit(400, 60)

  if (loading) {
    return (
      <Card>
        <CardContent className='flex items-center justify-center py-20'>
          <div className='flex flex-col items-center gap-3'>
            <div className='h-8 w-8 animate-spin rounded-full border-2 border-primary border-t-transparent' />
            <p className='text-sm text-muted-foreground'>Building investigation graph…</p>
          </div>
        </CardContent>
      </Card>
    )
  }

  if (error) {
    return (
      <Card>
        <CardContent className='flex items-center justify-center py-20'>
          <div className='flex flex-col items-center gap-3 text-destructive'>
            <AlertTriangle className='h-8 w-8' />
            <p className='text-sm'>Failed to load graph: {error}</p>
          </div>
        </CardContent>
      </Card>
    )
  }

  if (!graphData || graphData.nodes.length === 0) {
    return (
      <Card>
        <CardContent className='flex items-center justify-center py-20'>
          <div className='flex flex-col items-center gap-3 text-muted-foreground'>
            <Info className='h-8 w-8' />
            <p className='text-sm'>No graph data yet. Run an investigation first.</p>
          </div>
        </CardContent>
      </Card>
    )
  }

  // Collect distinct edge classes present in data for filter buttons
  const edgeClassesPresent = [...new Set(graphData.edges.map((e) => e.evidence_class))]

  return (
    <div className='flex flex-col gap-4'>
      {/* ── Stats Bar ── */}
      <div className='flex flex-wrap items-center gap-2'>
        <Badge variant='outline' className='gap-1'>
          <span className='h-2 w-2 rounded-full bg-amber-500' />
          {graphData.stats.seeds} seeds
        </Badge>
        <Badge variant='outline' className='gap-1'>
          <span className='h-2 w-2 rounded-full bg-blue-500' />
          {graphData.stats.accounts} accounts
        </Badge>
        {graphData.stats.discoveries > 0 && (
          <Badge variant='outline' className='gap-1'>
            <span className='h-2 w-2 rounded-full bg-gray-500' />
            {graphData.stats.discoveries} discoveries
          </Badge>
        )}
        <Badge variant='outline' className='gap-1'>
          <span className='h-2 w-2 rounded-full bg-green-500' />
          {graphData.stats.hard_links} hard links
        </Badge>
        <Badge variant='outline' className='gap-1'>
          <span className='h-2 w-2 rounded-full bg-yellow-500' />
          {graphData.stats.correlations} correlations
        </Badge>
        {graphData.stats.network_edges > 0 && (
          <Badge variant='outline' className='gap-1'>
            <span className='h-2 w-2 rounded-full bg-purple-500' />
            {graphData.stats.network_edges} network
          </Badge>
        )}
        {graphData.stats.mutual_total_shared > 0 && (
          <Badge variant='outline' className='gap-1'>
            <span className='h-2 w-2 rounded-full bg-cyan-500' />
            {graphData.stats.mutual_total_shared} mutuals
          </Badge>
        )}
      </div>

      {/* ── Graph Canvas ── */}
      <Card className={cn('relative overflow-hidden', isFullscreen && 'fixed inset-0 z-50 rounded-none border-0')}>
        {/* Zoom controls — top left */}
        <div className='absolute left-3 top-3 z-10 flex flex-col gap-1'>
          <Button size='icon' variant='secondary' className='h-8 w-8' onClick={handleZoomIn} title='Zoom in'>
            <ZoomIn className='h-4 w-4' />
          </Button>
          <Button size='icon' variant='secondary' className='h-8 w-8' onClick={handleZoomOut} title='Zoom out'>
            <ZoomOut className='h-4 w-4' />
          </Button>
          <Button size='icon' variant='secondary' className='h-8 w-8' onClick={handleFit} title='Fit to view'>
            <Scan className='h-4 w-4' />
          </Button>
          <Button
            size='icon'
            variant='secondary'
            className='h-8 w-8'
            onClick={() => setIsFullscreen(!isFullscreen)}
            title={isFullscreen ? 'Exit fullscreen' : 'Fullscreen'}
          >
            {isFullscreen ? <Minimize2 className='h-4 w-4' /> : <Maximize2 className='h-4 w-4' />}
          </Button>
        </div>

        {/* Filter toggles — top right */}
        <div className='absolute right-3 top-3 z-10 flex flex-wrap gap-1'>
          <Button
            size='sm'
            variant={showDiscoveries ? 'secondary' : 'ghost'}
            className='h-7 gap-1 text-xs'
            onClick={() => setShowDiscoveries(!showDiscoveries)}
          >
            {showDiscoveries ? <Eye className='h-3 w-3' /> : <EyeOff className='h-3 w-3' />}
            Discoveries
          </Button>
          {edgeClassesPresent.map((cls) => {
            const active = visibleEdgeClasses.has(cls)
            const color = EDGE_CLASS_COLORS[cls] || '#6B7280'
            return (
              <Button
                key={cls}
                size='sm'
                variant={active ? 'secondary' : 'ghost'}
                className='h-7 gap-1 text-xs'
                onClick={() => toggleEdgeClass(cls)}
              >
                <span className='h-2 w-2 rounded-full' style={{ backgroundColor: active ? color : '#6B7280' }} />
                {EDGE_CLASS_LABELS[cls] || cls}
              </Button>
            )
          })}
        </div>

        {/* Legend — bottom left */}
        <div className='absolute bottom-3 left-3 z-10 rounded-lg bg-background/90 p-2.5 text-xs shadow-lg backdrop-blur-sm'>
          <div className='flex flex-col gap-1.5'>
            <div className='flex items-center gap-2'>
              <span className='inline-block h-2.5 w-5 rounded-sm bg-green-500' />
              <span>Hard link</span>
            </div>
            <div className='flex items-center gap-2'>
              <span className='inline-block h-2.5 w-5 rounded-sm bg-yellow-500' style={{ opacity: 0.7 }} />
              <span>Correlation</span>
            </div>
            <div className='flex items-center gap-2'>
              <span className='inline-block h-2.5 w-5 rounded-sm bg-purple-500' style={{ opacity: 0.7 }} />
              <span>Network</span>
            </div>
            <div className='flex items-center gap-2'>
              <span className='inline-block h-2.5 w-5 rounded-sm bg-gray-500' style={{ opacity: 0.5 }} />
              <span>Discovery</span>
            </div>
            <hr className='border-border' />
            <div className='flex items-center gap-2'>
              <span className='flex h-5 w-5 items-center justify-center rounded-full bg-amber-500 text-[8px] font-bold text-white'>◎</span>
              <span>Seed</span>
            </div>
            <div className='flex items-center gap-2'>
              <span className='flex h-5 w-5 items-center justify-center rounded-full bg-blue-500 text-[8px] font-bold text-white'>A</span>
              <span>Account</span>
            </div>
          </div>
        </div>

        {/* Hint — bottom right */}
        <div className='absolute bottom-3 right-3 z-10 rounded-lg bg-background/80 px-2.5 py-1.5 text-[11px] text-muted-foreground backdrop-blur-sm'>
          Hover a node to inspect connections
        </div>

        {/* Dossier overlay panel — top right corner */}
        {dossierData && (
          <div
            className='absolute right-3 top-14 z-20 flex w-80 max-h-[65%] flex-col overflow-hidden rounded-xl border border-border/50 bg-background/90 shadow-2xl backdrop-blur-md'
            onMouseEnter={cancelHoverTimeout}
            onMouseLeave={startHoverTimeout}
          >
            {/* Header */}
            <div className='flex items-center gap-3 border-b border-border/30 bg-background/95 px-4 py-3 backdrop-blur-sm'>
              <div
                className='flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-sm font-bold text-white'
                style={{
                  backgroundColor:
                    dossierData.node.type === 'seed'
                      ? NODE_TYPE_COLORS.seed
                      : PLATFORM_COLORS[dossierData.node.platform || 'default'] || PLATFORM_COLORS.default,
                }}
              >
                {dossierData.node.type === 'seed'
                  ? '◎'
                  : (dossierData.node.platform || '?').charAt(0).toUpperCase()}
              </div>
              <div className='min-w-0 flex-1'>
                <p className='truncate text-sm font-semibold'>{dossierData.node.label}</p>
                <p className='text-[11px] text-muted-foreground'>
                  {dossierData.node.type === 'seed'
                    ? `Seed (${dossierData.node.identifier_type})`
                    : capitalize(dossierData.node.platform || 'Account')}
                  {dossierData.node.display_name && ` · ${dossierData.node.display_name}`}
                </p>
              </div>
            </div>

            {/* Connection list */}
            <div className='flex-1 overflow-y-auto'>
              {dossierData.connections.length === 0 ? (
                <div className='px-4 py-6 text-center text-xs text-muted-foreground'>No connections</div>
              ) : (
                <div className='divide-y divide-border/20 px-4'>
                  {dossierData.connections.map((conn) => {
                    const networkEdges = conn.edges.filter(
                      (e) => e.type === 'network' || e.type === 'seed_to_account'
                    )
                    const mutualEdges = conn.edges.filter((e) => e.type === 'mutual_network')
                    const analyticsEdges = conn.edges.filter(
                      (e) => e.type !== 'network' && e.type !== 'seed_to_account' && e.type !== 'mutual_network'
                    )

                    return (
                      <div key={conn.otherId} className='py-2.5'>
                        <div className='flex items-center gap-2'>
                          <div
                            className='flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[9px] font-bold text-white'
                            style={{
                              backgroundColor:
                                conn.otherType === 'seed'
                                  ? NODE_TYPE_COLORS.seed
                                  : PLATFORM_COLORS[conn.otherPlatform || 'default'] || PLATFORM_COLORS.default,
                            }}
                          >
                            {conn.otherType === 'seed'
                              ? '◎'
                              : (conn.otherPlatform || '?').charAt(0).toUpperCase()}
                          </div>
                          <span className='truncate text-xs font-medium'>{conn.otherLabel}</span>
                        </div>

                        <div className='mt-1.5 space-y-1 pl-7'>
                          {/* Network edges — directional follow indicators */}
                          {networkEdges.length > 0 && (() => {
                            const outgoing: string[] = []
                            const incoming: string[] = []
                            for (const edge of networkEdges) {
                              const src = typeof edge.source === 'object' ? (edge.source as any).id : edge.source
                              const isOut = src === hoverNode
                                ? edge.label === 'follows'
                                : edge.label !== 'follows'
                              if (isOut) outgoing.push(edge.platform || '')
                              else incoming.push(edge.platform || '')
                            }
                            const isMutual = outgoing.length > 0 && incoming.length > 0

                            return (
                              <div className='flex flex-wrap items-center gap-1.5 text-[11px]'>
                                {isMutual ? (
                                  <span className='inline-flex items-center gap-1 rounded-full bg-purple-500/20 px-2 py-0.5 font-medium text-purple-400'>
                                    ↔ mutual follow
                                  </span>
                                ) : (
                                  <>
                                    {outgoing.length > 0 && (
                                      <span className='inline-flex items-center gap-1 rounded-full bg-purple-500/15 px-2 py-0.5 text-purple-400'>
                                        → {dossierData.node.label} follows {conn.otherLabel}
                                      </span>
                                    )}
                                    {incoming.length > 0 && (
                                      <span className='inline-flex items-center gap-1 rounded-full bg-purple-500/15 px-2 py-0.5 text-purple-400'>
                                        ← {conn.otherLabel} follows {dossierData.node.label}
                                      </span>
                                    )}
                                  </>
                                )}
                              </div>
                            )
                          })()}

                          {/* Mutual network edges — show actual shared count + Jaccard */}
                          {mutualEdges.map((edge, i) => {
                            const e = edge as any
                            const sharedCount: number = e.shared_count ?? e.mutual_usernames?.length ?? 0
                            const jaccard: number | null = e.jaccard ?? null
                            return (
                              <div key={`m${i}`} className='flex items-center gap-2 text-[11px]'>
                                <span
                                  className='h-2 w-2 shrink-0 rounded-full'
                                  style={{ backgroundColor: '#06B6D4' }}
                                />
                                <span className='flex-1 text-cyan-400'>
                                  {sharedCount} mutual connections
                                </span>
                                {jaccard != null && (
                                  <span className='shrink-0 tabular-nums text-cyan-500'>
                                    {(jaccard * 100).toFixed(0)}% overlap
                                  </span>
                                )}
                              </div>
                            )
                          })}

                          {/* Analytics edges — labeled by class */}
                          {analyticsEdges.map((edge, i) => {
                            const color = EDGE_CLASS_COLORS[edge.evidence_class] || '#6B7280'
                            const confPct = Math.round((edge.confidence || 0) * 100)
                            const classLabel = EDGE_CLASS_LABELS[edge.evidence_class] || edge.evidence_class
                            return (
                              <div key={`a${i}`} className='flex items-center gap-2 text-[11px]'>
                                <span
                                  className='h-2 w-2 shrink-0 rounded-full'
                                  style={{ backgroundColor: color }}
                                />
                                <span className='flex-1 truncate text-muted-foreground'>
                                  {classLabel}: {edge.band || edge.label}
                                </span>
                                <span className='shrink-0 tabular-nums' style={{ color }}>
                                  {confPct}%
                                </span>
                              </div>
                            )
                          })}
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>

            {/* Footer */}
            <div className='border-t border-border/30 px-4 py-2 text-[10px] text-muted-foreground'>
              {dossierData.connections.length} connected profile
              {dossierData.connections.length !== 1 ? 's' : ''} ·{' '}
              {dossierData.connections.reduce((sum, c) => sum + c.edges.length, 0)} total links
            </div>
          </div>
        )}

        <div ref={containerRef} style={{ height: isFullscreen ? '100vh' : `${DEFAULT_HEIGHT}px`, width: '100%' }}>
          <ForceGraph2D
            ref={graphRef as any}
            width={isFullscreen ? window.innerWidth : dimensions.width}
            height={isFullscreen ? window.innerHeight : graphHeight}
            graphData={filteredData}
            nodeId='id'
            nodeCanvasObject={drawNode as any}
            nodePointerAreaPaint={(node: any, color, ctx) => {
              const size = (node as GraphNode).size || 8
              ctx.fillStyle = color
              ctx.beginPath()
              ctx.arc(node.x, node.y, size + 6, 0, 2 * Math.PI)
              ctx.fill()
            }}
            linkCanvasObject={drawLink as any}
            linkDirectionalArrowLength={0}
            onNodeHover={handleNodeHover as any}
            onNodeClick={handleNodeClick as any}
            onLinkClick={handleLinkClick as any}
            onBackgroundClick={() => {
              setSelectedNode(null)
              setSelectedEdge(null)
            }}
            cooldownTicks={120}
            d3AlphaDecay={0.015}
            d3VelocityDecay={0.25}
            d3AlphaMin={0.001}
            enableNodeDrag={true}
            enableZoomInteraction={true}
            enablePanInteraction={true}
            backgroundColor='transparent'
          />
        </div>
      </Card>

      {/* ── Mutual Connections Panel — only for clicked node ── */}
      <MutualConnectionsPanel
        edges={graphData.edges}
        nodes={graphData.nodes}
        selectedNodeId={selectedNode?.id ?? null}
      />

      {/* ── Detail Panel ── */}
      {selectedNode && (
        <NodeDetailPanel node={selectedNode} onClose={() => setSelectedNode(null)} />
      )}
      {selectedEdge && (
        <EdgeDetailPanel edge={selectedEdge} onClose={() => setSelectedEdge(null)} />
      )}
    </div>
  )
}

// ── Node Detail Panel ──

function NodeDetailPanel({ node, onClose }: { node: GraphNode; onClose: () => void }) {
  const color = node.type === 'seed'
    ? NODE_TYPE_COLORS.seed
    : PLATFORM_COLORS[node.platform || 'default'] || PLATFORM_COLORS.default

  return (
    <Card>
      <CardHeader className='flex flex-row items-center justify-between pb-3'>
        <div className='flex items-center gap-3'>
          <div
            className='flex h-10 w-10 items-center justify-center rounded-full text-sm font-bold text-white'
            style={{ backgroundColor: color }}
          >
            {node.type === 'seed' ? '◎' : (node.platform || '?').charAt(0).toUpperCase()}
          </div>
          <div>
            <CardTitle className='text-base'>{node.label}</CardTitle>
            <p className='text-xs text-muted-foreground'>
              {node.type === 'seed' && `Seed identifier (${node.identifier_type})`}
              {node.type === 'account' && `${capitalize(node.platform || '')} account`}
              {node.type === 'discovery' && `Discovery — ${node.category || 'unverified lead'}`}
            </p>
          </div>
        </div>
        <Button size='icon' variant='ghost' className='h-7 w-7' onClick={onClose}>
          <X className='h-4 w-4' />
        </Button>
      </CardHeader>
      <CardContent className='grid gap-2 text-sm'>
        {node.display_name && (
          <div className='flex justify-between'>
            <span className='text-muted-foreground'>Display name</span>
            <span>{node.display_name}</span>
          </div>
        )}
        {node.bio && (
          <div>
            <span className='text-muted-foreground'>Bio</span>
            <p className='mt-0.5 text-xs'>{node.bio}</p>
          </div>
        )}
        {node.location && (
          <div className='flex justify-between'>
            <span className='text-muted-foreground'>Location</span>
            <span>{node.location}</span>
          </div>
        )}
        {node.follower_count != null && (
          <div className='flex justify-between'>
            <span className='text-muted-foreground'>Followers</span>
            <span>{node.follower_count.toLocaleString()}</span>
          </div>
        )}
        {node.following_count != null && (
          <div className='flex justify-between'>
            <span className='text-muted-foreground'>Following</span>
            <span>{node.following_count.toLocaleString()}</span>
          </div>
        )}
        {node.url && (
          <div className='flex justify-between'>
            <span className='text-muted-foreground'>URL</span>
            <a
              href={node.url}
              target='_blank'
              rel='noopener noreferrer'
              className='truncate text-xs text-blue-400 hover:underline'
            >
              {node.url}
            </a>
          </div>
        )}
        {node.type === 'discovery' && (
          <div className='mt-2 rounded bg-muted/50 p-2 text-xs text-muted-foreground'>
            <AlertTriangle className='mb-1 inline h-3 w-3' /> This is an unverified discovery from
            username search. Requires deep collection to confirm.
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// ── Edge Detail Panel ──

function EdgeDetailPanel({ edge, onClose }: { edge: GraphEdge; onClose: () => void }) {
  const color = EDGE_CLASS_COLORS[edge.evidence_class] || '#6B7280'
  const confidencePct = Math.round((edge.confidence || 0) * 100)

  return (
    <Card>
      <CardHeader className='flex flex-row items-center justify-between pb-3'>
        <div className='flex items-center gap-3'>
          <div className='h-1 w-10 rounded' style={{ backgroundColor: color }} />
          <div>
            <CardTitle className='text-base'>Connection: {edge.label}</CardTitle>
            <p className='text-xs text-muted-foreground'>
              {edge.type === 'correlation' && 'Identity correlation'}
              {edge.type === 'cross_reference' && 'Self-declared link (bio/profile)'}
              {edge.type === 'network' && `Social network — ${edge.platform || ''}`}
              {edge.type === 'coordination' && 'Behavioral coordination signal'}
              {edge.type === 'discovery' && 'Unverified discovery link'}
              {edge.type === 'mutual_network' && `Mutual connections — ${edge.platform || ''}`}
              {edge.type === 'seed_to_account' && 'Seed → collected account'}
            </p>
          </div>
        </div>
        <Button size='icon' variant='ghost' className='h-7 w-7' onClick={onClose}>
          <X className='h-4 w-4' />
        </Button>
      </CardHeader>
      <CardContent className='grid gap-3 text-sm'>
        <div>
          <div className='mb-1 flex justify-between text-xs'>
            <span className='text-muted-foreground'>Confidence</span>
            <span className='font-medium' style={{ color }}>
              {confidencePct}%{edge.band && ` (${edge.band})`}
            </span>
          </div>
          <div className='h-2 overflow-hidden rounded-full bg-muted'>
            <div
              className='h-full rounded-full transition-all'
              style={{ width: `${confidencePct}%`, backgroundColor: color }}
            />
          </div>
        </div>

        <div className='flex justify-between'>
          <span className='text-muted-foreground'>Evidence class</span>
          <Badge
            variant='outline'
            className={cn(
              'text-[10px]',
              edge.evidence_class === 'hard_link' && 'border-green-500/50 text-green-400',
              edge.evidence_class === 'probabilistic' && 'border-yellow-500/50 text-yellow-400',
              edge.evidence_class === 'network' && 'border-purple-500/50 text-purple-400',
              edge.evidence_class === 'behavioral' && 'border-pink-500/50 text-pink-400',
              edge.evidence_class === 'discovery' && 'border-gray-500/50 text-gray-400'
            )}
          >
            {edge.evidence_class.replace('_', ' ')}
          </Badge>
        </div>

        {edge.shap && edge.type === 'correlation' && (
          <div className='space-y-1.5'>
            <span className='text-xs font-medium text-muted-foreground'>Signal Breakdown</span>
            {renderShapBar('Username', edge.shap.username_score as number)}
            {renderShapBar('Bio', edge.shap.bio_score as number)}
            {renderShapBar('Profile Image', edge.shap.profile_image_score as number)}
            {renderShapBar('Temporal', edge.shap.temporal_score as number)}
            {renderShapBar('Community', edge.shap.community_score as number)}
            {renderShapBar('Stylometry', edge.shap.stylometry_score as number)}
            {renderShapBar('Geo Agreement', edge.shap.geo_agreement as number)}
          </div>
        )}

        {edge.tier1_links && edge.tier1_links.length > 0 && (
          <div>
            <span className='text-xs font-medium text-muted-foreground'>Hard Evidence</span>
            <ul className='mt-1 space-y-0.5'>
              {edge.tier1_links.map((link, i) => (
                <li key={i} className='text-xs text-green-400'>
                  ✓ {link}
                </li>
              ))}
            </ul>
          </div>
        )}

        {edge.detail && (
          <div>
            <span className='text-xs font-medium text-muted-foreground'>Detail</span>
            <p className='mt-0.5 text-xs'>{edge.detail}</p>
          </div>
        )}

        {(edge as any).mutual_usernames && (edge as any).mutual_usernames.length > 0 && (
          <div>
            <span className='text-xs font-medium text-muted-foreground'>
              Mutual Accounts ({(edge as any).mutual_usernames.length})
            </span>
            <div className='mt-1.5 max-h-48 overflow-y-auto rounded-md bg-muted/30 p-2'>
              <div className='grid grid-cols-2 gap-x-3 gap-y-1'>
                {((edge as any).mutual_usernames as string[]).map((username: string) => (
                  <span key={username} className='truncate text-[11px] text-muted-foreground'>
                    @{username}
                  </span>
                ))}
              </div>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// ── Mutual Connections Panel ──

function MutualConnectionsPanel({
  edges,
  nodes,
  selectedNodeId,
}: {
  edges: GraphEdge[]
  nodes: GraphNode[]
  selectedNodeId: string | null
}) {
  const mutualEdges = edges.filter((e) => e.type === 'mutual_network')
  if (mutualEdges.length === 0 || !selectedNodeId) return null

  const nodeLabel = new Map<string, string>()
  for (const n of nodes) nodeLabel.set(n.id, n.label)

  const relevantEdges = mutualEdges.filter((e) => {
    const src = typeof e.source === 'object' ? (e.source as any).id : e.source
    const tgt = typeof e.target === 'object' ? (e.target as any).id : e.target
    return src === selectedNodeId || tgt === selectedNodeId
  })

  if (relevantEdges.length === 0) return null

  const selectedLabel = nodeLabel.get(selectedNodeId) || selectedNodeId

  return (
    <Card>
      <CardHeader className='pb-2'>
        <CardTitle className='flex items-center gap-2 text-sm font-medium'>
          <span className='h-3 w-3 rounded-full bg-cyan-500' />
          Mutual Connections — {selectedLabel}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className='space-y-4'>
          {relevantEdges.map((edge, i) => {
            const src = typeof edge.source === 'object' ? (edge.source as any).id : edge.source
            const tgt = typeof edge.target === 'object' ? (edge.target as any).id : edge.target
            const otherId = src === selectedNodeId ? tgt : src
            const otherLabel = nodeLabel.get(otherId) || otherId
            const usernames = (edge as any).mutual_usernames as string[] | undefined
            const sharedCount = (edge as any).shared_count as number | undefined
            const jaccard = (edge as any).jaccard as number | undefined

            return (
              <div key={i}>
                <div className='mb-2 flex items-center justify-between'>
                  <div className='flex items-center gap-2'>
                    <Badge variant='outline' className='border-purple-500/50 text-[10px] text-purple-400'>
                      {edge.platform}
                    </Badge>
                    <span className='text-xs font-medium'>
                      {selectedLabel} ↔ {otherLabel}
                    </span>
                  </div>
                  <div className='flex items-center gap-2'>
                    <Badge variant='secondary' className='text-[10px]'>
                      {sharedCount ?? 0} shared
                    </Badge>
                    {jaccard != null && (
                      <Badge variant='outline' className='text-[10px]'>
                        Jaccard: {(jaccard * 100).toFixed(1)}%
                      </Badge>
                    )}
                  </div>
                </div>
                {edge.detail && (
                  <p className='mb-2 text-[11px] text-muted-foreground'>{edge.detail}</p>
                )}
                {usernames && usernames.length > 0 && (
                  <div className='max-h-52 overflow-y-auto rounded-md bg-muted/30 p-2'>
                    <div className='grid grid-cols-3 gap-x-4 gap-y-1 sm:grid-cols-4 md:grid-cols-5'>
                      {usernames.map((u) => (
                        <span key={u} className='truncate text-[11px] text-muted-foreground'>
                          @{u}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </CardContent>
    </Card>
  )
}

// ── Helpers ──

function renderShapBar(label: string, value: number | null | undefined) {
  if (value == null) return null
  const pct = Math.round(value * 100)
  const color = pct >= 70 ? '#10B981' : pct >= 40 ? '#F59E0B' : '#6B7280'
  return (
    <div className='flex items-center gap-2'>
      <span className='w-20 text-[10px] text-muted-foreground'>{label}</span>
      <div className='h-1.5 flex-1 overflow-hidden rounded-full bg-muted'>
        <div className='h-full rounded-full' style={{ width: `${pct}%`, backgroundColor: color }} />
      </div>
      <span className='w-8 text-right text-[10px]' style={{ color }}>
        {pct}%
      </span>
    </div>
  )
}

function capitalize(s: string) {
  return s.charAt(0).toUpperCase() + s.slice(1)
}
