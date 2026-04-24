# Phân tích sâu: `langchain-ai/open_deep_research` vs dự án `chat-agents`

> Nguồn: https://github.com/langchain-ai/open_deep_research
> Trạng thái repo tại thời điểm khảo sát (2026-04-23): 11.2k⭐, MIT license, maintainer Lance Martin, vừa cập nhật trong ngày.
> Viết tắt trong tài liệu: **ODR** = `open_deep_research`, **chat-agents** = dự án hiện tại.

---

## Mục lục

1. ODR thực chất là gì và hoạt động thế nào
2. So sánh trực tiếp với `chat-agents`
3. Những gì nên copy trực tiếp (rủi ro thấp, giá trị cao)
4. Những gì nên học và điều chỉnh (copy ý tưởng, không copy code)
5. Những gì KHÔNG nên copy
6. Năm bài học cần "ngấm" vào team
7. Thứ tự triển khai đề xuất

---

## 1. ODR thực chất là gì và hoạt động thế nào

### 1a. Hình dáng ứng dụng

ODR **chỉ là một LangGraph graph, không có gì khác** — không FastAPI, không web UI, không lớp SSE. Entry point được khai báo trong `langgraph.json`:

```json
"graphs": { "Deep Researcher": "./src/open_deep_research/deep_researcher.py:deep_researcher" }
```

Chạy bằng `langgraph dev` và tương tác qua LangGraph Studio hoặc gọi programmatic. Toàn bộ "sản phẩm" chỉ gồm ~30KB `deep_researcher.py` + ~33KB `utils.py` + ~21KB `prompts.py`.

### 1b. Graph (main / supervisor / researcher)

Ba graph xếp chồng với **tách biệt state nghiêm ngặt** — kênh messages không rò rỉ giữa các tầng:

```
   [AgentState]        clarify_with_user → write_research_brief → research_supervisor → final_report_generation
                                                                          │
                                                                          ▼
 [SupervisorState]                    supervisor ↔ supervisor_tools (vòng lặp, có cap iteration)
                                                         │ ConductResearch tool call fan-out
                                                         ▼
 [ResearcherState]              researcher ↔ researcher_tools (loop) → compress_research
```

Các node chính & chức năng:

| Node | Đọc | Ghi | Vai trò |
|---|---|---|---|
| `clarify_with_user` | `messages` | `messages` | Chỉ hỏi lại user **khi cần thiết**, dùng structured output `ClarifyWithUser{need_clarification, question, verification}`. Quy tắc cứng: nếu đã hỏi một lần trong history thì không hỏi lại. |
| `write_research_brief` | `messages` | `research_brief`, `supervisor_messages` | Tóm chat thành một brief nghiên cứu độc lập (structured output `ResearchQuestion`). Tách supervisor khỏi ngữ cảnh chat lộn xộn. |
| `supervisor` | `SupervisorState` | `supervisor_messages`, `research_iterations++` | Planner với 3 tool: `ConductResearch`, `ResearchComplete`, `think_tool`. **Không tự đi search.** |
| `supervisor_tools` | tool calls | `raw_notes`, `notes` | Chạy researcher song song qua `asyncio.gather(*[researcher_subgraph.ainvoke(...)])`, giới hạn bởi `max_concurrent_research_units`. Vượt cap → trả error message cho supervisor. |
| `researcher` | topic | `researcher_messages`, `tool_call_iterations++` | ReAct loop với search tool + `think_tool`. |
| `researcher_tools` | tool calls | `researcher_messages` | Gọi Tavily/OpenAI/Anthropic web search hoặc MCP tools. |
| `compress_research` | toàn bộ researcher messages | `compressed_research`, `raw_notes` | Nén nội dung researcher dài dòng thành tóm tắt dày đặc **nhưng không bỏ fact** ("DO NOT summarize, just reformat"). Retry 3 lần với truncation 10% khi lỗi token-limit. |
| `final_report_generation` | `research_brief`, `notes` | `final_report`, `messages` | Gọi writer lớn một lần; retry 3 lần với truncation char (≈4× token cap mỗi lần). |

