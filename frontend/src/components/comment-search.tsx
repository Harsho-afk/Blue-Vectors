import { useMemo, useState } from 'react'
import { ExternalLink, MessageCircle, Search, X } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

export interface InstagramComment {
  pk: string
  text: string
  username: string
  user_pk: string
  created_at: number | null
  like_count: number | null
  reply_count: number
}

function formatCommentTime(ts: number | null) {
  if (!ts) return null
  const d = new Date(ts * 1000)
  if (isNaN(d.getTime())) return null
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function matchesQuery(c: InstagramComment, q: string) {
  if (!q) return true
  return (
    (c.text && c.text.toLowerCase().includes(q)) ||
    (c.username && c.username.toLowerCase().includes(q))
  )
}

/** Username, linked out to their Instagram profile. */
export function CommentAuthor({ username }: { username: string }) {
  const handle = username || 'unknown'
  if (!username) {
    return <span className='font-mono font-medium text-muted-foreground'>@unknown</span>
  }
  return (
    <a
      href={`https://www.instagram.com/${handle}/`}
      target='_blank'
      rel='noopener noreferrer'
      className='font-mono font-medium text-primary hover:underline'
    >
      @{handle}
    </a>
  )
}

function CommentRow({ comment, postUrl }: { comment: InstagramComment; postUrl?: string | null }) {
  const when = formatCommentTime(comment.created_at)
  return (
    <div className='rounded border bg-background p-1.5 text-xs'>
      <div className='flex items-center justify-between gap-2'>
        <CommentAuthor username={comment.username} />
        <div className='flex items-center gap-1.5 text-muted-foreground'>
          {when && <span>{when}</span>}
          {comment.like_count != null && comment.like_count > 0 && (
            <span>♥ {comment.like_count}</span>
          )}
          {postUrl && (
            <a
              href={postUrl}
              target='_blank'
              rel='noopener noreferrer'
              className='hover:text-primary'
              title='View post'
            >
              <ExternalLink className='h-3 w-3' />
            </a>
          )}
        </div>
      </div>
      <p className='mt-0.5 text-foreground'>{comment.text}</p>
    </div>
  )
}

// ── Per-post search ──

interface PostSearchProps {
  comments: InstagramComment[]
  postUrl?: string | null
}

/**
 * Inline, per-post comment search. Meant to be embedded directly under a
 * single post's comment preview, scoped only to that post's comments.
 */
export function PostCommentSearch({ comments, postUrl }: PostSearchProps) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')

  const sorted = useMemo(
    () => [...comments].sort((a, b) => (b.created_at || 0) - (a.created_at || 0)),
    [comments]
  )

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase()
    return sorted.filter((c) => matchesQuery(c, q))
  }, [sorted, query])

  if (comments.length === 0) return null

  if (!open) {
    return (
      <button
        type='button'
        onClick={() => setOpen(true)}
        className='mt-1 text-xs text-primary hover:underline'
      >
        Search {comments.length} comment{comments.length !== 1 ? 's' : ''} on this post
      </button>
    )
  }

  return (
    <div className='mt-1.5 rounded-md border bg-muted/10 p-2'>
      <div className='flex items-center gap-1.5'>
        <div className='relative flex-1'>
          <Search className='absolute left-2 top-1/2 h-3 w-3 -translate-y-1/2 text-muted-foreground' />
          <Input
            autoFocus
            placeholder='Search text or username...'
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className='h-7 pl-7 text-xs'
          />
        </div>
        <Badge variant='secondary' className='shrink-0 text-xs'>
          {matches.length}/{comments.length}
        </Badge>
        <Button
          variant='ghost'
          size='icon'
          className='h-7 w-7 shrink-0'
          onClick={() => {
            setOpen(false)
            setQuery('')
          }}
        >
          <X className='h-3 w-3' />
        </Button>
      </div>

      {matches.length === 0 ? (
        <p className='py-3 text-center text-xs text-muted-foreground'>
          No comments match &quot;{query}&quot;.
        </p>
      ) : (
        <div className='mt-2 max-h-64 space-y-1.5 overflow-y-auto'>
          {matches.map((c) => (
            <CommentRow key={c.pk} comment={c} postUrl={postUrl} />
          ))}
        </div>
      )}

      {postUrl && (
        <a
          href={postUrl}
          target='_blank'
          rel='noopener noreferrer'
          className='mt-1.5 flex items-center gap-1 text-xs text-muted-foreground hover:text-primary'
        >
          <ExternalLink className='h-3 w-3' />
          View post
        </a>
      )}
    </div>
  )
}

// ── Global (account-wide) search ──

interface PostLike {
  id: number
  metadata: Record<string, unknown> | null
}

interface AccountSearchProps {
  posts: PostLike[]
}

/**
 * Global comment search across every post in an account. Rendered once at
 * the bottom of the post feed, in addition to each post's own inline search.
 */
export function AccountCommentSearch({ posts }: AccountSearchProps) {
  const [query, setQuery] = useState('')

  const totalComments = useMemo(
    () =>
      posts.reduce(
        (sum, p) => sum + (((p.metadata?.comments as InstagramComment[]) || []).length),
        0
      ),
    [posts]
  )

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return []

    const out: { postId: number; postUrl: string | null; comment: InstagramComment }[] = []
    for (const post of posts) {
      const comments = (post.metadata?.comments as InstagramComment[]) || []
      const url = (post.metadata?.url as string) || null
      for (const c of comments) {
        if (matchesQuery(c, q)) {
          out.push({ postId: post.id, postUrl: url, comment: c })
        }
      }
    }
    out.sort((a, b) => (b.comment.created_at || 0) - (a.comment.created_at || 0))
    return out
  }, [posts, query])

  if (totalComments === 0) return null

  return (
    <Card className='mt-3'>
      <CardHeader className='pb-3'>
        <div className='flex items-center justify-between'>
          <CardTitle className='flex items-center gap-2 text-sm'>
            <MessageCircle className='h-4 w-4' />
            Search All Comments
          </CardTitle>
          <Badge variant='secondary'>{totalComments.toLocaleString()} collected</Badge>
        </div>
      </CardHeader>
      <CardContent className='pt-0'>
        <div className='relative'>
          <Search className='absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground' />
          <Input
            placeholder='Search comment text or username across all posts...'
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className='h-8 pl-8 text-sm'
          />
        </div>

        {query.trim() && (
          <div className='mt-3'>
            <p className='mb-2 text-xs text-muted-foreground'>
              {matches.length} match{matches.length !== 1 ? 'es' : ''} for &quot;{query}&quot;
            </p>

            {matches.length === 0 ? (
              <p className='rounded-md border border-dashed py-4 text-center text-sm text-muted-foreground'>
                No comments match this search.
              </p>
            ) : (
              <div className='max-h-96 space-y-2 overflow-y-auto'>
                {matches.map(({ postId, postUrl, comment }, i) => (
                  <CommentRow key={`${postId}-${comment.pk}-${i}`} comment={comment} postUrl={postUrl} />
                ))}
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
