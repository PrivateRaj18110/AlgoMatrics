import { useState, type ReactNode } from 'react'
import { Bell, Check, Lock, Mail, Send } from 'lucide-react'
import { PageHeader } from '@/components/layout/PageHeader'
import { Panel } from '@/components/layout/Panel'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Badge } from '@/components/ui/badge'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'
import { useTheme } from '@/providers/theme'
import { useSettings } from '@/providers/settings'
import { USE_MOCK } from '@/services'
import { APP_VERSION } from '@/utils/constants'

/** A labelled settings row with a right-aligned control. */
function SettingRow({
  label,
  description,
  htmlFor,
  control,
}: {
  label: string
  description?: string
  htmlFor?: string
  control: ReactNode
}) {
  return (
    <div className="flex items-center justify-between gap-4 py-3">
      <div className="min-w-0">
        <Label htmlFor={htmlFor} className="text-sm">
          {label}
        </Label>
        {description && <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>}
      </div>
      <div className="shrink-0">{control}</div>
    </div>
  )
}

export default function SettingsPage() {
  const { theme, setTheme } = useTheme()
  const { settings, update } = useSettings()
  const [browserPerm, setBrowserPerm] = useState(
    typeof Notification !== 'undefined' ? Notification.permission : 'default',
  )

  const enableBrowser = async () => {
    if (typeof Notification === 'undefined') return
    const perm = await Notification.requestPermission()
    setBrowserPerm(perm)
    update({ channels: { ...settings.channels, browser: perm === 'granted' } })
  }

  return (
    <div className="space-y-5">
      <PageHeader
        title="Settings"
        description="Workspace, data source, notification and risk configuration. Changes persist locally."
        actions={
          <Badge variant="success" className="gap-1">
            <Check className="size-3.5" />
            Auto-saved
          </Badge>
        }
      />

      <div className="grid gap-5 lg:grid-cols-2">
        {/* General */}
        <Panel title="General">
          <div className="divide-y divide-border">
            <SettingRow
              label="Workspace name"
              description="Displayed across the terminal."
              htmlFor="ws-name"
              control={
                <Input
                  id="ws-name"
                  value={settings.workspaceName}
                  onChange={(e) => update({ workspaceName: e.target.value })}
                  className="w-56"
                />
              }
            />
            <SettingRow
              label="Base currency"
              description="Reporting currency for PnL."
              control={
                <Select value={settings.baseCurrency} onValueChange={(v) => update({ baseCurrency: v })}>
                  <SelectTrigger className="w-32">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="USD">USD</SelectItem>
                    <SelectItem value="EUR">EUR</SelectItem>
                    <SelectItem value="GBP">GBP</SelectItem>
                    <SelectItem value="INR">INR</SelectItem>
                  </SelectContent>
                </Select>
              }
            />
            <SettingRow
              label="Timezone"
              description="Used for session labels and charts."
              control={
                <Select value={settings.timezone} onValueChange={(v) => update({ timezone: v })}>
                  <SelectTrigger className="w-40">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="utc">UTC</SelectItem>
                    <SelectItem value="london">Europe/London</SelectItem>
                    <SelectItem value="ny">America/New_York</SelectItem>
                    <SelectItem value="mumbai">Asia/Kolkata</SelectItem>
                  </SelectContent>
                </Select>
              }
            />
          </div>
        </Panel>

        {/* Appearance */}
        <Panel title="Appearance">
          <div className="divide-y divide-border">
            <SettingRow
              label="Theme"
              description="Dark is the recommended terminal experience."
              control={
                <Select value={theme} onValueChange={(v) => { setTheme(v as 'dark' | 'light'); update({ theme: v as 'dark' | 'light' }) }}>
                  <SelectTrigger className="w-32">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="dark">Dark</SelectItem>
                    <SelectItem value="light">Light</SelectItem>
                  </SelectContent>
                </Select>
              }
            />
            <SettingRow
              label="Dense tables"
              description="Compact row height in the trade blotter."
              control={
                <Switch
                  checked={settings.denseTables}
                  onCheckedChange={(v) => update({ denseTables: v })}
                />
              }
            />
            <SettingRow
              label="Show heartbeat pulse"
              description="Animated status indicators."
              control={
                <Switch
                  checked={settings.heartbeatPulse}
                  onCheckedChange={(v) => update({ heartbeatPulse: v })}
                />
              }
            />
          </div>
        </Panel>

        {/* Data source */}
        <Panel title="Data Source">
          <div className="divide-y divide-border">
            <SettingRow
              label="Mode"
              description="Mock data or live backend API."
              control={
                <Badge variant={USE_MOCK ? 'warning' : 'success'}>
                  {USE_MOCK ? 'Mock data' : 'Live API'}
                </Badge>
              }
            />
            <SettingRow
              label="API base URL"
              description="Set VITE_API_BASE_URL to go live."
              htmlFor="api-url"
              control={
                <Input
                  id="api-url"
                  placeholder="http://localhost:8000/api"
                  value={settings.apiBaseUrl}
                  onChange={(e) => update({ apiBaseUrl: e.target.value })}
                  className="w-64"
                />
              }
            />
            <SettingRow
              label="Refresh interval"
              description="How often views auto-refresh."
              control={
                <Select
                  value={String(settings.refreshIntervalSec)}
                  onValueChange={(v) => update({ refreshIntervalSec: Number(v) })}
                >
                  <SelectTrigger className="w-32">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="5">5 seconds</SelectItem>
                    <SelectItem value="10">10 seconds</SelectItem>
                    <SelectItem value="30">30 seconds</SelectItem>
                    <SelectItem value="60">60 seconds</SelectItem>
                  </SelectContent>
                </Select>
              }
            />
          </div>
        </Panel>

        {/* Notification channels */}
        <Panel title="Notification Channels">
          <div className="divide-y divide-border">
            <ChannelRow
              icon={<Send className="size-4" />}
              label="Telegram"
              description="Push alerts to a Telegram chat."
              ready
              checked={settings.channels.telegram}
              onChange={(v) => update({ channels: { ...settings.channels, telegram: v } })}
            />
            <ChannelRow
              icon={<Bell className="size-4" />}
              label="Browser notifications"
              description={browserPerm === 'granted' ? 'Permission granted.' : 'Requires browser permission.'}
              ready
              checked={settings.channels.browser}
              onChange={(v) =>
                v && browserPerm !== 'granted'
                  ? enableBrowser()
                  : update({ channels: { ...settings.channels, browser: v } })
              }
            />
            <ChannelRow
              icon={<Mail className="size-4" />}
              label="Email"
              description="Daily digests and critical alerts."
              ready
              checked={settings.channels.email}
              onChange={(v) => update({ channels: { ...settings.channels, email: v } })}
            />
          </div>
        </Panel>

        {/* Notification rules */}
        <Panel title="Alert Rules">
          <div className="divide-y divide-border">
            <SettingRow
              label="Machine offline"
              control={
                <Switch
                  checked={settings.notifyMachineOffline}
                  onCheckedChange={(v) => update({ notifyMachineOffline: v })}
                />
              }
            />
            <SettingRow
              label="High CPU / RAM"
              control={
                <Switch
                  checked={settings.notifyHighResource}
                  onCheckedChange={(v) => update({ notifyHighResource: v })}
                />
              }
            />
            <SettingRow
              label="Broker disconnects"
              control={
                <Switch
                  checked={settings.notifyBrokerDisconnect}
                  onCheckedChange={(v) => update({ notifyBrokerDisconnect: v })}
                />
              }
            />
            <SettingRow
              label="Strategy crashes"
              control={
                <Switch
                  checked={settings.notifyStrategyCrash}
                  onCheckedChange={(v) => update({ notifyStrategyCrash: v })}
                />
              }
            />
          </div>
        </Panel>

        {/* Machine settings */}
        <Panel title="Machine Defaults">
          <div className="divide-y divide-border">
            <SettingRow
              label="Heartbeat timeout"
              description="Mark a host offline after this many seconds."
              control={
                <Select defaultValue="30">
                  <SelectTrigger className="w-32">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="15">15s</SelectItem>
                    <SelectItem value="30">30s</SelectItem>
                    <SelectItem value="60">60s</SelectItem>
                  </SelectContent>
                </Select>
              }
            />
            <SettingRow
              label="CPU alert threshold"
              description="Warn when sustained above this %."
              control={
                <Select defaultValue="85">
                  <SelectTrigger className="w-32">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="75">75%</SelectItem>
                    <SelectItem value="85">85%</SelectItem>
                    <SelectItem value="95">95%</SelectItem>
                  </SelectContent>
                </Select>
              }
            />
          </div>
        </Panel>
      </div>

      {/* Strategy defaults */}
      <Panel title="Strategy Defaults">
        <div className="grid gap-x-8 sm:grid-cols-2">
          <SettingRow
            label="Auto-restart on crash"
            description="Relaunch a strategy that exits unexpectedly."
            control={<Switch defaultChecked />}
          />
          <SettingRow
            label="Max daily loss per strategy"
            description="Halt a strategy after this loss."
            control={<Input defaultValue="2,500" className="w-32 text-right" />}
          />
          <SettingRow
            label="Max open positions"
            description="Cap concurrent positions per strategy."
            control={<Input defaultValue="6" className="w-32 text-right" />}
          />
          <SettingRow
            label="Kill switch"
            description="Flatten all positions on breach."
            control={<Switch defaultChecked />}
          />
        </div>
      </Panel>

      {/* Account / auth placeholder */}
      <Panel title="Account & Authentication" actions={<Badge variant="muted">Coming soon</Badge>}>
        <div className="flex flex-col items-start gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            <div className="rounded-lg bg-muted p-2.5 text-muted-foreground">
              <Lock className="size-5" />
            </div>
            <div>
              <p className="text-sm font-medium">Supabase Auth</p>
              <p className="text-xs text-muted-foreground">
                Authentication is architected but intentionally not enabled in this build.
              </p>
            </div>
          </div>
          <Button variant="outline" disabled>
            Connect Supabase
          </Button>
        </div>
        <Separator className="my-4" />
        <p className="text-xs text-muted-foreground">Build version v{APP_VERSION}</p>
      </Panel>
    </div>
  )
}

function ChannelRow({
  icon,
  label,
  description,
  ready,
  checked,
  onChange,
}: {
  icon: ReactNode
  label: string
  description: string
  ready?: boolean
  checked: boolean
  onChange: (value: boolean) => void
}) {
  return (
    <div className="flex items-center justify-between gap-4 py-3">
      <div className="flex min-w-0 items-center gap-3">
        <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground">
          {icon}
        </div>
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <p className="text-sm font-medium">{label}</p>
            {ready && (
              <Badge variant="success" className="text-[10px]">
                Ready
              </Badge>
            )}
          </div>
          <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>
        </div>
      </div>
      <Switch checked={checked} onCheckedChange={onChange} />
    </div>
  )
}