### 1c. Các cơ chế thực sự làm nên hiệu quả

Đây mới là những nước đi kỹ thuật không hiển nhiên — quan trọng hơn cả hình dáng graph:

1. **Bốn LLM chuyên biệt, không phải một.** `configuration.py` khai báo `summarization_model`, `research_model`, `compression_model`, `final_report_model` độc lập (mỗi model có `*_max_tokens` riêng). Mặc định là `gpt-4.1` cho reasoning + `gpt-4.1-mini` cho summarization — rẻ ở nơi context nhiễu, mạnh ở nơi cần suy luận.
2. **Structured output dùng như tool.** `ConductResearch` và `ResearchComplete` là Pydantic models bind làm tool nhưng **không chạy Python nào**. Chúng chỉ là quyết định có kiểu (typed decisions) mà supervisor phát ra. Mọi branching logic (clarify, brief, summary) đều dùng `.with_structured_output(Model).with_retry(stop_after_attempt=n)`.
3. **`think_tool` — phản tỉnh có chủ đích.** Tool no-op với mục đích ép model viết ra "phân tích khoảng trống" giữa các bước ReAct. Prompt bảo *"think trước và sau mỗi ConductResearch"* — đây là cách ODR buộc model parallel-tool-call phải reason tuần tự.
4. **Raw notes vs compressed notes là hai state channel riêng.** `raw_notes` là sự thật thô; `notes` là những gì writer cuối thấy. Báo cáo cuối chính xác vì writer thấy view sạch, không phải message stream thô.
5. **`override_reducer` trong `state.py`.** Một đoạn quan trọng:
   ```python
   def override_reducer(current, new):
       if isinstance(new, dict) and new.get("type") == "override":
           return new["value"]
       return operator.add(current, new)
   ```
   Mặc định là tích luỹ (list+list); truyền `{"type":"override","value":X}` sẽ reset channel. Đây là cách `compress_research` xoá sạch chatter researcher giữa chừng mà không cần hack.
6. **Phục hồi token-limit, không né tránh.** `is_token_limit_exceeded()` detect overflow string theo từng provider; `MODEL_TOKEN_LIMITS` hardcode ~40 model ceilings; compress/final-report nodes có graceful truncation retry thay vì cầu trời.
7. **Fan-out song song bằng asyncio thuần.** Không dùng `Send()` API — chỉ `asyncio.gather()` trên các researcher subgraph invocation. Đơn giản, bớt gắn chặt với LangGraph.
8. **Summarize webpage là một call model riêng với hard timeout 60 giây.** Nếu summarize hang/fail, trả về nội dung gốc kèm warning. Không để một URL chập chờn làm chết cả run.
9. **Cap cứng khắp nơi.** `max_researcher_iterations=6`, `max_concurrent_research_units=5`, `max_react_tool_calls=10`. Không có vòng lặp vô hạn.
10. **Config điều khiển bằng UI.** Metadata `x_oap_ui_config` trong mỗi `Field()` chỉ cho Open Agent Platform cách render slider/select/text — config nằm trong code nhưng non-dev vẫn chỉnh được.
11. **MCP được hỗ trợ gốc.** `load_mcp_tools()`, OAuth token exchange qua Supabase, auth-error translation. Thêm data source mới = register MCP server.
12. **Eval harness được commit vào repo.** `tests/run_evaluate.py` chạy Deep Research Bench qua LangSmith, `extract_langsmith_data.py` tạo JSONL sẵn sàng submit leaderboard, README công bố số liệu thực với chi phí. Evaluation được đối xử như surface bậc nhất của sản phẩm.

