import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import ForceGraph2D, {
  type ForceGraphMethods,
  type NodeObject,
  type LinkObject,
} from 'react-force-graph-2d'
import {
  AlertTriangle,
  Eye,
  EyeOff,
  Info,
  Maximize2,
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

// ── Edge dash patterns ──

const EDGE_DASH: Record<string, number[] | undefined> = {
  hard_link: undefined,
  deterministic: undefined,
  probabilistic: [5, 3],
  network: [2, 2],
  behavioral: [8, 4],
  discovery: [3, 6],
}

// ── Component ──

export function InvestigationGraph({ caseId, apiBase }: InvestigationGraphProps) {
  const graphRef = useRef<ForceGraphMethods<NodeObject<GraphNode>>>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [graphData, setGraphData] = useState<GraphData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null)
  const [selectedEdge, setSelectedEdge] = useState<GraphEdge | null>(null)
  const [dimensions, setDimensions] = useState({ width: 800, height: 500 })
  const [showDiscoveries, setShowDiscoveries] = useState(true)
  const [highlightNodes, setHighlightNodes] = useState<Set<string>>(new Set())
  const [highlightEdges, setHighlightEdges] = useState<Set<string>>(new Set())
  const [hoverNode, setHoverNode] = useState<string | null>(null)

  // Fetch graph data
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

  // Configure force simulation after data loads
  useEffect(() => {
    if (!graphRef.current || !graphData) return
    const fg = graphRef.current
    // Repulsion: nodes push apart
    fg.d3Force('charge')?.strength((node: any) => {
      const n = node as GraphNode
      return n.type === 'seed' ? -300 : n.type === 'discovery' ? -50 : -150
    })
    // Link distance: strong links pull tight, weak float further
    fg.d3Force('link')?.distance((link: any) => {
      const confidence = link.confidence || 0.3
      return 50 + (1 - confidence) * 120
    })
    // Collision: prevent overlap
    fg.d3Force('collide', null)
    // Center force
    fg.d3Force('center')?.strength(0.05)
  }, [graphData])

  // Resize observer
  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setDimensions({
          width: entry.contentRect.width,
          height: Math.max(entry.contentRect.height, 500),
        })
      }
    })
    observer.observe(container)
    return () => observer.disconnect()
  }, [])

  // Filter nodes based on toggle
  const filteredData = useMemo(() => {
    if (!graphData) return { nodes: [], links: [] }

    const visibleNodes = showDiscoveries
      ? graphData.nodes
      : graphData.nodes.filter((n) => n.type !== 'discovery')

    const visibleIds = new Set(visibleNodes.map((n) => n.id))

    const links = graphData.edges
      .filter((e) => visibleIds.has(e.source) && visibleIds.has(e.target))
      .map((e) => ({
        ...e,
        source: e.source,
        target: e.target,
      }))

    return { nodes: [...visibleNodes], links }
  }, [graphData, showDiscoveries])

  // Node interactions
  const handleNodeHover = useCallback(
    (node: NodeObject<GraphNode> | null) => {
      if (!node) {
        setHighlightNodes(new Set())
        setHighlightEdges(new Set())
        setHoverNode(null)
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
    [filteredData.links]
  )

  const handleNodeClick = useCallback(
    (node: NodeObject<GraphNode>) => {
      setSelectedEdge(null)
      setSelectedNode(node as unknown as GraphNode)
      // Center on node
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

  // Custom node rendering
  const drawNode = useCallback(
    (node: NodeObject<GraphNode>, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const n = node as unknown as GraphNode & { x: number; y: number }
      const size = n.size || 8
      const isHighlighted = highlightNodes.size === 0 || highlightNodes.has(n.id)
      const opacity = isHighlighted ? 1 : 0.2

      ctx.save()
      ctx.globalAlpha = opacity

      // Draw outer ring for seeds
      if (n.type === 'seed') {
        ctx.beginPath()
        ctx.arc(n.x, n.y, size + 3, 0, 2 * Math.PI)
        ctx.strokeStyle = NODE_TYPE_COLORS.seed
        ctx.lineWidth = 2
        ctx.stroke()
      }

      // Draw node circle
      ctx.beginPath()
      ctx.arc(n.x, n.y, size, 0, 2 * Math.PI)

      if (n.type === 'seed') {
        ctx.fillStyle = NODE_TYPE_COLORS.seed
      } else if (n.type === 'discovery') {
        ctx.fillStyle = NODE_TYPE_COLORS.discovery
        ctx.setLineDash([2, 2])
        ctx.strokeStyle = '#9CA3AF'
        ctx.lineWidth = 1
        ctx.stroke()
        ctx.setLineDash([])
      } else {
        ctx.fillStyle = PLATFORM_COLORS[n.platform || 'default'] || PLATFORM_COLORS.default
      }
      ctx.fill()

      // Draw platform icon letter
      const fontSize = Math.max(size * 0.8, 4)
      ctx.font = `bold ${fontSize}px Inter, sans-serif`
      ctx.textAlign = 'center'
      ctx.textBaseline = 'middle'
      ctx.fillStyle = '#FFFFFF'
      const icon = n.type === 'seed'
        ? '◎'
        : n.platform
          ? n.platform.charAt(0).toUpperCase()
          : '?'
      ctx.fillText(icon, n.x, n.y)

      // Draw label if zoomed in enough
      if (globalScale > 1.2) {
        const label = n.label || ''
        const truncated = label.length > 16 ? label.slice(0, 14) + '…' : label
        const labelSize = Math.max(3.5, 10 / globalScale)
        ctx.font = `${labelSize}px Inter, sans-serif`
        ctx.textAlign = 'center'
        ctx.fillStyle = isHighlighted ? '#E5E7EB' : '#6B7280'
        ctx.fillText(truncated, n.x, n.y + size + labelSize + 1)
      }

      // Hover halo
      if (hoverNode === n.id) {
        ctx.beginPath()
        ctx.arc(n.x, n.y, size + 6, 0, 2 * Math.PI)
        ctx.strokeStyle = PLATFORM_COLORS[n.platform || 'default'] || '#3B82F6'
        ctx.lineWidth = 1.5
        ctx.globalAlpha = 0.4
        ctx.stroke()
      }

      ctx.restore()
    },
    [highlightNodes, hoverNode]
  )

  // Custom link rendering
  const drawLink = useCallback(
    (link: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const edge = link as GraphEdge & { source: { x: number; y: number }; target: { x: number; y: number } }
      if (!edge.source || !edge.target) return

      const src = edge.source as any
      const tgt = edge.target as any
      if (!src.x || !tgt.x) return

      const linkIdx = filteredData.links.indexOf(link)
      const isHighlighted = highlightEdges.size === 0 || highlightEdges.has(`${linkIdx}`)
      const opacity = isHighlighted ? 0.8 : 0.1

      const color = EDGE_CLASS_COLORS[edge.evidence_class] || '#6B7280'
      const dash = EDGE_DASH[edge.evidence_class]
      const width = Math.max(0.5, (edge.confidence || 0.3) * 3)

      ctx.save()
      ctx.globalAlpha = opacity
      ctx.strokeStyle = color
      ctx.lineWidth = width / globalScale

      if (dash) ctx.setLineDash(dash.map((d) => d / globalScale))
      else ctx.setLineDash([])

      // Draw curved path for visual distinction
      const midX = (src.x + tgt.x) / 2
      const midY = (src.y + tgt.y) / 2
      const dx = tgt.x - src.x
      const dy = tgt.y - src.y
      const dist = Math.sqrt(dx * dx + dy * dy)
      const offset = Math.min(dist * 0.1, 15)
      const cpX = midX + (dy / dist) * offset
      const cpY = midY - (dx / dist) * offset

      ctx.beginPath()
      ctx.moveTo(src.x, src.y)
      ctx.quadraticCurveTo(cpX, cpY, tgt.x, tgt.y)
      ctx.stroke()
      ctx.setLineDash([])

      // Draw confidence label on hover
      if (isHighlighted && highlightEdges.size > 0 && globalScale > 1.5) {
        const labelSize = Math.max(3, 8 / globalScale)
        ctx.font = `${labelSize}px Inter, sans-serif`
        ctx.textAlign = 'center'
        ctx.fillStyle = color
        ctx.globalAlpha = 1
        ctx.fillText(edge.label || '', cpX, cpY - 3 / globalScale)
      }

      ctx.restore()
    },
    [highlightEdges, filteredData.links]
  )

  // Zoom controls
  const handleZoomIn = () => graphRef.current?.zoom(graphRef.current.zoom() * 1.5, 300)
  const handleZoomOut = () => graphRef.current?.zoom(graphRef.current.zoom() / 1.5, 300)
  const handleFit = () => graphRef.current?.zoomToFit(400, 40)

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
      </div>

      {/* ── Graph Canvas ── */}
      <Card className='relative overflow-hidden'>
        {/* Controls */}
        <div className='absolute left-3 top-3 z-10 flex flex-col gap-1'>
          <Button size='icon' variant='secondary' className='h-7 w-7' onClick={handleZoomIn}>
            <ZoomIn className='h-3.5 w-3.5' />
          </Button>
          <Button size='icon' variant='secondary' className='h-7 w-7' onClick={handleZoomOut}>
            <ZoomOut className='h-3.5 w-3.5' />
          </Button>
          <Button size='icon' variant='secondary' className='h-7 w-7' onClick={handleFit}>
            <Maximize2 className='h-3.5 w-3.5' />
          </Button>
        </div>

        {/* Filter toggle */}
        <div className='absolute right-3 top-3 z-10 flex gap-1'>
          <Button
            size='sm'
            variant={showDiscoveries ? 'secondary' : 'ghost'}
            className='h-7 gap-1 text-xs'
            onClick={() => setShowDiscoveries(!showDiscoveries)}
          >
            {showDiscoveries ? <Eye className='h-3 w-3' /> : <EyeOff className='h-3 w-3' />}
            Discoveries
          </Button>
        </div>

        {/* Legend */}
        <div className='absolute bottom-3 left-3 z-10 rounded-md bg-background/80 p-2 text-[10px] backdrop-blur-sm'>
          <div className='flex flex-col gap-1'>
            <div className='flex items-center gap-1.5'>
              <span className='inline-block h-2 w-4 rounded-sm bg-green-500' />
              <span>Hard link</span>
            </div>
            <div className='flex items-center gap-1.5'>
              <span className='inline-block h-2 w-4 rounded-sm bg-yellow-500' style={{ opacity: 0.7 }} />
              <span>Correlation</span>
            </div>
            <div className='flex items-center gap-1.5'>
              <span className='inline-block h-2 w-4 rounded-sm bg-purple-500' style={{ opacity: 0.7 }} />
              <span>Network</span>
            </div>
            <div className='flex items-center gap-1.5'>
              <span className='inline-block h-2 w-4 rounded-sm bg-gray-500' style={{ opacity: 0.5 }} />
              <span>Discovery (weak)</span>
            </div>
          </div>
        </div>

        <div ref={containerRef} className='h-[550px] w-full'>
          <ForceGraph2D
            ref={graphRef as any}
            width={dimensions.width}
            height={550}
            graphData={filteredData}
            nodeId='id'
            nodeCanvasObject={drawNode as any}
            nodePointerAreaPaint={(node: any, color, ctx) => {
              const size = (node as GraphNode).size || 8
              ctx.fillStyle = color
              ctx.beginPath()
              ctx.arc(node.x, node.y, size + 4, 0, 2 * Math.PI)
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
            cooldownTicks={80}
            d3AlphaDecay={0.02}
            d3VelocityDecay={0.3}
            d3AlphaMin={0.001}
            enableNodeDrag={true}
            enableZoomInteraction={true}
            enablePanInteraction={true}
            backgroundColor='transparent'
          />
        </div>
      </Card>

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
          <div
            className='h-1 w-10 rounded'
            style={{ backgroundColor: color }}
          />
          <div>
            <CardTitle className='text-base'>Connection: {edge.label}</CardTitle>
            <p className='text-xs text-muted-foreground'>
              {edge.type === 'correlation' && 'Identity correlation'}
              {edge.type === 'cross_reference' && 'Self-declared link (bio/profile)'}
              {edge.type === 'network' && `Social network — ${edge.platform || ''}`}
              {edge.type === 'coordination' && 'Behavioral coordination signal'}
              {edge.type === 'discovery' && 'Unverified discovery link'}
              {edge.type === 'seed_to_account' && 'Seed → collected account'}
            </p>
          </div>
        </div>
        <Button size='icon' variant='ghost' className='h-7 w-7' onClick={onClose}>
          <X className='h-4 w-4' />
        </Button>
      </CardHeader>
      <CardContent className='grid gap-3 text-sm'>
        {/* Confidence meter */}
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

        {/* Evidence class */}
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

        {/* SHAP breakdown for correlation edges */}
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

        {/* Tier 1 links */}
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

        {/* Detail text */}
        {edge.detail && (
          <div>
            <span className='text-xs font-medium text-muted-foreground'>Detail</span>
            <p className='mt-0.5 text-xs'>{edge.detail}</p>
          </div>
        )}
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
