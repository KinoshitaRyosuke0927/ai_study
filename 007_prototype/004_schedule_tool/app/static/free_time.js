/**
 * 空き時間の計算(画面とテストの両方から使う)
 *
 * 予定の形式(サーバの /api/schedule の events の1件):
 *   { uid, start_date, end_date, start_time: "HH:MM" | null, end_time, all_day, ... }
 * 条件(conditions):
 *   { businessStart: "09:00", businessEnd: "18:00", slotMinutes: 30,
 *     lunchStart: "12:00", lunchEnd: "13:00", minDurationMinutes: 60,
 *     requiredCount: 必要な人数, excludeHolidays: true }
 * blockingKeys: 「埋まっている扱い」にした時刻なし予定のキー(eventKey の値)の Set
 */
(function (root) {
  "use strict";

  /**
   * "HH:MM" を0時からの分に変換する
   * @param {string} hhmm 時刻
   * @returns {number} 分
   */
  function toMinutes(hhmm) {
    const [h, m] = hhmm.split(":").map(Number);
    return h * 60 + m;
  }

  /**
   * 分を "HH:MM" に変換する
   * @param {number} minutes 0時からの分
   * @returns {string} 時刻
   */
  function toHHMM(minutes) {
    const h = Math.floor(minutes / 60);
    const m = minutes % 60;
    return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
  }

  /**
   * 予定を一意に表すキー(時刻なし予定の「埋まっている扱い」の切り替えに使う)
   * @param {object} ev 予定
   * @returns {string} キー
   */
  function eventKey(ev) {
    return [ev.uid, ev.sid || "", ev.start_date, ev.end_date, ev.start_time || "", ev.title || ""].join("|");
  }

  /**
   * 1日分の判定の枠(業務時間を刻みで区切り、昼休みにかかる枠を除く)を作る
   * @param {object} c 条件
   * @returns {{start:number,end:number}[]} 枠の一覧
   */
  function buildSlots(c) {
    const slots = [];
    const bs = toMinutes(c.businessStart);
    const be = toMinutes(c.businessEnd);
    const ls = toMinutes(c.lunchStart);
    const le = toMinutes(c.lunchEnd);
    for (let s = bs; s + c.slotMinutes <= be; s += c.slotMinutes) {
      const e = s + c.slotMinutes;
      // 昼休みに少しでもかかる枠は候補にしない
      if (s < le && e > ls) continue;
      slots.push({ start: s, end: e });
    }
    return slots;
  }

  /**
   * 1日分の、枠ごとの空いているメンバーを求める
   * @param {string} date 日付 "YYYY-MM-DD"
   * @param {string[]} memberIds 対象メンバーのID
   * @param {object[]} events 予定の一覧
   * @param {object} c 条件
   * @param {Set<string>} blockingKeys 埋まっている扱いにした時刻なし予定のキー
   * @returns {{start:number,end:number,free:string[],busy:string[]}[]} 枠ごとの結果
   */
  function computeDaySlots(date, memberIds, events, c, blockingKeys) {
    // その日の予定をメンバーごとに分ける(時刻あり / 埋まっている扱いの時刻なし)
    const timed = {};
    const blockedAllDay = new Set();
    memberIds.forEach((uid) => { timed[uid] = []; });
    events.forEach((ev) => {
      if (!(ev.uid in timed) || ev.start_date > date || ev.end_date < date) return;
      if (ev.all_day) {
        if (blockingKeys && blockingKeys.has(eventKey(ev))) blockedAllDay.add(ev.uid);
      } else {
        timed[ev.uid].push({ start: toMinutes(ev.start_time), end: toMinutes(ev.end_time) });
      }
    });

    // 枠ごとに、予定と少しでも重なっているメンバーを「空いていない」とする
    return buildSlots(c).map((slot) => {
      const free = [];
      const busy = [];
      memberIds.forEach((uid) => {
        const isBusy = blockedAllDay.has(uid) || timed[uid].some((t) => t.start < slot.end && t.end > slot.start);
        (isBusy ? busy : free).push(uid);
      });
      return { ...slot, free, busy };
    });
  }

  /**
   * 空き時間の候補を求める。連続する枠のうち、同じ顔ぶれで必要な人数以上が通して空いている時間帯をまとめる
   * @param {{date:string,holiday:boolean}[]} days 期間の日付
   * @param {string[]} memberIds 対象メンバーのID
   * @param {object[]} events 予定の一覧
   * @param {object} c 条件
   * @param {Set<string>} blockingKeys 埋まっている扱いにした時刻なし予定のキー
   * @returns {{date:string,start:string,end:string,minutes:number,free:string[]}[]} 候補の一覧
   */
  function findCandidates(days, memberIds, events, c, blockingKeys) {
    const candidates = [];
    const required = Math.max(1, Math.min(c.requiredCount, memberIds.length));

    days.forEach((day) => {
      if (c.excludeHolidays && day.holiday) return;
      const slots = computeDaySlots(day.date, memberIds, events, c, blockingKeys);

      // 候補を1件確定する(必要な長さに満たないものは捨てる)
      let run = null;
      const close = () => {
        if (run && run.end - run.start >= c.minDurationMinutes) {
          candidates.push({
            date: day.date,
            start: toHHMM(run.start),
            end: toHHMM(run.end),
            minutes: run.end - run.start,
            free: memberIds.filter((uid) => run.free.has(uid)),
          });
        }
        run = null;
      };

      slots.forEach((slot) => {
        const slotFree = new Set(slot.free);
        if (run && run.end === slot.start) {
          // 前の枠と時間が続いている場合: 通して空いている顔ぶれが必要な人数以上なら延ばす
          const both = new Set([...run.free].filter((uid) => slotFree.has(uid)));
          if (both.size >= required) {
            run.end = slot.end;
            run.free = both;
            return;
          }
        }
        // 続かない(昼休みをはさむ・顔ぶれが足りない)場合は、ここで区切って新しく始める
        close();
        if (slotFree.size >= required) run = { start: slot.start, end: slot.end, free: slotFree };
      });
      close();
    });
    return candidates;
  }

  const api = { toMinutes, toHHMM, eventKey, buildSlots, computeDaySlots, findCandidates };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.FreeTime = api;
})(typeof window !== "undefined" ? window : globalThis);
