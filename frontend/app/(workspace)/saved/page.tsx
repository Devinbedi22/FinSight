import { DemoNotice } from "@/components/cards";
import { Button, DataTable, EmptyState, PageHeader, Panel, PanelHeading, StatusBadge } from "@/components/ui";

export default function SavedAnalysesPage() {
  return (
    <>
      <PageHeader eyebrow="Personal workspace" title="Saved analyses" description="Return to events and decisions you have saved for later review." action={<StatusBadge>Local UI only</StatusBadge>} />
      <DemoNotice>Saved items require an account and persistence layer, neither of which is connected in this UI-only step.</DemoNotice>
      <Panel><PanelHeading title="Saved items" detail="No saved analyses" action={<Button variant="secondary" disabled>Export</Button>} /><EmptyState title="Nothing saved yet" description="Save an event or analysis from its detail page and it will appear here once persistence is implemented." /></Panel>
      <div className="mt-5 overflow-hidden rounded-xl border border-[#252d36]">
        <DataTable headers={["Company", "Event", "Decision", "Saved on", "Status"]}>
          <tr><td colSpan={5} className="py-5 text-center text-xs text-[#74808c]">No rows to display</td></tr>
        </DataTable>
      </div>
    </>
  );
}
