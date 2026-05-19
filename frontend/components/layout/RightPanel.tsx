"use client";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";
import { MemoryPanel } from "@/components/panels/MemoryPanel";
import { SecurityPanel } from "@/components/panels/SecurityPanel";
import { TeamPanel } from "@/components/panels/TeamPanel";

interface RightPanelProps {
  memoryRefresh: number;
}

export function RightPanel({ memoryRefresh }: RightPanelProps) {
  return (
    <div className="w-72 shrink-0 border-l border-border flex flex-col bg-muted/30">
      <Tabs defaultValue="memory" className="flex flex-col h-full">
        <TabsList className="shrink-0 m-2 mb-0 grid grid-cols-3">
          <TabsTrigger value="memory"   className="text-xs">Memoria</TabsTrigger>
          <TabsTrigger value="team"     className="text-xs">Equipo</TabsTrigger>
          <TabsTrigger value="security" className="text-xs">Seguridad</TabsTrigger>
        </TabsList>
        <ScrollArea className="flex-1 mt-2">
          <TabsContent value="memory"   className="mt-0"><MemoryPanel refreshSignal={memoryRefresh} /></TabsContent>
          <TabsContent value="team"     className="mt-0"><TeamPanel /></TabsContent>
          <TabsContent value="security" className="mt-0"><SecurityPanel /></TabsContent>
        </ScrollArea>
      </Tabs>
    </div>
  );
}
