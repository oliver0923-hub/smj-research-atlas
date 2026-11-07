# REVIEW_GUIDE

取得合法全文，新增逐篇 variable_id、paper_id、construct、role、proxy 與來源 locator/URL/hash。formula、lag、sample 不清楚時填 null 並標記 missingness。不可由 abstract 自動升為 measurement_verified。LLM 只能提草稿；human_reviewed 需實際人工 reviewer 與日期。PR 應附最短可核查摘述與頁碼，不上傳私人 PDF。執行 validate/build/tests 後人工核對 primary source 再合併。
