import dayjs, { type Dayjs } from 'dayjs'
import timezone from 'dayjs/plugin/timezone'
import utc from 'dayjs/plugin/utc'

import { appConfig } from '../config/env'

dayjs.extend(utc)
dayjs.extend(timezone)

export function currentBusinessMonth(): Dayjs {
  return dayjs().tz(appConfig.businessTimezone).startOf('month')
}

export function formatBusinessDateTime(value: string): string {
  return dayjs(value).tz(appConfig.businessTimezone).format('YYYY-MM-DD HH:mm')
}

export function toBusinessDateTimeIso(value: Dayjs): string {
  return dayjs
    .tz(value.format('YYYY-MM-DD HH:mm:ss'), appConfig.businessTimezone)
    .toISOString()
}

export function toBusinessDayRange(
  start: Dayjs,
  end: Dayjs,
): { plannedFrom: string; plannedTo: string } {
  const plannedFrom = dayjs.tz(
    start.format('YYYY-MM-DD'),
    appConfig.businessTimezone,
  )
  const plannedTo = dayjs
    .tz(end.format('YYYY-MM-DD'), appConfig.businessTimezone)
    .add(1, 'day')
  return {
    plannedFrom: plannedFrom.toISOString(),
    plannedTo: plannedTo.toISOString(),
  }
}

export function businessDateRangeFromUtc(
  plannedFrom: string | null,
  plannedTo: string | null,
): [Dayjs, Dayjs] | null {
  if (!plannedFrom || !plannedTo) {
    return null
  }
  return [
    dayjs(plannedFrom).tz(appConfig.businessTimezone),
    dayjs(plannedTo).tz(appConfig.businessTimezone).subtract(1, 'day'),
  ]
}