> **★ Insight**
> - "Bộ não" của ODR không phải topology graph — mà là **kênh notes hai lớp** (`raw_notes` / `notes`) + **`override_reducer`**. Hai thứ này kết hợp cho phép nhiều researcher chạy song song, gom raw findings không giới hạn, rồi thay thế nguyên tử (atomic) bằng view nén cho writer. Hầu hết repo "deep research" khác gộp mọi thứ vào một message list duy nhất rồi xin lỗi vì context phình.
> - `think_tool` là thủ thuật ít được đánh giá đúng: không cần chống lại xu hướng emit parallel tool calls của model — cứ thêm một *reflection tool* và ghi trong prompt "dùng trước/sau mỗi search". Tool không tốn gì để chạy, nhưng buộc model serialize reasoning vào message log.
> - Tách `clarify_with_user` + `write_research_brief` thành hai node riêng giúp supervisor làm việc với một "research brief" chuẩn, sạch sẽ thay vì chat lộn xộn của user — mọi model downstream đều nhìn cùng một mục tiêu đã chưng cất.

---

## 2. So sánh trực tiếp với `chat-agents`

| Khía cạnh | ODR | chat-agents | Kết luận |
|---|---|---|---|
| Agent framework | LangGraph thuần, tự build | `deepagents` trên LangGraph (sub-agents qua `task` tool, virtual FS) | Khác tầng trừu tượng |
| Hình dáng graph | 3 subgraph xếp chồng (main/supervisor/researcher) | 1 `create_deep_agent(...)` phẳng với 2 SubAgent | ODR rõ ràng hơn; chat-agents khai báo hơn |
| Song song | `asyncio.gather` giữa các researcher, cap 5 | Tuần tự — `deepagents` chạy subagents qua `task` tool, từng cái một | **ODR thắng về wall-clock** |
| Vai trò LLM | 4 model chuyên biệt (research, summarization, compression, writer) | 2 model (main + fast cho subagents) | **ODR thắng ở dial cost/quality** |
| Prompts | Python string templates với `.format()` | Markdown files + version registry + per-request overrides | **chat-agents thắng về iteration/A-B** |
| Clarification | Node cổng đầu tiên với structured output | Thiếu | ODR thắng |
| Research brief | Node riêng distill chat → brief | Thiếu; main prompt nhận thẳng câu hỏi | ODR thắng |
| Reflection | `think_tool` gắn sẵn | Thiếu | ODR thắng |
| Mô hình notes | `raw_notes` + `notes` + `override_reducer` | Message stream + virtual FS (`draft.md`) | Cách tiếp cận khác; chat-agents file-backed, ODR channel-backed |
| Token-limit | Detect + retry với truncation + bảng theo model | Không có (fail open) | ODR thắng |
| Summarize webpage | Mini-model với timeout 60s | Kết quả Tavily thô truyền thẳng | ODR thắng |
| Tín hiệu compression | Hành động node thực | Heuristic suy ra từ token delta + fallback "synthetic compression" trong router | chat-agents thông minh nhưng phòng thủ; ODR chủ động |
| MCP | Built-in | Không | ODR thắng |
| Final-report fallback | Không cần — writer node tự đứng | Fallback `draft.md` khi stream < 200 chars (`routers/research.py:87-101`) | chat-agents là *workaround* cho vấn đề ODR không gặp |
| HTTP transport | Không (chỉ Studio/Platform) | FastAPI + SSE + typed event map | **chat-agents thắng ở mức deployable** |
| Frontend | Không | Next.js 14 dashboard với `SSEEventMap` có type | chat-agents thắng |
| Config surface | Pydantic `Configuration` + metadata `x_oap_ui_config` | `pydantic-settings` env only | ODR polish hơn cho multi-tenant; chat-agents đơn giản hơn |
| Eval | Deep Research Bench harness + số liệu LangSmith công khai | Không có | **ODR thắng đậm** |
| Prompt versioning | Không có | File-backed registry + overrides | **chat-agents thắng** |

