import { useMemo, useState } from 'react'
import type { AvailabilityDay } from '../api/planDetailApi'
import './AvailabilityCalendar.css'

type AvailabilityCalendarProps = {
  // 当日から一定日数分の空室状況(日付昇順)。カレンダーの移動可能範囲もこのデータから決まる。
  availability: AvailabilityDay[]
  selectedDate: string | null
  onSelectDate: (date: string) => void
}

const WEEKDAY_LABELS = ['日', '月', '火', '水', '木', '金', '土']

function toMonthKey(year: number, month: number) {
  return `${year}-${String(month + 1).padStart(2, '0')}`
}

function toDateKey(year: number, month: number, day: number) {
  return `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`
}

// プラン詳細画面の空室状況エリアに表示する月カレンダー。
// availabilityで渡された日付のみ予約可否を判定でき、それ以外の日付(範囲外)は選択不可として表示する。
function AvailabilityCalendar({ availability, selectedDate, onSelectDate }: AvailabilityCalendarProps) {
  // 日付文字列(YYYY-MM-DD)をキーに空室状況をすぐ引けるようにしておく
  const availabilityMap = useMemo(() => {
    const map = new Map<string, boolean>()
    availability.forEach((day) => map.set(day.date_of_stay, day.is_available))
    return map
  }, [availability])

  const firstDate = availability.length > 0 ? new Date(availability[0].date_of_stay) : new Date()
  const lastDate = availability.length > 0 ? new Date(availability[availability.length - 1].date_of_stay) : new Date()
  const minMonthKey = toMonthKey(firstDate.getFullYear(), firstDate.getMonth())
  const maxMonthKey = toMonthKey(lastDate.getFullYear(), lastDate.getMonth())

  const [viewYear, setViewYear] = useState(firstDate.getFullYear())
  const [viewMonth, setViewMonth] = useState(firstDate.getMonth())

  const currentMonthKey = toMonthKey(viewYear, viewMonth)
  const canGoPrev = currentMonthKey > minMonthKey
  const canGoNext = currentMonthKey < maxMonthKey

  function goToPrevMonth() {
    const prev = new Date(viewYear, viewMonth - 1, 1)
    setViewYear(prev.getFullYear())
    setViewMonth(prev.getMonth())
  }

  function goToNextMonth() {
    const next = new Date(viewYear, viewMonth + 1, 1)
    setViewYear(next.getFullYear())
    setViewMonth(next.getMonth())
  }

  const firstWeekday = new Date(viewYear, viewMonth, 1).getDay()
  const daysInMonth = new Date(viewYear, viewMonth + 1, 0).getDate()

  // 月初の曜日に合わせて空セルを入れたのち、当月の日付を並べる
  const cells: (string | null)[] = [
    ...Array.from({ length: firstWeekday }, () => null),
    ...Array.from({ length: daysInMonth }, (_, i) => toDateKey(viewYear, viewMonth, i + 1)),
  ]

  return (
    <div className="availability-calendar">
      <div className="calendar-header">
        <button type="button" className="calendar-nav" onClick={goToPrevMonth} disabled={!canGoPrev}>
          ＜
        </button>
        <div className="calendar-title">
          {viewYear}年{viewMonth + 1}月
        </div>
        <button type="button" className="calendar-nav" onClick={goToNextMonth} disabled={!canGoNext}>
          ＞
        </button>
      </div>
      <div className="calendar-grid">
        {WEEKDAY_LABELS.map((label) => (
          <div className="calendar-weekday" key={label}>
            {label}
          </div>
        ))}
        {cells.map((dateKey, index) => {
          if (!dateKey) return <div className="calendar-cell empty" key={`empty-${index}`} />

          const isKnown = availabilityMap.has(dateKey)
          const isAvailable = availabilityMap.get(dateKey) === true
          const isSelected = dateKey === selectedDate
          const day = Number(dateKey.slice(-2))

          return (
            <button
              type="button"
              key={dateKey}
              className={`calendar-cell${!isKnown ? ' unknown' : isAvailable ? ' available' : ' unavailable'}${isSelected ? ' selected' : ''}`}
              onClick={() => onSelectDate(dateKey)}
              disabled={!isKnown || !isAvailable}
            >
              {day}
            </button>
          )
        })}
      </div>
      <div className="calendar-legend">
        <span className="legend-item">
          <span className="legend-swatch available" />予約可
        </span>
        <span className="legend-item">
          <span className="legend-swatch unavailable" />満室
        </span>
      </div>
    </div>
  )
}

export default AvailabilityCalendar
