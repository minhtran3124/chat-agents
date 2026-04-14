# LangChain Deep Agents — Ghi chú Review

**Nguồn:** *LangChain Just Released Deep Agents and It Changes How You Build AI Systems* — Towards AI (qua Freedium mirror)
**Ngày review:** 2026-04-13

---

## Tóm tắt nhanh (TL;DR)

Deep Agents là một **"harness" có quan điểm sẵn** do LangChain mới phát hành, xây dựng trên nền LangGraph. Nó tích hợp sẵn năm năng lực mà các team AI lâu nay phải tự xây lại nhiều lần — lập kế hoạch, virtual filesystem, spawn subagent, tự động nén context, và bộ nhớ xuyên hội thoại — giúp developer tập trung vào logic ứng dụng thay vì hạ tầng agent.

> *"Vẫn là core tool-calling loop giống các framework khác, nhưng tích hợp sẵn một bộ capability."*

---

## Vấn đề mà Deep Agents giải quyết

Lộ trình điển hình của team dùng LangChain:

1. Bắt đầu với **LangChain chain** đơn giản.
2. Lên **LangGraph** khi task cần tool calling + vòng lặp.
3. Nhận ra LangGraph là *runtime cấp thấp* — phải tự viết state schema, conditional edge, logic compile **trước khi** chạm đến bài toán nghiệp vụ thực sự.

Deep Agents lấp khoảng trống này. Nó là lớp "default có quan điểm" giúp team khỏi phải tái phát minh cùng những pattern quản lý context, điều phối subagent, và memory lặp đi lặp lại.

---

## Kiến trúc — Ba lớp

```
┌─────────────────────────────────┐
│  Deep Agents (harness, default) │   ← MỚI
├─────────────────────────────────┤
│  LangGraph (runtime)            │   persistence, streaming, interrupt
├─────────────────────────────────┤
│  LangChain (building block)     │   model, tool, prompt
└─────────────────────────────────┘
```

---

## Năm năng lực tích hợp sẵn

| # | Năng lực | Làm gì |
|---|---|---|
| 1 | **Lập kế hoạch (`write_todos`)** | Agent tự phân rã task phức tạp thành bước, theo dõi trạng thái, điều chỉnh kế hoạch. To-do list tồn tại suốt session. |
| 2 | **Virtual Filesystem** | Khi kết quả tool vượt ~20,000 token, chúng được đẩy sang backend cấu hình được; chỉ preview tham chiếu ở lại trong context. Nén thông minh, không phải cắt cụt. |
| 3 | **Spawn Subagent (tool `task`)** | Giao các subtask độc lập cho agent chuyên biệt với context sạch. Giúp agent chính không bị ngập. |
| 4 | **Nén context tự động** | Khi đạt ~85% giới hạn context, harness tạo summary có cấu trúc thay cho lịch sử hội thoại. Bản gốc lưu xuống filesystem. |
| 5 | **Bộ nhớ xuyên hội thoại** | State bền vững qua LangGraph Store — preference và tiến độ sống sót qua thread và restart. |

---

## Ví dụ code tối thiểu

```python
from deepagents import create_deep_agent

agent = create_deep_agent(
    tools=[get_weather],
    system_prompt="You are a helpful assistant",
)
```

Ví dụ research agent:

```python
from deepagents import create_deep_agent
from tavily import TavilyClient

agent = create_deep_agent(
    model="anthropic:claude-sonnet-4-6",
    tools=[internet_search],
    system_prompt="You are an expert researcher...",
)

result = agent.invoke({
    "messages": [{
        "role": "user",
        "content": "Research agentic AI frameworks and write a report.",
    }]
})
```

Mọi thứ — build graph, quản state, streaming, offload filesystem, spawn subagent, nén context — đều được xử lý bên trong.

---

## Khi nào dùng vs. Khi nào KHÔNG dùng

**Dùng Deep Agents khi:**
- Task cần lập kế hoạch nhiều bước
- Tool result lớn và cần quản lý
- Cần session dài có bộ nhớ bền vững
- Tự động hóa nghiên cứu, phân tích tài chính, workflow code với skill tuỳ biến

**KHÔNG dùng khi:**
- Cần agent đơn giản → dùng `create_agent` của LangChain
- Cần kiểm soát chi tiết → dùng raw LangGraph

Hướng dẫn chính thức của thư viện: *"cho agent đơn giản, hãy dùng công cụ đơn giản."*

---

## Đánh đổi (Tradeoffs)

- **Được:** convention-over-configuration — team thôi tái phát minh cùng một hạ tầng.
- **Mất:** quyền kiểm soát chi tiết. Abstraction có quan điểm riêng; loop tuỳ chỉnh vẫn phải xuống raw LangGraph.

---

## Điểm mấu chốt

Deep Agents ra mắt đúng thời điểm vì agentic AI đã vượt qua giai đoạn "làm cho nó gọi được tool" và bước vào giai đoạn **thực thi tác vụ dài hạn đáng tin cậy**. Ngành này đã liên tục xây lại cùng những pattern (offload context, giao việc cho subagent, kiến trúc memory) một cách cô lập. Chuẩn hóa những pattern đó kéo developer quay lại tập trung vào bài toán ứng dụng thực sự.

Quyết định thực tế cho mỗi team: *lợi ích của abstraction có bù cho việc mất kiểm soát trong use case của mình không?*

---

## Ghi chú cá nhân / Câu hỏi cần khám phá

- Ngưỡng offload 20,000 token tương tác thế nào với context window riêng của từng provider (ví dụ Claude 200k / 1M)?
- Backend của virtual filesystem có swap được sang Redis không (liên quan đến hạ tầng `chat-agents`)?
- `write_todos` so với cơ chế task-tracking của Claude Code — cùng mental model?
- `create_deep_agent()` có hỗ trợ provider non-Anthropic như first-class không, hay ưu tiên Anthropic?
