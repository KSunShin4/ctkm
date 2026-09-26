import test from "node:test"
import assert from "node:assert/strict"
import {readFile} from "node:fs/promises"
const s=await readFile(new URL("./App.jsx",import.meta.url),"utf8")
test("ctkm integrates shared contextual help and assistant",()=>{for(const x of ["HelpTip","MODULE_HELP","Mascot","GuideBubble","assistantComponentCss","helpTipCss"])assert.match(s,new RegExp(x))})
test("mapping confirmation remains explicit and source-preserving",()=>{assert.match(s,/Xác nhận và tiếp tục job/);assert.match(s,/giá trị nguồn không bị sửa/);assert.match(s,/không sử dụng/)})
test("ctkm help preserves POG and action contract",()=>{assert.match(s,/POG chỉ cung cấp vị trí kệ/);assert.match(s,/không quyết định Gắn, Tháo hay Chờ/);assert.match(s,/Không dùng việc thiếu POG để tự đổi quyết định Gắn\/Tháo/)})
test("overlap help does not imply deduplication",()=>{assert.match(s,/Cảnh báo trùng thời gian/);assert.match(s,/không tự xoá hay gộp bản ghi nguồn/)})
test("tem r help describes displayed-value mapping without source mutation",()=>{assert.match(s,/Tem R/);assert.match(s,/giá trị đang hiển thị/);assert.match(s,/không thay đổi dữ liệu nguồn/)})
