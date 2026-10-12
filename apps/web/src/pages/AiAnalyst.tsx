/**
 * AI analyst — ask a question, get an answer that is fully traceable.
 *
 * The engine is deterministic by default (`engine: "deterministic-planner"`), and even when an LLM
 * planner is configured (`llm:*`) the numbers still come from the deterministic tool layer. Every
 * finding carries `[citation_id]` tokens which this page renders as chips linked to the evidence
 * table, and the whole tool-call audit trail is available in a collapsible table.
 */

import type { ReactElement, ReactNode } from "react";
import { useMemo, useState } from "react";

import { api, errorMessage } from "@/api/client";
import type { AgentAnswer, Evidence } from "@/api/types";
import { PageHeader } from "@/components/AppLayout";
import { DataTable } from "@/components/DataTable";
import { EmptyState, ErrorState, Skeleton, SkeletonTable } from "@/components/Feedback";
import { StatusBadge } from "@/components/StatusBadge";
import { formatPeriod, formatValue, NOT_AVAILABLE } from "@/lib/format";
import { cite } from "@/lib/data";
import { useAsync } from "@/lib/useAsync";
import { useFilters } from "@/lib/useFilters";

export const CITATION_PATTERN = /\[([a-z_]+:[^\]\s]+)\]/g;

const EXAMPLES = [
  "本期的风险信号有哪些？",
  "现金和流动性状况如何？",
  "毛利率和盈利能力变化的原因是什么？",
  "预算差异情况怎么样？",
  "利率和汇率变化对公司的敞口有多大？",
  "生成一份管理层报告",
];

/** Split a narrative line into text and `[citation_id]` chips. */
export function InlineCitations({ text, known }: { text: string; known: Set<string> }): ReactElement {
  const parts: ReactNode[] = [];
  let cursor = 0;
  let index = 0;
  const pattern = new RegExp(CITATION_PATTERN.source, "g");
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(text)) !== null) {
    if (match.index > cursor) parts.push(text.slice(cursor, match.index));
    const citation = match[1] ?? "";
    parts.push(
      <span
        key={`cite-${index++}`}
        data-testid="citation-chip"
        title={known.has(citation) ? "该引证在证据表中可查" : "证据表中未找到该引证"}
        className={`code mx-0.5 align-middle ${
          known.has(citation) ? "border border-accent/40 text-accent" : "border border-warn/40 text-warn"
        }`}
      >
        {citation}
      </span>,
    );
    cursor = match.index + match[0].length;
  }
  if (cursor < text.length) parts.push(text.slice(cursor));
  return <>{parts}</>;
}

function engineTone(engine: string): "accent" | "info" | "warn" {
  if (engine.startsWith("llm")) return "warn";
  return "accent";
}

