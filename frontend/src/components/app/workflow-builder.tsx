"use client";
import "@xyflow/react/dist/style.css";
import { useCallback, useEffect, useMemo, useState } from "react";
import { addEdge, Background, Controls, Handle, MiniMap, Position, ReactFlow, ReactFlowProvider, useEdgesState, useNodesState, useReactFlow, type Connection, type Edge, type Node, type NodeProps } from "@xyflow/react";
import { Bot, GitBranch, Mail, Plus, Repeat, Timer, Trash2, Zap, ShieldCheck, Database, FileText, Webhook, Filter, FileBarChart, CheckSquare, Workflow as WfIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge, Button, Field, Input, Select, Switch, Textarea } from "@/components/ui";

export type NodeSpec = { type: string; category: "trigger" | "action" | "logic"; label: string; description: string; fields: { key: string; label: string; type: string; required: boolean; options?: string[]; placeholder?: string }[]; handles: string[]; plan_feature: string | null };
export type Definition = { nodes: { id: string; type: string; position: { x: number; y: number }; data: { label: string; config: Record<string, unknown> } }[]; edges: { id: string; source: string; target: string; sourceHandle?: string | null }[] };
type NData = { label: string; config: Record<string, unknown>; spec: NodeSpec; error?: string };

const ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  "trigger.manual": Zap, "trigger.schedule": Timer, "trigger.webhook": Webhook, "trigger.form": FileText, "trigger.document_uploaded": FileText,
  "action.send_email": Mail, "action.ai_generate": Bot, "action.summarize_document": Bot, "action.extract_data": Database, "action.create_task": CheckSquare,
  "action.update_record": Database, "action.send_webhook": Webhook, "action.n8n": WfIcon, "action.generate_report": FileBarChart,
  "logic.if": GitBranch, "logic.filter": Filter, "logic.branch": GitBranch, "logic.delay": Timer, "logic.loop": Repeat, "logic.approval": ShieldCheck,
};
const CAT_CLS = { trigger: "border-l-[var(--chart-3)]", action: "border-l-[var(--brand)]", logic: "border-l-[var(--chart-2)]" };

function handlesOf(spec: NodeSpec, config: Record<string, unknown>) {
  if (spec.type === "logic.branch") return [...String(config.cases || "").split(",").map((c) => c.trim()).filter(Boolean), "default"];
  return spec.handles;
}

function FlowNode({ data, selected }: NodeProps<Node<NData>>) {
  const I = ICONS[data.spec.type] || Zap;
  const hs = handlesOf(data.spec, data.config);
  return (
    <div className={cn("min-w-[180px] max-w-[240px] rounded-xl border border-line border-l-4 bg-panel px-3 py-2.5 shadow-card", CAT_CLS[data.spec.category], selected && "ring-2 ring-brand", data.error && "ring-2 ring-danger")}>
      {data.spec.category !== "trigger" && <Handle type="target" position={Position.Left} />}
      <div className="flex items-center gap-2"><I className="h-3.5 w-3.5 text-subtle" /><span className="text-[10.5px] font-medium uppercase tracking-wide text-subtle">{data.spec.category}</span></div>
      <div className="mt-0.5 truncate text-[13px] font-medium text-fg">{data.label}</div>
      {data.error && <div className="mt-1 text-[11px] text-danger">{data.error}</div>}
      {hs.length === 1 ? <Handle type="source" position={Position.Right} id={hs[0]} /> : (
        <div className="mt-2 space-y-1">{hs.map((h) => (
          <div key={h} className="relative pr-3 text-right text-[10.5px] text-subtle">{h}<Handle type="source" position={Position.Right} id={h} style={{ top: "50%" }} /></div>
        ))}</div>
      )}
    </div>
  );
}
const nodeTypes = { nx: FlowNode };

