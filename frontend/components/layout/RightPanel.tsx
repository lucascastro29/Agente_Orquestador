"use client";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { AgentsPanel } from "@/components/panels/AgentsPanel";
import { MemoryPanel } from "@/components/panels/MemoryPanel";
import { SecurityPanel } from "@/components/panels/SecurityPanel";
import { TeamPanel } from "@/components/panels/TeamPanel";

interface RightPanelProps {
  memoryRefresh: number;
}

export function RightPanel({ memoryRefresh }: RightPanelProps) {
  return (
    <div className="w-72 shrink-0 border-l border-border flex flex-col bg-muted/30 min-h-0">
      <Tabs defaultValue="agents" className="flex flex-col h-full min-h-0">
        <TabsList className="shrink-0 m-2 mb-0 grid grid-cols-4">
          <TabsTrigger value="agents"   className="text-[11px] px-1">Agentes</TabsTrigger>
          <TabsTrigger value="memory"   className="text-[11px] px-1">Memoria</TabsTrigger>
          <TabsTrigger value="team"     className="text-[11px] px-1">Workers</TabsTrigger>
          <TabsTrigger value="security" className="text-[11px] px-1">Seguridad</TabsTrigger>
        </TabsList>
        <div className="flex-1 overflow-y-auto mt-2 min-h-0">
          <TabsContent value="agents"   className="mt-0"><AgentsPanel /></TabsContent>
          <TabsContent value="memory"   className="mt-0"><MemoryPanel refreshSignal={memoryRefresh} /></TabsContent>
          <TabsContent value="team"     className="mt-0"><TeamPanel /></TabsContent>
          <TabsContent value="security" className="mt-0"><SecurityPanel /></TabsContent>
        </div>
      </Tabs>
    </div>
  );
}
