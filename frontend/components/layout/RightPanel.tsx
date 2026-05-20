"use client";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { AgentsPanel } from "@/components/panels/AgentsPanel";
import { MemoryPanel } from "@/components/panels/MemoryPanel";
import { SecurityPanel } from "@/components/panels/SecurityPanel";
import { TeamPanel } from "@/components/panels/TeamPanel";
import { PlaybooksPanel } from "@/components/panels/PlaybooksPanel";

interface RightPanelProps {
  memoryRefresh: number;
  agentsRefresh: number;
  onRunPlaybook?: (message: string) => void;
}

export function RightPanel({ memoryRefresh, agentsRefresh, onRunPlaybook }: RightPanelProps) {
  return (
    <div className="w-80 shrink-0 border-l border-zinc-800 flex flex-col bg-zinc-900/50 min-h-0">
      <Tabs defaultValue="agents" className="flex flex-col h-full min-h-0">
        <TabsList className="shrink-0 m-2 mb-0 grid grid-cols-5 bg-zinc-800/60 rounded-lg">
          <TabsTrigger value="agents"    className="text-[10px] px-0.5 data-[state=active]:bg-zinc-700 data-[state=active]:text-zinc-100 text-zinc-400">Agentes</TabsTrigger>
          <TabsTrigger value="memory"    className="text-[10px] px-0.5 data-[state=active]:bg-zinc-700 data-[state=active]:text-zinc-100 text-zinc-400">Memoria</TabsTrigger>
          <TabsTrigger value="flujos"    className="text-[10px] px-0.5 data-[state=active]:bg-zinc-700 data-[state=active]:text-zinc-100 text-zinc-400">Flujos</TabsTrigger>
          <TabsTrigger value="team"      className="text-[10px] px-0.5 data-[state=active]:bg-zinc-700 data-[state=active]:text-zinc-100 text-zinc-400">Workers</TabsTrigger>
          <TabsTrigger value="security"  className="text-[10px] px-0.5 data-[state=active]:bg-zinc-700 data-[state=active]:text-zinc-100 text-zinc-400">Seg.</TabsTrigger>
        </TabsList>
        <div className="flex-1 overflow-y-auto mt-2 min-h-0">
          <TabsContent value="agents"   className="mt-0"><AgentsPanel refreshSignal={agentsRefresh} /></TabsContent>
          <TabsContent value="memory"   className="mt-0"><MemoryPanel refreshSignal={memoryRefresh} /></TabsContent>
          <TabsContent value="flujos"   className="mt-0"><PlaybooksPanel onRunPlaybook={onRunPlaybook} /></TabsContent>
          <TabsContent value="team"     className="mt-0"><TeamPanel /></TabsContent>
          <TabsContent value="security" className="mt-0"><SecurityPanel /></TabsContent>
        </div>
      </Tabs>
    </div>
  );
}
