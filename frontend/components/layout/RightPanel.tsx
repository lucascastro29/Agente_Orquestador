"use client";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { AgentsPanel } from "@/components/panels/AgentsPanel";
import { ConsolasPanel } from "@/components/panels/ConsolasPanel";
import { MemoryPanel } from "@/components/panels/MemoryPanel";
import { SecurityPanel } from "@/components/panels/SecurityPanel";
import { TeamPanel } from "@/components/panels/TeamPanel";

interface RightPanelProps {
  memoryRefresh: number;
  agentsRefresh: number;
}

export function RightPanel({ memoryRefresh, agentsRefresh }: RightPanelProps) {
  return (
    <div className="w-72 shrink-0 border-l border-border flex flex-col bg-muted/30 min-h-0">
      <Tabs defaultValue="agents" className="flex flex-col h-full min-h-0">
        <TabsList className="shrink-0 m-2 mb-0 grid grid-cols-5">
          <TabsTrigger value="agents"   className="text-[10px] px-1">Agentes</TabsTrigger>
          <TabsTrigger value="consolas" className="text-[10px] px-1">Consolas</TabsTrigger>
          <TabsTrigger value="memory"   className="text-[10px] px-1">Memoria</TabsTrigger>
          <TabsTrigger value="team"     className="text-[10px] px-1">Workers</TabsTrigger>
          <TabsTrigger value="security" className="text-[10px] px-1">Seg.</TabsTrigger>
        </TabsList>
        <div className="flex-1 overflow-y-auto mt-2 min-h-0">
          <TabsContent value="agents"   className="mt-0"><AgentsPanel refreshSignal={agentsRefresh} /></TabsContent>
          <TabsContent value="consolas" className="mt-0"><ConsolasPanel refreshSignal={agentsRefresh} /></TabsContent>
          <TabsContent value="memory"   className="mt-0"><MemoryPanel refreshSignal={memoryRefresh} /></TabsContent>
          <TabsContent value="team"     className="mt-0"><TeamPanel /></TabsContent>
          <TabsContent value="security" className="mt-0"><SecurityPanel /></TabsContent>
        </div>
      </Tabs>
    </div>
  );
}