function toFlow(def: Definition, specs: Record<string, NodeSpec>): { nodes: Node<NData>[]; edges: Edge[] } {
  return {
    nodes: def.nodes.filter((n) => specs[n.type]).map((n) => ({ id: n.id, type: "nx", position: n.position, data: { label: n.data?.label || specs[n.type].label, config: n.data?.config || {}, spec: specs[n.type] } })),
    edges: def.edges.map((e) => ({ id: e.id, source: e.source, target: e.target, sourceHandle: e.sourceHandle || (specs[def.nodes.find((n) => n.id === e.source)?.type || ""]?.handles.length === 1 ? specs[def.nodes.find((n) => n.id === e.source)!.type].handles[0] : null), label: e.sourceHandle && e.sourceHandle !== "out" ? e.sourceHandle : undefined })),
  };
}

export function fromFlow(nodes: Node<NData>[], edges: Edge[]): Definition {
  return {
    nodes: nodes.map((n) => ({ id: n.id, type: n.data.spec.type, position: { x: Math.round(n.position.x), y: Math.round(n.position.y) }, data: { label: n.data.label, config: n.data.config } })),
    edges: edges.map((e) => ({ id: e.id, source: e.source, target: e.target, sourceHandle: e.sourceHandle && e.sourceHandle !== "out" ? e.sourceHandle : null })),
  };
}

