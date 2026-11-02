"use client";
import { use } from "react";
import { AssistantView } from "@/components/app/assistant";
export default function Page({ params }: { params: Promise<{ id: string }> }) { const { id } = use(params); return <AssistantView id={id} />; }