> **★ Insight**
> - Fallback `MIN_STREAM_REPORT_CHARS` trong `apps/api/app/routers/research.py:27-28` là tín hiệu rõ rệt: main model đôi khi ghi báo cáo vào virtual FS thay vì stream ra, và ta đang phục hồi bằng cách đọc `draft.md`. ODR né hoàn toàn loại bug này vì writer là **node riêng** chỉ chạy sau khi research đã compress. Công việc duy nhất của writer là emit báo cáo — nó không thể "quên" và save vào disk.
> - `ChunkMapper` đang làm nặng post-hoc inference từ ba stream mode (`values` + `messages` + `updates`) để tái hiện điều đã xảy ra. ODR không cần vì state writes tường minh theo từng node và runtime surface là LangGraph Studio chứ không phải custom UI. Đây là cái giá thực của việc tự build frontend — ngược lại cũng đúng: ODR sẽ cần cả layer streaming này để ship như một sản phẩm.

---

## 3. Những gì nên copy trực tiếp (rủi ro thấp, giá trị cao)

Các mục sau vừa khớp kiến trúc hiện tại mà không đổi framework:

1. **`think_tool` (~10 dòng).** Khai báo một Python function no-op đăng ký làm tool, gắn vào main agent + researcher subagent, cập nhật prompt: *"gọi `think_tool` trước và sau mỗi search để liệt kê điều đã biết và khoảng trống còn lại."* Chi phí: 1 file + 2 prompt edits. Kỳ vọng: giảm search thừa, synthesis tốt hơn.
2. **Clarification gate.** Trước khi `build_research_agent()` chạy, gọi một LLM nhẹ với structured output `ClarifyWithUser{need_clarification, question, verification}`. Nếu cần làm rõ, emit SSE event mới `clarification_requested` và end stream; nếu không thì tiếp tục. Thêm ~50 dòng vào router + 1 event type mới trong `events.py` + `SSEEventMap`.
3. **Distill research-brief.** Cùng pattern — một call structured-output tạo brief 1 đoạn văn, inject vào `agent.astream()` thay vì `payload.question` thô. Giúp tách chat noise khỏi mục tiêu của supervisor.
4. **Detect token-limit + compression retry.** Port `is_token_limit_exceeded()` và `MODEL_TOKEN_LIMITS` nguyên văn từ `utils.py`. Bọc call critic/final-report bằng retry cắt `draft.md` ~10-20% khi fail. Hiện tại virtual FS 200K tokens sẽ nổ ngầm — cơ chế này làm nó phục hồi được.
5. **Summarize webpage trước khi kết quả Tavily đi vào LLM.** Hiện `internet_search` trả payload Tavily thô. Thêm một bước summarize rẻ (`gpt-4o-mini`/`claude-haiku-4-5`) mỗi kết quả với timeout 60s. Giảm đáng kể input tokens trong các run dài.
6. **Chuyên biệt hoá model theo role trong `llm_factory.py`.** Hiện đã có `get_llm()` + `get_fast_llm()`. Thêm `get_summarizer_llm()` và `get_writer_llm()` trỏ model ID qua settings. Dù cùng trỏ một model hôm nay, seam này có giá trị cho tương lai.
7. **Cap cứng là settings, không phải "lời thỉnh cầu" trong prompt.** `max_searches_per_researcher`, `max_subagent_invocations_per_run`, `max_total_tokens_per_run`. Enforced trong chunk mapper hoặc wrapper quanh agent. Prompt hiện nói "2-4 searches" nhưng model có thể phớt lờ; cap từ settings có răng.

---

## 4. Những gì nên học và điều chỉnh (copy ý tưởng, không copy code)

Các mục sau cần suy nghĩ lại một chút vì lớp trừu tượng của chat-agents (`deepagents` + virtual FS) khác LangGraph thuần của ODR:

