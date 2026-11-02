"use client";
import { use, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { Button, Field, Input, Spinner, Textarea } from "@/components/ui";
import { Logo } from "@/components/app/logo";
import { titleCase } from "@/lib/utils";

export default function PublicForm({ params }: { params: Promise<{ token: string }> }) {
  const { token } = use(params);
  const [form, setForm] = useState<{ title: string; description: string; fields: string[] } | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [state, setState] = useState<"idle" | "sending" | "done">("idle");
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { api<typeof form>(`/forms/${token}`, { noOrg: true }).then(setForm).catch((e) => setErr(e instanceof ApiError ? e.message : "Form not found")); }, [token]);
  return (
    <div className="flex min-h-screen items-center justify-center px-4 py-10">
      <div className="w-full max-w-md rounded-2xl border border-line bg-panel p-6 shadow-pop">
        {err && <p className="text-sm text-danger">{err}</p>}
        {!form && !err && <Spinner />}
        {form && state === "done" && <div className="text-center"><h1 className="text-lg font-semibold">Thank you!</h1><p className="mt-2 text-sm text-muted">Your response has been received.</p></div>}
        {form && state !== "done" && (
          <form className="space-y-3.5" onSubmit={async (e) => {
            e.preventDefault(); setState("sending");
            try { await api(`/forms/${token}`, { body: { data: values }, noOrg: true }); setState("done"); } catch (e) { setErr(e instanceof ApiError ? e.message : "Failed"); setState("idle"); }
          }}>
            <h1 className="text-lg font-semibold">{form.title}</h1>
            {form.description && <p className="text-sm text-muted">{form.description}</p>}
            {form.fields.map((f) => (
              <Field key={f} label={titleCase(f)} htmlFor={f}>
                {/message|notes|description/.test(f) ? <Textarea id={f} value={values[f] || ""} onChange={(e) => setValues({ ...values, [f]: e.target.value })} />
                  : <Input id={f} type={f.includes("email") ? "email" : "text"} value={values[f] || ""} onChange={(e) => setValues({ ...values, [f]: e.target.value })} required={f === "email" || f === "name"} />}
              </Field>
            ))}
            <input type="text" name="website" className="hidden" tabIndex={-1} autoComplete="off" aria-hidden />
            <Button type="submit" className="w-full" loading={state === "sending"}>Submit</Button>
          </form>
        )}
        <div className="mt-6 flex justify-center opacity-70"><Logo className="scale-90" /></div>
      </div>
    </div>
  );
}
