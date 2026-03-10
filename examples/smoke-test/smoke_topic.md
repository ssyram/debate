---
topic: "函数式编程风格 vs 面向对象编程风格：哪种更适合作为现代后端项目的主要范式？"
rounds: 1
cross_exam: 0
max_reply_tokens: 1500
timeout: 300

debaters:
  - name: "FP-Advocate"
    base_url: "http://localhost:8081/v1/chat/completions"
    api_key: "dummy"
    model: "yunwu/claude-sonnet-4-6"
    style: "函数式编程支持者，强调不可变性、纯函数和可组合性"

  - name: "OOP-Advocate"
    base_url: "http://localhost:8082/v1/chat/completions"
    api_key: "dummy"
    model: "yunwu/claude-sonnet-4-6"
    style: "面向对象编程支持者，强调封装、继承和设计模式"

judge:
  base_url: "http://localhost:8083/v1/chat/completions"
  api_key: "dummy"
  model: "yunwu/claude-sonnet-4-6"
  max_tokens: 2000
---

## 辩题说明

函数式编程（FP）和面向对象编程（OOP）是现代后端开发的两大主流范式。请双方基于自身立场，从以下角度展开论证：

- 代码可维护性和可测试性
- 并发处理能力
- 团队协作和学习曲线
- 典型使用场景和生态支持

请直接给出简洁有力的论点，无需查阅外部资料。