1. **Tách raw vs compressed notes → ánh xạ sang virtual FS.** Dùng `findings/*.md` cho output researcher thô và chỉ `brief.md` + `outline.md` cho writer. Dặn writer subagent chỉ đọc file đã nén. Đây là bản VFS của kênh state hai lớp của ODR.
2. **Song song.** `deepagents` tuần tự hoá subagent. Hai cách để có research song song:
   - **(A) Bỏ `deepagents` ở pha research** và dùng LangGraph thuần với `asyncio.gather` như ODR. Giữ phần còn lại của stack.
   - **(B) Fan-out bên trong một researcher subagent** bằng cách cấp cho nó một tool batch-search dùng `asyncio.gather` chạy N query Tavily trong một call.
   Option B ít xâm lấn hơn và nhiều khả năng đủ cho workload hiện tại.
3. **Eval harness.** Đừng adopt Deep Research Bench gốc — quá đắt ($45-$200/run). Thay vào đó, steal *pattern*: một `tests/e2e/run_eval.py` chạy tập vàng nhỏ (10-20 câu hỏi), chấm report bằng LLM judge, ghi JSONL điểm. Kèm GitHub Action comment score delta lên PR nào chạm `prompts/`. Đây là cách biến prompt version registry thành nền thí nghiệm có kiểm soát chất lượng.
4. **Định dạng prompt.** Cách dùng Markdown-file-per-version tốt hơn Python strings của ODR cho iteration. Nhưng prompt ODR giàu *reasoning* — có `{date}`, `{max_concurrent}`, `{max_researcher_iterations}`, heuristic delegation tường minh ("bias sang single agent trừ khi parallelize rõ ràng"). Nâng prompts thành Jinja2 template để inject settings và state hints live. Giữ file format, thêm variable substitution.
5. **`override_reducer` cho LangGraph state.** Nếu có ngày bỏ `deepagents` (xem mục 2A), copy reducer này nguyên văn. 6 dòng, giải quyết bài toán state-merge thực cho checkpointer-backed runs.
6. **UI-config metadata cho prompt registry.** `x_oap_ui_config` của ODR cho OAP cách render form. Prompt registry của chat-agents có thể surface metadata tương tự — per-prompt-version `description`, `tags`, `recommended_for` — và Next.js dashboard có thể render sidebar "Prompt settings" cho user chọn version mà không phải sửa `active.yaml` thủ công.
7. **MCP.** Không cần hôm nay (Tavily là nguồn duy nhất), nhưng đáng nhớ seam. Nếu thêm PubMed, arXiv, docs nội bộ — dùng `langchain-mcp-adapters` thay vì tự viết tool cho từng nguồn.

---

## 5. Những gì KHÔNG nên copy

- Tư thế **no-frontend** của ODR. LangGraph Studio là dev tool; Next.js dashboard là sản phẩm. Giữ nguyên.
- **Bỏ hẳn `deepagents`.** Chỉ làm nếu parallelism hoặc custom state reducer trở thành load-bearing. Nó cho virtual FS + subagent orchestration miễn phí.
- **Python string-template prompts.** Cách versioned markdown của chat-agents chặt chẽ hơn cho iteration và A/B.
- **Bỏ layer SSE/chunk-mapper.** Đó là surface sản phẩm. Làm vững hơn, không thay thế.

---

## 6. Năm bài học cần "ngấm"

1. **Một node, một trách nhiệm.** ODR tách "quyết định research" / "chọn brief" / "research" / "compress" / "viết" thành các node riêng với state writes tường minh. Đây là lý do hành vi auditable và failure recoverable được. Main prompt của chat-agents hiện làm bước 1 + 4 + 5 của flow ODR trong **một** call LLM — đó là lý do cần fallback `draft.md`.
2. **Dùng model rẻ nhất mà vẫn chạy cho mỗi bước.** Summarize và compress không cần cùng ngân sách reasoning như plan hay write. Tạo seam ngay bây giờ, kể cả nếu hôm nay tất cả thu về cùng một model.
3. **Structured output + retry > free-form + parsing.** Mọi quyết định branching trong ODR là Pydantic model. Của chat-agents hầu hết chưa. Retrofit pattern này trả lãi kép về reliability.
4. **Fail gracefully khi token-limit.** Detect + truncate + retry hơn "cầu cho vừa". Riêng bảng `MODEL_TOKEN_LIMITS` đã đáng port.
5. **Evaluation là infrastructure, không phải afterthought.** ODR ship harness, số công khai, chi phí per-model trong README. Prompt versioning của chat-agents hay nhưng không có bảo vệ — không có cách biết `main/v3.md` có tốt hơn `v2` hay không. Eval harness là nửa còn lại.

