export type UserSetupBlockerUiHints = {
  kind?: string
  blocker?: string
  app?: string
  title?: string
  body?: string
  cta?: string
}

/** Inline card when Computer Use hits an app setup wall the agent can't clear. */
export function UserSetupBlockerCard({ hints }: { hints: UserSetupBlockerUiHints }) {
  const title =
    typeof hints.title === 'string' && hints.title.trim()
      ? hints.title.trim()
      : hints.app
        ? `${hints.app} needs your attention`
        : 'App needs your attention'
  const body =
    typeof hints.body === 'string' && hints.body.trim()
      ? hints.body.trim()
      : 'Finish setup in the app, then reply done so I can continue.'
  const cta =
    typeof hints.cta === 'string' && hints.cta.trim()
      ? hints.cta.trim()
      : 'Reply done when ready'
  const app = typeof hints.app === 'string' ? hints.app.trim() : ''

  return (
    <div
      className="mt-3 flex max-w-md flex-col gap-2 rounded-lg border border-[color-mix(in_srgb,var(--dt-foreground)_14%,transparent)] bg-[color-mix(in_srgb,var(--dt-foreground)_4%,transparent)] p-3"
      data-slot="user-setup-blocker"
      data-blocker={hints.blocker || undefined}
    >
      <div className="text-[0.75rem] font-medium tracking-wide text-[color-mix(in_srgb,var(--dt-foreground)_72%,var(--ui-text-secondary))]">
        {app ? `${app} · Setup required` : 'Setup required'}
      </div>
      <div className="text-[0.95rem] font-medium text-[color-mix(in_srgb,var(--dt-foreground)_92%,transparent)]">
        {title}
      </div>
      <p className="text-sm leading-5 text-[color-mix(in_srgb,var(--dt-foreground)_78%,transparent)]">
        {body}
      </p>
      <p className="text-[0.75rem] text-[color-mix(in_srgb,var(--dt-foreground)_55%,transparent)]">
        {cta}
      </p>
    </div>
  )
}

export function isUserSetupBlockerUiHints(value: unknown): value is UserSetupBlockerUiHints {
  if (!value || typeof value !== 'object') {
    return false
  }
  const rec = value as Record<string, unknown>
  return rec.kind === 'user_setup_blocker'
}
