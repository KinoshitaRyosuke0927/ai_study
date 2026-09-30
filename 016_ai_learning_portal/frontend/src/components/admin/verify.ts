// 作成者による検証:作成者の解答(と AI の模範解答)をブラウザで実行して、結果をサーバに送る
import { api } from '../../api/client'
import type { Problem, RunIn, VerifyResult } from '../../api/adminTypes'
import type { Dataset } from '../../api/types'
import { pythonRuntime } from '../../python/runtime'

/** 変数の残っていない実行コンテキストでコードを実行する */
async function runFresh(ctx: string, code: string, datasets: Dataset[], test?: string): Promise<RunIn> {
  await pythonRuntime.reset(ctx)
  const res = await pythonRuntime.run(ctx, code, datasets, test)
  return { output: res.output, error: res.error ?? (res.test_passed === false ? res.test_message : null), test_passed: res.test_passed }
}

/**
 * 保存済みのコード問題を検証する
 * - 作成者の解答と AI の模範解答(あれば)を、それぞれ別の実行コンテキストで実行する
 * - テストコード採点の問題は、テストも実行する
 */
export async function verifyProblem(problem: Problem, datasets: Dataset[]): Promise<VerifyResult & { authorRun: RunIn }> {
  const test = problem.grading === 'test' ? problem.test_code : undefined
  const author = await runFresh(`verify-author-${problem.id}`, problem.author_answer, datasets, test)
  // テストに落ちただけの場合はエラー扱いにせず、サーバで判定させる
  const authorRun: RunIn = { ...author, error: problem.grading === 'test' && author.test_passed === false ? null : author.error }
  const ai = problem.ai_model_answer.trim()
    ? await runFresh(`verify-ai-${problem.id}`, problem.ai_model_answer, datasets, test)
    : null
  const result = await api.admin.verify(problem.id, authorRun, ai)
  return { ...result, authorRun }
}
