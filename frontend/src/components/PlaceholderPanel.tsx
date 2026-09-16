import { Typography } from 'antd'
import type { ReactNode } from 'react'

interface PlaceholderPanelProps {
  title: string
  description: string
  children?: ReactNode
}

export function PlaceholderPanel({
  title,
  description,
  children,
}: PlaceholderPanelProps) {
  return (
    <section className="placeholder-panel">
      <Typography.Title level={4}>{title}</Typography.Title>
      <Typography.Paragraph type="secondary">
        {description}
      </Typography.Paragraph>
      {children}
    </section>
  )
}
