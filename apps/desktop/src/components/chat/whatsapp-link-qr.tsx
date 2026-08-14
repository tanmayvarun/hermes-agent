import QRCode from 'qrcode'
import { useEffect, useState } from 'react'

export type WhatsAppLinkUiHints = {
  kind?: string
  qr_payload?: string
  status?: string
  pairing_id?: string
  expires_at?: string
}

/** Inline WhatsApp “Link a device” QR for chat console turns. */
export function WhatsAppLinkQr({ hints }: { hints: WhatsAppLinkUiHints }) {
  const payload = typeof hints.qr_payload === 'string' ? hints.qr_payload.trim() : ''
  const [dataUrl, setDataUrl] = useState<string>('')
  const [error, setError] = useState<string>('')

  useEffect(() => {
    let cancelled = false
    setError('')
    setDataUrl('')
    if (!payload) {
      return
    }
    void QRCode.toDataURL(payload, {
      errorCorrectionLevel: 'M',
      margin: 1,
      width: 240
    })
      .then(url => {
        if (!cancelled) {
          setDataUrl(url)
        }
      })
      .catch(err => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err))
        }
      })
    return () => {
      cancelled = true
    }
  }, [payload])

  if (!payload && hints.kind !== 'whatsapp_link_device') {
    return null
  }

  return (
    <div
      className="mt-3 flex max-w-sm flex-col gap-2 rounded-lg border border-[color-mix(in_srgb,var(--dt-foreground)_14%,transparent)] bg-[color-mix(in_srgb,var(--dt-foreground)_4%,transparent)] p-3"
      data-slot="whatsapp-link-qr"
    >
      <div className="text-[0.75rem] font-medium tracking-wide text-[color-mix(in_srgb,var(--dt-foreground)_72%,var(--ui-text-secondary))]">
        WhatsApp · Link a device
      </div>
      {dataUrl ? (
        <img
          alt="WhatsApp link-device QR code"
          className="h-60 w-60 rounded-md bg-white p-2"
          src={dataUrl}
        />
      ) : error ? (
        <p className="text-sm text-[color-mix(in_srgb,var(--dt-foreground)_70%,transparent)]">
          Could not render QR ({error}). Open WhatsApp → Linked devices and paste the pairing payload
          from Settings → Channels if needed.
        </p>
      ) : (
        <p className="text-sm text-[color-mix(in_srgb,var(--dt-foreground)_70%,transparent)]">
          {payload ? 'Generating QR…' : 'Starting WhatsApp pairing…'}
        </p>
      )}
      {hints.expires_at ? (
        <p className="text-[0.7rem] text-[color-mix(in_srgb,var(--dt-foreground)_55%,transparent)]">
          Expires {hints.expires_at}
        </p>
      ) : null}
    </div>
  )
}

export function isWhatsAppLinkUiHints(value: unknown): value is WhatsAppLinkUiHints {
  if (!value || typeof value !== 'object') {
    return false
  }
  const rec = value as Record<string, unknown>
  const kind = typeof rec.kind === 'string' ? rec.kind : ''
  const qr = typeof rec.qr_payload === 'string' ? rec.qr_payload.trim() : ''
  return kind === 'whatsapp_link_device' || Boolean(qr)
}