function Inner({ initial, specs, readOnly, onChange, errors }: { initial: Definition; specs: NodeSpec[]; readOnly: boolean; onChange: (d: Definition) => void; errors: Record<string, string> }) {
  const specMap = useMemo(() => Object.fromEntries(specs.map((s) => [s.type, s])), [specs]);
  const start = useMemo(() => toFlow(initial, specMap), [initial, specMap]);
  const [nodes, setNodes, onNodesChange] = useNodesState<Node<NData>>(start.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>(start.edges);
  const [sel, setSel] = useState<string | null>(null);
  const rf = useReactFlow();

  useEffect(() => { onChange(fromFlow(nodes, edges)); }, [nodes, edges]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { setNodes((ns) => ns.map((n) => ({ ...n, data: { ...n.data, error: errors[n.id] } }))); }, [errors, setNodes]);

  const onConnect = useCallback((c: Connection) => setEdges((es) => addEdge({ ...c, id: `${c.source}-${c.target}-${c.sourceHandle || "out"}`, label: c.sourceHandle && c.sourceHandle !== "out" ? c.sourceHandle : undefined }, es)), [setEdges]);
  const addNode = (spec: NodeSpec, pos?: { x: number; y: number }) => {
    if (spec.category === "trigger" && nodes.some((n) => n.data.spec.category === "trigger")) { alert("A workflow has exactly one trigger. Delete the existing trigger first."); return; }
    const id = `${spec.type.split(".")[1]}_${Math.random().toString(36).slice(2, 7)}`;
    const p = pos || { x: 120 + nodes.length * 40, y: 120 + nodes.length * 30 };
    setNodes((ns) => [...ns, { id, type: "nx", position: p, data: { label: spec.label, config: {}, spec } }]);
    setSel(id);
  };
  const selected = nodes.find((n) => n.id === sel);
  const updateSel = (patch: Partial<NData>) => setNodes((ns) => ns.map((n) => (n.id === sel ? { ...n, data: { ...n.data, ...patch } } : n)));
  const groups = (["trigger", "action", "logic"] as const).map((c) => ({ c, items: specs.filter((s) => s.category === c) }));

  return (
    <div className="flex h-full flex-col lg:flex-row">
      {!readOnly && (
        <aside className="max-h-48 shrink-0 overflow-y-auto border-b border-line p-3 lg:max-h-none lg:w-56 lg:border-b-0 lg:border-r" aria-label="Node palette">
          {groups.map((g) => (
            <div key={g.c} className="mb-3">
              <div className="mb-1.5 text-[11px] font-medium uppercase tracking-wide text-subtle">{g.c}s</div>
              <div className="grid grid-cols-2 gap-1 lg:grid-cols-1">{g.items.map((s) => {
                const I = ICONS[s.type] || Plus;
                return (
                  <button key={s.type} draggable onDragStart={(e) => e.dataTransfer.setData("application/nexora-node", s.type)} onClick={() => addNode(s)} title={s.description}
                    className="flex items-center gap-2 rounded-lg border border-line bg-panel px-2 py-1.5 text-left text-[12.5px] hover:border-brand">
                    <I className="h-3.5 w-3.5 shrink-0 text-subtle" /><span className="truncate">{s.label}</span>{s.plan_feature && <Badge tone="brand" className="ml-auto">Pro</Badge>}
                  </button>
                );
              })}</div>
            </div>
          ))}
        </aside>
      )}
      <div className="min-h-[420px] flex-1" onDragOver={(e) => e.preventDefault()} onDrop={(e) => {
        const t = e.dataTransfer.getData("application/nexora-node");
        if (t && specMap[t]) addNode(specMap[t], rf.screenToFlowPosition({ x: e.clientX, y: e.clientY }));
      }}>
        <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} onNodesChange={readOnly ? undefined : onNodesChange} onEdgesChange={readOnly ? undefined : onEdgesChange}
          onConnect={readOnly ? undefined : onConnect} onNodeClick={(_, n) => setSel(n.id)} onPaneClick={() => setSel(null)} fitView fitViewOptions={{ padding: 0.3 }}
          nodesDraggable={!readOnly} nodesConnectable={!readOnly} deleteKeyCode={readOnly ? null : ["Backspace", "Delete"]} proOptions={{ hideAttribution: true }}>
          <Background gap={18} size={1} /><Controls showInteractive={false} /><MiniMap pannable zoomable className="hidden md:block" />
        </ReactFlow>
      </div>
      {selected && (
        <aside className="max-h-[50vh] shrink-0 overflow-y-auto border-t border-line p-4 lg:max-h-none lg:w-80 lg:border-l lg:border-t-0" aria-label="Node configuration">
          <div className="mb-3 flex items-center justify-between"><Badge>{selected.data.spec.type}</Badge>
            {!readOnly && <Button size="sm" variant="ghost" className="text-danger" onClick={() => { setNodes((ns) => ns.filter((n) => n.id !== sel)); setEdges((es) => es.filter((e) => e.source !== sel && e.target !== sel)); setSel(null); }}><Trash2 className="h-4 w-4" /></Button>}</div>
          <p className="mb-3 text-[12.5px] text-subtle">{selected.data.spec.description}</p>
          <div className="space-y-3">
            <Field label="Label"><Input value={selected.data.label} onChange={(e) => updateSel({ label: e.target.value })} disabled={readOnly} /></Field>
            {selected.data.spec.fields.map((f) => {
              const v = selected.data.config[f.key];
              const set = (val: unknown) => updateSel({ config: { ...selected.data.config, [f.key]: val } });
              return (
                <Field key={f.key} label={`${f.label}${f.required ? " *" : ""}`}>
                  {f.type === "select" ? <Select value={String(v ?? "")} onChange={(e) => set(e.target.value)} disabled={readOnly}><option value="">—</option>{f.options?.map((o) => <option key={o} value={o}>{o || "any"}</option>)}</Select>
                    : f.type === "textarea" || f.type === "json" ? <Textarea rows={f.type === "json" ? 4 : 3} className={f.type === "json" ? "font-mono text-[12px]" : ""} value={String(v ?? "")} placeholder={f.placeholder} onChange={(e) => set(e.target.value)} disabled={readOnly} />
                      : f.type === "boolean" ? <Switch checked={v !== false && v !== "false"} onChange={set} label={v === false ? "Off" : "On"} disabled={readOnly} />
                        : <Input type={f.type === "number" ? "number" : "text"} value={String(v ?? "")} placeholder={f.placeholder} onChange={(e) => set(e.target.value)} disabled={readOnly} />}
                </Field>
              );
            })}
            <p className="rounded-lg bg-panel-2 p-2.5 text-[11.5px] text-subtle">Use <code className="font-mono">{"{{trigger.field}}"}</code>, <code className="font-mono">{"{{nodes.<id>.output.field}}"}</code> or <code className="font-mono">{"{{item}}"}</code> inside loops. Node id: <code className="font-mono">{selected.id}</code></p>
          </div>
        </aside>
      )}
    </div>
  );
}

export function WorkflowCanvas(props: { initial: Definition; specs: NodeSpec[]; readOnly: boolean; onChange: (d: Definition) => void; errors: Record<string, string> }) {
  return <ReactFlowProvider><Inner {...props} /></ReactFlowProvider>;
}