export default function AiAnalyst() {
  const { latest } = useFilters();
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [answer, setAnswer] = useState<AgentAnswer | null>(null);

  const toolsState = useAsync((signal) => api.agentTools(signal), []);

  const known = useMemo(() => new Set(answer?.evidence.map((item) => item.citation_id) ?? []), [answer]);

  const ask = async (text: string) => {
    const trimmed = text.trim();
    if (trimmed.length < 2) {
      setError(new Error("问题至少需要 2 个字符（后端校验 min_length=2）"));
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const response = await api.askAgent({ question: trimmed, month: latest });
      setAnswer(response);
    } catch (caught) {
      setError(caught);
      setAnswer(null);
    } finally {
      setLoading(false);
    }
  };

  const evidenceColumns = [
    { key: "id", header: "引证 ID", render: (row: Evidence) => <span className="code">{row.citation_id}</span>, sortValue: (row: Evidence) => row.citation_id },
    { key: "kind", header: "类型", render: (row: Evidence) => <StatusBadge tone="neutral">{row.kind}</StatusBadge>, sortValue: (row: Evidence) => row.kind },
    { key: "label", header: "标签", render: (row: Evidence) => row.label, sortValue: (row: Evidence) => row.label },
    {
      key: "value",
      header: "数值（含单位）",
      align: "right" as const,
      render: (row: Evidence) => {
        const cited = cite(row.label, row.value, row.unit, row.period, "证据表中的该数值为空");
        return <span className="tnum">{formatValue(cited)}</span>;
      },
      sortValue: (row: Evidence) => row.value,
    },
    { key: "period", header: "期间", render: (row: Evidence) => <span className="tnum">{formatPeriod(row.period)}</span>, sortValue: (row: Evidence) => row.period },
    {
      key: "source",
      header: "来源",
      render: (row: Evidence) => (
        <span className="flex flex-wrap gap-1">
          {row.source_ids.length === 0 ? <span className="text-muted">无</span> : row.source_ids.map((id) => <span className="code" key={id}>{id}</span>)}
        </span>
      ),
    },
  ];

  const auditColumns = [
    { key: "call", header: "调用", render: (row: AgentAnswer["tool_calls"][number]) => <span className="font-mono text-[11px]">{row.call_id.slice(0, 8)}</span> },
    { key: "tool", header: "工具", render: (row: AgentAnswer["tool_calls"][number]) => <span className="font-medium">{row.tool}</span>, sortValue: (row: AgentAnswer["tool_calls"][number]) => row.tool },
    {
      key: "arguments",
      header: "参数",
      render: (row: AgentAnswer["tool_calls"][number]) => (
        <code className="code break-all">{JSON.stringify(row.arguments)}</code>
      ),
    },
    {
      key: "status",
      header: "状态",
      render: (row: AgentAnswer["tool_calls"][number]) => (
        <StatusBadge tone={row.status === "ok" ? "good" : row.status === "rejected" ? "warn" : "bad"} title={row.error ?? undefined}>
          {row.status}
        </StatusBadge>
      ),
      sortValue: (row: AgentAnswer["tool_calls"][number]) => row.status,
    },
    {
      key: "duration",
      header: "耗时 (ms)",
      align: "right" as const,
      render: (row: AgentAnswer["tool_calls"][number]) => <span className="tnum">{row.duration_ms.toFixed(1)}</span>,
      sortValue: (row: AgentAnswer["tool_calls"][number]) => row.duration_ms,
    },
    {
      key: "citations",
      header: "引证",
      render: (row: AgentAnswer["tool_calls"][number]) => (
        <span className="flex flex-wrap gap-1">
          {row.citations.length === 0 ? <span className="text-muted">无</span> : row.citations.map((id) => <span className="code" key={id}>{id}</span>)}
        </span>
      ),
    },
    { key: "summary", header: "结果摘要", render: (row: AgentAnswer["tool_calls"][number]) => <span className="text-[11px] text-muted">{row.result_summary || "—"}</span> },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="AI 分析师"
        description={
          <>
            数字来自确定性引擎与受限工具集，语言模型只负责规划与叙述，<strong>不计算任何数字</strong>。
            每条结论都通过 <span className="code">[citation_id]</span> 指向证据表。
          </>
        }
        actions={
          toolsState.data ? (
            <StatusBadge tone="info">可用工具 {toolsState.data.tools.length} 个</StatusBadge>
          ) : toolsState.loading ? (
            <Skeleton className="h-6 w-24" />
          ) : null
        }
      />

      <section className="card space-y-3">
        <form
          className="flex flex-wrap items-start gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            void ask(question);
          }}
        >
          <label className="sr-only" htmlFor="agent-question">
            问题
          </label>
          <input
            id="agent-question"
            className="input min-w-[16rem] flex-1"
            placeholder="例如：本期有哪些高风险信号？"
            value={question}
            maxLength={1000}
            onChange={(event) => setQuestion(event.target.value)}
          />
          <button type="submit" className="btn btn-primary" disabled={loading} data-testid="ask-button">
            {loading ? "分析中…" : "提问"}
          </button>
        </form>

        <div className="flex flex-wrap items-center gap-1.5">
          <span className="label">示例问题</span>
          {EXAMPLES.map((example) => (
            <button
              key={example}
              type="button"
              className="btn-chip"
              onClick={() => {
                setQuestion(example);
                void ask(example);
              }}
            >
              {example}
            </button>
          ))}
        </div>

        <p className="rounded-md border border-accent/30 bg-accent/5 px-3 py-2 text-[11px] text-ink">
          提示：本页所有数字均由后端确定性引擎（规则/财务模型 + 受限工具集）产生，语言模型只做规划与措辞。
          当前月份范围 <span className="tnum">{formatPeriod(latest)}</span>。
        </p>
      </section>

      {loading ? (
        <section className="card space-y-3">
          <Skeleton className="h-5 w-40" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-5/6" />
          <SkeletonTable rows={4} columns={5} />
        </section>
      ) : error ? (
        <ErrorState title="提问失败" error={error} message={errorMessage(error)} onRetry={() => void ask(question)} retrying={loading} />
      ) : !answer ? (
        <EmptyState
          title="尚未提问"
          description="在上方输入问题或点击示例问题。回答会包含结论、关键发现（带引证）、证据表、风险、建议、置信度边界、缺失数据与完整工具调用审计。"
        />
      ) : (
        <>
          <section className="card space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge tone={engineTone(answer.engine)} title="回答引擎">
                引擎 {answer.engine}
              </StatusBadge>
              {answer.engine.startsWith("llm") ? (
                <StatusBadge tone="warn">LLM 仅规划，数值仍来自确定性引擎</StatusBadge>
              ) : (
                <StatusBadge tone="good">确定性规划器：无 LLM 参与</StatusBadge>
              )}
              <StatusBadge tone="neutral">as_of {formatPeriod(answer.as_of)}</StatusBadge>
              <StatusBadge tone="info">合成数据 {String(answer.synthetic)}</StatusBadge>
              <span className="text-[11px] text-muted">工具调用 {answer.tool_calls.length} 次</span>
            </div>

            <div>
              <h2 className="card-title mb-1">结论</h2>
              <p className="text-sm leading-relaxed text-ink">
                <InlineCitations text={answer.conclusion} known={known} />
              </p>
            </div>

            <div>
              <h2 className="card-title mb-1">关键发现</h2>
              {answer.key_findings.length === 0 ? (
                <p className="text-xs text-muted">本次回答没有关键发现。</p>
              ) : (
                <ul className="list-disc space-y-1 pl-5 text-sm text-ink">
                  {answer.key_findings.map((finding) => (
                    <li key={finding}>
                      <InlineCitations text={finding} known={known} />
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </section>

          <section className="card">
            <h2 className="card-title mb-2">证据表</h2>
            {answer.evidence.length === 0 ? (
              <EmptyState title="没有证据条目" description="本次回答未引用任何引证。" />
            ) : (
              <DataTable columns={evidenceColumns} rows={answer.evidence} rowKey={(row) => row.citation_id} testId="evidence-table" />
            )}
          </section>

          <div className="grid gap-3 xl:grid-cols-2">
            <NarrativeBlock title="风险" items={answer.risks} known={known} tone="bad" />
            <NarrativeBlock title="建议" items={answer.recommendations} known={known} tone="good" />
            <NarrativeBlock title="假设" items={answer.assumptions} known={known} tone="neutral" />
            <NarrativeBlock title="置信度边界" items={answer.confidence_limits} known={known} tone="warn" />
            <NarrativeBlock title="缺失数据" items={answer.missing_data} known={known} tone="warn" />
          </div>

          <section className="card">
            <details>
              <summary className="cursor-pointer text-sm font-semibold text-ink">
                工具调用审计（{answer.tool_calls.length} 条）
              </summary>
              <p className="mt-2 text-[11px] text-muted">
                仅记录参数与耗时，不记录提示词、密钥或个人数据。
              </p>
              <div className="mt-2">
                {answer.tool_calls.length === 0 ? (
                  <EmptyState title="没有工具调用" description="后端返回的 tool_calls 为空。" />
                ) : (
                  <DataTable
                    columns={auditColumns}
                    rows={answer.tool_calls}
                    rowKey={(row) => row.call_id}
                    dense
                    testId="tool-call-table"
                  />
                )}
              </div>
            </details>
          </section>

          <section className="card text-[11px] text-muted">
            <div className="label mb-1">免责声明 disclaimer</div>
            <p>{answer.disclaimer || NOT_AVAILABLE}</p>
            <p className="mt-1">问题：{answer.question} · 单据 as_of {formatPeriod(answer.as_of)}</p>
          </section>
        </>
      )}
    </div>
  );
}

function NarrativeBlock({
  title,
  items,
  known,
  tone,
}: {
  title: string;
  items: string[];
  known: Set<string>;
  tone: "bad" | "good" | "warn" | "neutral";
}) {
  return (
    <section className="card">
      <div className="mb-2 flex items-center gap-2">
        <h2 className="card-title">{title}</h2>
        <StatusBadge tone={tone}>{items.length} 条</StatusBadge>
      </div>
      {items.length === 0 ? (
        <p className="text-xs text-muted">本次回答未提供{title}。</p>
      ) : (
        <ul className="list-disc space-y-1 pl-5 text-sm text-ink">
          {items.map((item) => (
            <li key={item}>
              <InlineCitations text={item} known={known} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