---

## 7. Thứ tự triển khai đề xuất

Để có đòn bẩy cao nhất với thay đổi code ít nhất, làm theo thứ tự:

1. Thêm `think_tool` (nhỏ, lên chất lượng ngay).
2. Thêm lớp summarize-webpage trong `search_tool.py` (tiết kiệm token lớn).
3. Tách `llm_factory.py` thành 3-4 role (không đổi hành vi, mở đường tune sau).
4. Thêm node clarification + research-brief (loại bỏ gốc rễ của hack `draft.md` fallback).
5. Port token-limit detection + compression retry (thắng về resilience).
6. Build eval harness nhỏ (10 câu hỏi vàng, LLM judge, JSONL output).
7. (Tuỳ chọn, lớn hơn) Thêm parallel research qua `asyncio.gather` trong batch-search tool.

Mục 1-3 có thể land thành các PR nhỏ riêng trong hôm nay. Mục 4-5 là change phối hợp — chắc cần một branch "research pipeline v2".

---

## Phụ lục A: So sánh phụ thuộc

**ODR (`pyproject.toml`)** — đa provider mạnh:
- `langchain-openai`, `langchain-anthropic`, `langchain-deepseek`, `langchain-groq`, `langchain-google-vertexai`, `langchain-google-genai`, `langchain-aws`
- `langchain-mcp-adapters` (MCP gốc)
- Search: `langchain-tavily`, `exa-py`, `duckduckgo-search`, `linkup-sdk`, `arxiv`, `pymupdf`
- `supabase` (OAuth cho MCP)
- `langsmith` (eval tracing)

**chat-agents** — focus hơn:
- `fastapi`, `uvicorn`, `sse-starlette`
- `deepagents` (hơn LangGraph thuần)
- `langchain-anthropic`, `langchain-openai`, `langchain-google-genai` (3 provider)
- `tavily-python` (1 search provider)
- `langgraph-checkpoint-sqlite`
- `pydantic-settings`, `tiktoken`

Nhận xét: ODR rộng và chung; chat-agents hẹp nhưng deployable đầu-cuối.

---

## Phụ lục B: Tham chiếu nhanh đến code

**ODR key files đã khảo sát:**
- `src/open_deep_research/deep_researcher.py` — graph chính (30KB)
- `src/open_deep_research/state.py` — `AgentState`, `SupervisorState`, `ResearcherState`, `override_reducer`
- `src/open_deep_research/configuration.py` — 4 model roles, metadata UI
- `src/open_deep_research/prompts.py` — prompts cho mọi node (21KB)
- `src/open_deep_research/utils.py` — search wrappers, token limits, MCP adapters, summarizer (33KB)

**chat-agents key files dùng để so sánh:**
- `apps/api/app/services/agent_factory.py` — `create_deep_agent(...)` với 2 SubAgents
- `apps/api/app/routers/research.py` — SSE streaming + draft.md fallback
- `apps/api/app/streaming/chunk_mapper.py` — inference post-hoc từ 3 stream mode
- `apps/api/app/services/llm_factory.py` — 2 role (main + fast)
- `apps/api/app/streaming/events.py` — contract SSE
- `apps/api/app/config/settings.py` — settings env-backed
- `apps/api/prompts/{main,researcher,critic}/v*.md` — prompt registry file-backed

---

*Tài liệu này được tạo tự động từ session phân tích ngày 2026-04-23.*
