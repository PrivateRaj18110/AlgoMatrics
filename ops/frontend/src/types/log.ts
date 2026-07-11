/** The log streams surfaced by the log viewer. */
export type LogSource =
  | 'application'
  | 'strategy'
  | 'python'
  | 'broker'
  | 'database'
  | 'system'

export type LogLevel = 'debug' | 'info' | 'warn' | 'error'

/** A single structured log line. */
export interface LogEntry {
  id: string
  /** ISO timestamp. */
  time: string
  source: LogSource
  level: LogLevel
  /** Logger / module name. */
  logger: string
  message: string
}
