import { Phone, MapPin, ExternalLink, ShieldAlert } from 'lucide-react'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'

interface Lookup {
  id: number
  input_value?: string
  result?: Record<string, unknown>
}

interface Props {
  lookup: Lookup
}

function InfoRow({
  label,
  value,
  sub,
  variant,
}: {
  label: string
  value?: string | null
  sub?: string | null
  variant?: 'success' | 'danger' | 'default'
}) {
  if (value == null || value === '') return null
  return (
    <div className='flex items-center justify-between py-1.5 border-b border-muted/30 last:border-0'>
      <span className='text-sm text-muted-foreground'>{label}</span>
      <span
        className={`text-sm font-medium ${
          variant === 'success'
            ? 'text-primary'
            : variant === 'danger'
              ? 'text-destructive'
              : ''
        }`}
      >
        {value}
        {sub && (
          <span className='ml-1 text-xs font-normal text-muted-foreground'>
            ({sub})
          </span>
        )}
      </span>
    </div>
  )
}

export function PhoneResults({ lookup }: Props) {
  const r = (lookup.result || {}) as Record<string, unknown>
  const phoneNumber = String(r.phone_number ?? lookup.input_value ?? '')

  // Resolve validity and validation errors
  const isValid = r.twilio_valid !== null ? (r.twilio_valid as boolean) : (r.valid as boolean)
  const validationErrors = (r.twilio_validation_errors as string[]) || (r.validation_errors as string[]) || []

  // Resolve Carrier Info (prefer Twilio authoritative)
  const lineType = (r.twilio_line_type as string) || (r.line_type as string) || 'unknown'
  const carrier = (r.twilio_carrier_name as string) || (r.carrier as string) || 'unknown'
  const countryName = (r.country_name as string) || 'unknown'
  const countryCode = (r.twilio_country_code as string) || (r.country_code as string) || ''
  const location = (r.location as string) || ''

  // Twilio Caller Name (CNAM)
  const callerName = r.twilio_caller_name as string | null
  const callerType = r.twilio_caller_type as string | null

  // Geocoding Coordinates
  const geoLat = r.geo_lat as number | null
  const geoLon = r.geo_lon as number | null
  const geoDisplayName = r.geo_display_name as string | null

  // Map embedding iframe URL
  const mapIframeUrl = geoLat && geoLon
    ? `https://www.openstreetmap.org/export/embed.html?bbox=${geoLon - 0.015}%2C${geoLat - 0.015}%2C${geoLon + 0.015}%2C${geoLat + 0.015}&layer=mapnik&marker=${geoLat}%2C${geoLon}`
    : null

  const mapExternalUrl = geoLat && geoLon
    ? `https://www.openstreetmap.org/?mlat=${geoLat}&mlon=${geoLon}#map=15/${geoLat}/${geoLon}`
    : null

  return (
    <div className='overflow-hidden rounded-lg border bg-card'>
      {/* Header */}
      <div className='flex items-center gap-3 border-b bg-muted/30 px-4 py-3'>
        <div className='flex h-8 w-8 items-center justify-center rounded-full bg-primary/10'>
          <Phone className='h-4 w-4 text-primary' />
        </div>
        <div>
          <p className='text-sm font-medium'>Phone Intelligence</p>
          <div className='flex items-center gap-2'>
            <p className='font-mono text-xs text-muted-foreground'>
              {phoneNumber}
            </p>
            {!!r.twilio_national_format && (
              <p className='font-mono text-xs text-muted-foreground/80'>
                ({String(r.twilio_national_format)})
              </p>
            )}
          </div>
        </div>
        <div className='ml-auto flex items-center gap-2'>
          {r.twilio_valid !== null && (
            <Badge variant='outline' className='border-emerald-500/30 text-emerald-500 bg-emerald-500/10'>
              Twilio Verified
            </Badge>
          )}
          <Badge
            variant={isValid ? 'default' : 'destructive'}
          >
            {isValid ? 'Valid Number' : 'Invalid Number'}
          </Badge>
        </div>
      </div>

      {/* Twilio Lookup Warning Banner for Invalid Numbers */}
      {!isValid && (
        <div className='flex items-start gap-2.5 bg-destructive/10 border-b border-destructive/20 px-4 py-3 text-destructive text-sm'>
          <ShieldAlert className='h-4 w-4 mt-0.5 shrink-0' />
          <div>
            <p className='font-medium'>Validation Failure</p>
            {validationErrors.length > 0 ? (
              <p className='text-xs opacity-90'>
                Error code: {validationErrors.join(', ')}
              </p>
            ) : (
              <p className='text-xs opacity-90'>
                Number is in an invalid range or has incorrect prefixes.
              </p>
            )}
          </div>
        </div>
      )}

      {/* Grid for Carrier & Location details */}
      <div className='grid grid-cols-1 md:grid-cols-2 divide-y md:divide-y-0 md:divide-x'>
        {/* Carrier Section */}
        <div className='px-4 py-3 flex flex-col justify-between'>
          <div>
            <p className='mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground'>
              Carrier Information
            </p>
            <div className='space-y-0.5'>
              <InfoRow label='Line Type' value={lineType} />
              <InfoRow label='Carrier' value={carrier} />
              <InfoRow
                label='Country'
                value={countryName}
                sub={countryCode}
              />
              <InfoRow label='Location (Carrier)' value={location} />
              
              {!!r.twilio_mobile_country_code && (
                <InfoRow 
                  label='Network Code (MCC/MNC)' 
                  value={`${r.twilio_mobile_country_code}/${r.twilio_mobile_network_code ?? '—'}`} 
                />
              )}
            </div>
          </div>

          {/* Caller Name Info (CNAM) */}
          {callerName && (
            <div className='mt-3 pt-3 border-t border-muted/50'>
              <p className='mb-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground'>
                Caller ID (CNAM)
              </p>
              <div className='rounded bg-muted/20 p-2 text-xs flex flex-col gap-1'>
                <div className='flex justify-between'>
                  <span className='text-muted-foreground'>Caller Name:</span>
                  <span className='font-medium text-foreground'>{callerName}</span>
                </div>
                {callerType && (
                  <div className='flex justify-between'>
                    <span className='text-muted-foreground'>Type:</span>
                    <span className='font-medium text-foreground'>{callerType}</span>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Location & Map Section */}
        <div className='px-4 py-3 flex flex-col justify-between'>
          <div>
            <p className='mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground'>
              Geographic Intelligence
            </p>
            {geoLat && geoLon ? (
              <div className='space-y-2'>
                {mapIframeUrl && (
                  <div className='relative w-full h-[150px] rounded border overflow-hidden bg-muted/20'>
                    <iframe
                      title='Location Map'
                      src={mapIframeUrl}
                      className='absolute inset-0 w-full h-full border-none'
                      scrolling='no'
                    />
                  </div>
                )}
                <div className='flex items-start gap-1.5 text-xs'>
                  <MapPin className='h-3.5 w-3.5 mt-0.5 text-muted-foreground shrink-0' />
                  <div className='flex-1'>
                    <p className='font-medium text-foreground line-clamp-2'>
                      {geoDisplayName || location || countryName}
                    </p>
                    <div className='mt-1 flex items-center justify-between'>
                      <span className='font-mono text-[10px] text-muted-foreground'>
                        {geoLat.toFixed(5)}, {geoLon.toFixed(5)}
                      </span>
                      {mapExternalUrl && (
                        <a
                          href={mapExternalUrl}
                          target='_blank'
                          rel='noopener noreferrer'
                          className='inline-flex items-center gap-1 text-[10px] text-primary hover:underline'
                        >
                          OpenStreetMap <ExternalLink className='h-2.5 w-2.5' />
                        </a>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              <div className='rounded border border-dashed py-6 text-center text-xs text-muted-foreground flex flex-col items-center justify-center gap-1'>
                <MapPin className='h-5 w-5 opacity-40 mb-1' />
                <p>No map data available</p>
                <p className='text-[10px] opacity-80 max-w-[200px]'>
                  Location string from carrier lookup was insufficient to geocode.
                </p>
              </div>
            )}
          </div>
        </div>
      </div>

      <Separator />

      {/* Messaging Apps */}
      <div className='grid grid-cols-1 divide-y sm:grid-cols-2 sm:divide-x sm:divide-y-0'>
        {/* Telegram */}
        <div className='px-4 py-3'>
          <p className='mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground'>
            Telegram
          </p>
          {r.telegram_user_id ? (
            <div className='flex items-center gap-3'>
              <Avatar className='h-9 w-9'>
                {!!r.telegram_profile_photo_url && (
                  <AvatarImage src={r.telegram_profile_photo_url as string} />
                )}
                <AvatarFallback className='text-xs bg-sky-500/10 text-sky-500'>TG</AvatarFallback>
              </Avatar>
              <div>
                <p className='text-sm font-medium'>
                  {String(r.telegram_display_name ?? 'Unknown')}
                </p>
                {!!r.telegram_username && (
                  <a
                    href={`https://t.me/${r.telegram_username}`}
                    target='_blank'
                    rel='noopener noreferrer'
                    className='text-xs text-primary hover:underline flex items-center gap-1'
                  >
                    @{String(r.telegram_username)} <ExternalLink className='h-2.5 w-2.5' />
                  </a>
                )}
              </div>
            </div>
          ) : (
            <p className='text-sm text-muted-foreground'>
              {r.telegram_registered === false
                ? 'Not registered'
                : 'Not checked'}
            </p>
          )}
        </div>

        {/* WhatsApp */}
        <div className='px-4 py-3'>
          <p className='mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground'>
            WhatsApp
          </p>
          {r.whatsapp_registered ? (
            <div className='flex items-center gap-3'>
              <Avatar className='h-9 w-9'>
                {!!r.whatsapp_profile_photo_url && (
                  <AvatarImage
                    src={r.whatsapp_profile_photo_url as string}
                  />
                )}
                <AvatarFallback className='text-xs bg-emerald-500/10 text-emerald-500'>WA</AvatarFallback>
              </Avatar>
              <div>
                <p className='text-sm font-medium'>
                  {String(r.whatsapp_display_name ?? '—')}
                </p>
                {!!r.whatsapp_about && (
                  <p className='line-clamp-1 text-xs text-muted-foreground'>
                    {String(r.whatsapp_about)}
                  </p>
                )}
              </div>
            </div>
          ) : (
            <p className='text-sm text-muted-foreground'>
              {r.whatsapp_registered === false
                ? 'Not registered'
                : 'Not checked'}
            </p>
          )}
        </div>
      </div>

      {/* Web mentions */}
      {Array.isArray(r.web_mentions) && r.web_mentions.length > 0 && (
        <>
          <Separator />
          <div className='px-4 py-3'>
            <div className='mb-2 flex items-center gap-2'>
              <p className='text-xs font-semibold uppercase tracking-wider text-muted-foreground'>
                Web Mentions
              </p>
              <Badge variant='secondary'>{r.web_mentions.length}</Badge>
            </div>
            <div className='space-y-2'>
              {(r.web_mentions as Array<Record<string, string>>).map(
                (m, i) => (
                  <div key={i} className='text-xs'>
                    <a
                      href={m.url}
                      target='_blank'
                      rel='noopener noreferrer'
                      className='inline-flex items-center gap-1 text-sm text-primary hover:underline'
                    >
                      {m.title || m.url} <ExternalLink className='h-3 w-3' />
                    </a>
                    {m.snippet && (
                      <p className='text-muted-foreground mt-0.5 leading-relaxed'>
                        {m.snippet}
                      </p>
                    )}
                  </div>
                )
              )}
            </div>
          </div>
        </>
      )}

      {/* Confidence / Pipeline Footer */}
      <div className='bg-muted/10 px-4 py-2 border-t text-[10px] text-muted-foreground flex justify-between items-center'>
        <span>Verification Pipeline Confidence: <strong>{isValid ? 'High' : 'Low'}</strong></span>
        <div className='flex items-center gap-2'>
          <span className='flex items-center gap-0.5'>
            Local {r.valid !== null ? '✓' : '—'}
          </span>
          <span className='flex items-center gap-0.5'>
            Twilio {r.twilio_valid !== null ? '✓' : '—'}
          </span>
          <span className='flex items-center gap-0.5'>
            Geocoded {geoLat !== null ? '✓' : '—'}
          </span>
        </div>
      </div>
    </div>
  )
}
