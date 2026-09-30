// 表示用の書式

/** 日付を「2026/10/01」の形にする */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}/${pad(d.getMonth() + 1)}/${pad(d.getDate())}`
}

/** 日時を「10/01 14:05」の形にする */
export function formatDateTime(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getMonth() + 1)}/${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/** 分を「約1.9時間」「25分」の形にする */
export function formatMinutes(minutes: number): string {
  if (minutes < 60) return `${minutes}分`
  return `約${Math.round((minutes / 60) * 10) / 10}時間`
}
