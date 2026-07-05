import { Phone, ExternalLink, ShieldAlert } from 'lucide-react'
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

      {/* Carrier details */}
      <div className='px-4 py-3'>
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
                  {r.telegram_display_name
                    ? String(r.telegram_display_name)
                    : <span className='text-muted-foreground italic'>Name not available</span>}
                </p>
                {r.telegram_username ? (
                  <a
                    href={`https://t.me/${r.telegram_username}`}
                    target='_blank'
                    rel='noopener noreferrer'
                    className='text-xs text-primary hover:underline flex items-center gap-1'
                  >
                    @{String(r.telegram_username)} <ExternalLink className='h-2.5 w-2.5' />
                  </a>
                ) : (
                  <p className='text-xs text-muted-foreground italic'>Username not available</p>
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
        </div>
      </div>
    </div>
  )
}
